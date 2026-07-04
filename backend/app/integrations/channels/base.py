"""Multi-channel foundation.

Defines the channel-agnostic contract that concrete channel adapters (web,
LINE, Facebook, ...) will implement in future sprints. This is *structure
only* — no channel is implemented here.

The intent is that inbound platform payloads are normalized into
`InboundMessage`, and application responses are expressed as `OutboundMessage`
regardless of the originating channel, so the conversation/AI layers stay
channel-independent.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar

from app.core.channels import ChannelType

__all__ = [
    "BaseChannelAdapter",
    "ChannelType",
    "InboundMessage",
    "OutboundMessage",
]


@dataclass(slots=True)
class InboundMessage:
    """Normalized inbound message from any channel."""

    channel: ChannelType
    channel_user_id: str
    text: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class OutboundMessage:
    """Channel-agnostic outbound message."""

    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseChannelAdapter(ABC):
    """Interface every channel adapter must implement.

    Concrete adapters register themselves via the channel registry. Method
    bodies are intentionally left abstract for a later sprint.
    """

    channel_type: ClassVar[ChannelType]

    @abstractmethod
    async def verify_signature(self, *, body: bytes, signature: str) -> bool:
        """Validate an inbound webhook's authenticity."""
        raise NotImplementedError

    @abstractmethod
    async def parse_inbound(self, payload: dict[str, Any]) -> list[InboundMessage]:
        """Translate a raw platform payload into normalized messages."""
        raise NotImplementedError

    @abstractmethod
    async def send_message(
        self, *, channel_user_id: str, message: OutboundMessage
    ) -> None:
        """Deliver an outbound message to the channel."""
        raise NotImplementedError
