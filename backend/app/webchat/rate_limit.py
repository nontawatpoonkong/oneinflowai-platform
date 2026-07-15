"""Isolated rate-limit hook for public WebChat endpoints."""

from fastapi import Request


async def enforce_webchat_rate_limit(request: Request) -> None:
    # TODO: Replace with the platform Redis limiter once a shared rate-limit
    # abstraction and trusted-proxy IP handling are available.
    return None
