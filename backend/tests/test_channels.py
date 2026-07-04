"""Multi-channel scaffolding tests.

Validates the registry contract without implementing any real channel.
"""

from typing import Any

import pytest

from app.integrations.channels.base import (
    BaseChannelAdapter,
    ChannelType,
    InboundMessage,
    OutboundMessage,
)
from app.integrations.channels.registry import (
    available_channels,
    get_adapter_class,
    register_channel,
)


def test_registry_is_empty_by_default() -> None:
    assert available_channels() == []


def test_get_unregistered_adapter_raises() -> None:
    with pytest.raises(LookupError):
        get_adapter_class(ChannelType.LINE)


def test_register_and_resolve_adapter() -> None:
    class _DummyWebAdapter(BaseChannelAdapter):
        channel_type = ChannelType.WEB

        async def verify_signature(self, *, body: bytes, signature: str) -> bool:
            return True

        async def parse_inbound(self, payload: dict[str, Any]) -> list[InboundMessage]:
            return []

        async def send_message(
            self, *, channel_user_id: str, message: OutboundMessage
        ) -> None:
            return None

    try:
        register_channel(_DummyWebAdapter)
        assert ChannelType.WEB in available_channels()
        assert get_adapter_class(ChannelType.WEB) is _DummyWebAdapter
    finally:
        # Keep global registry clean for other tests.
        from app.integrations.channels import registry

        registry._REGISTRY.clear()
