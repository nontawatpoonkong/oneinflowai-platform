"""Request ID middleware (pure ASGI).

Assigns a request ID to every HTTP request:
  - reuses an inbound `X-Request-ID` header if present, otherwise generates
    a UUID v4;
  - stores it in the request-scoped contextvar so logs are correlated;
  - exposes it on `request.state.request_id`;
  - echoes it back on the response `X-Request-ID` header.

Implemented as pure ASGI (not BaseHTTPMiddleware) so the contextvar is set
in the same task that runs the endpoint, guaranteeing log correlation.
"""

import re
import uuid

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.context import request_id_var

REQUEST_ID_HEADER = b"x-request-id"
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


class RequestIDMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        inbound = headers.get(REQUEST_ID_HEADER)
        try:
            candidate = inbound.decode("ascii") if inbound else ""
        except UnicodeDecodeError:
            candidate = ""
        request_id = (
            candidate
            if _SAFE_REQUEST_ID.fullmatch(candidate)
            else str(uuid.uuid4())
        )

        token = request_id_var.set(request_id)

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                response_headers = message.setdefault("headers", [])
                response_headers.append((REQUEST_ID_HEADER, request_id.encode()))
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            request_id_var.reset(token)
