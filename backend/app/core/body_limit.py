"""Request body limits enforced while the body arrives (pure ASGI).

FastAPI reads and spools a multipart body to temporary files before any
dependency or endpoint runs, so a size check in the endpoint only happens
after the whole upload has reached disk. This middleware refuses a request
whose declared Content-Length is over the limit before reading anything,
and counts the bytes actually received, which also covers chunked bodies
with no Content-Length and bodies that send more than they declared.

Every route gets the default limit; upload and webhook routes declare their
own. An upload rule can also pre-authorize the request from its headers, so
a client without a valid token is refused before it can send a large body.
"""

import json
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.exceptions import AppError
from app.schemas.response import error_response


class RequestBodyTooLargeError(OSError):
    """Raised from `receive` once a body passes its limit.

    It is an OSError so Starlette's multipart parser closes, and thereby
    deletes, the temporary files it already created for the request.
    """


@dataclass(frozen=True, slots=True)
class BodyLimitRule:
    """The body limit for one route.

    `path` is the route path as declared, where each `{name}` matches one
    path segment. `preauthorize` sees only the headers, runs before any body
    byte is read, and rejects the request by returning an `AppError`.
    """

    method: str
    path: str
    max_bytes: int
    preauthorize: Callable[[Scope], AppError | None] | None = None


_REJECTION = json.dumps(
    error_response(
        message="Request body exceeds the allowed size",
        code="REQUEST_BODY_TOO_LARGE",
    )
).encode()

_PLACEHOLDER = re.compile(r"\{[^/{}]+\}")


class BodySizeLimitMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        default_max_bytes: int,
        rules: Sequence[BodyLimitRule] = (),
    ) -> None:
        self.app = app
        self.default_max_bytes = default_max_bytes
        self.rules = [(rule, _compile(rule.path)) for rule in rules]

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        rule = self._match(scope)
        limit = rule.max_bytes if rule else self.default_max_bytes
        declared = _declared_length(scope)
        if declared is not None and declared > limit:
            await _send(send, 413, _REJECTION)
            return
        if rule and rule.preauthorize:
            error = rule.preauthorize(scope)
            if error is not None:
                await _send_error(send, error)
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
                    await _send(send, 413, _REJECTION)
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
                await _send(send, 413, _REJECTION)

    def _match(self, scope: Scope) -> BodyLimitRule | None:
        method = scope["method"]
        path = _route_path(scope)
        for rule, pattern in self.rules:
            if rule.method == method and pattern.fullmatch(path):
                return rule
        return None


def _compile(template: str) -> re.Pattern[str]:
    parts = _PLACEHOLDER.split(template)
    return re.compile("[^/]+".join(re.escape(part) for part in parts))


def _route_path(scope: Scope) -> str:
    """The path routing matches on: `path` without a mounted `root_path`."""
    path: str = scope["path"]
    root_path: str = scope.get("root_path", "")
    if root_path and path.startswith(root_path + "/"):
        return path[len(root_path) :]
    return path


def _declared_length(scope: Scope) -> int | None:
    for name, value in scope.get("headers") or []:
        if name == b"content-length":
            try:
                return int(value)
            except ValueError:
                return None
    return None


async def _send_error(send: Send, error: AppError) -> None:
    body = json.dumps(
        error_response(message=error.message, code=error.code, details=error.details)
    ).encode()
    await _send(send, error.status_code, body)


async def _send(send: Send, status: int, body: bytes) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
                (b"connection", b"close"),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})
