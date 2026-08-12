"""Provider-neutral SaaS billing boundary; no provider is selected yet."""

from typing import Protocol


class BillingProvider(Protocol):
    name: str

    async def create_checkout(self, *args, **kwargs) -> str: ...

    async def verify_event(self, payload: bytes, signature: str) -> dict: ...
