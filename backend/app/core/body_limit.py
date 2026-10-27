"""Per-route request body limits enforced while the body arrives (pure ASGI).

FastAPI reads and spools a multipart body to temporary files before any
dependency or endpoint runs, so a size check in the endpoint only happens
after the whole upload has reached disk. This middleware refuses a request
whose declared Content-Length is over the limit before reading anything,
and counts the bytes actually received, which also covers chunked bodies
with no Content-Length and bodies that send more than they declared.
"""

import json

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.schemas.response import error_response


class RequestBodyTooLargeError(OSError):
    """Raised from `receive` once a body passes its limit.

    It is an OSError so Starlette's multipart parser closes, and thereby
    deletes, the temporary files it already created for the request.
    """


_REJECTION = json.dumps(
    error_response(
        message="Request body exceeds the allowed size",
        code="REQUEST_BODY_TOO_LARGE",
    )
).encode()


class BodySizeLimitMiddleware:
    def __init__(self, app: ASGIApp, *, limits: dict[tuple[str, str], int]) -> None:
        self.app = app
        self.limits = limits

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        limit = self.limits.get((scope["method"], scope["path"]))
        if limit is None:
            await self.app(scope, receive, send)
            return
        declared = _declared_length(scope)
        if declared is not None and declared > limit:
            await _reject(send)
            return

        received = 0
        exceeded = False
        response_started = False

        async def limited_receive() -> Message:
            nonlocal received, exceeded
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    exceeded = True
                    raise RequestBodyTooLargeError("Request body exceeds the limit")
            return message

        async def guarded_send(message: Message) -> None:
            nonlocal response_started
            if exceeded:
                # Replace whatever error the application produced for the
                # aborted body with one consistent 413.
                if message["type"] == "http.response.start" and not response_started:
                    response_started = True
                    await _reject(send)
                return
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, guarded_send)
        except Exception:
            if not exceeded:
                raise
            if not response_started:
                await _reject(send)


def _declared_length(scope: Scope) -> int | None:
    for name, value in scope.get("headers") or []:
        if name == b"content-length":
            try:
                return int(value)
            except ValueError:
                return None
    return None


async def _reject(send: Send) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(_REJECTION)).encode()),
                (b"connection", b"close"),
            ],
        }
    )
    await send({"type": "http.response.body", "body": _REJECTION})
