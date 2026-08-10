"""Provider-neutral, non-mutating action intent contracts."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ActionIntentOption:
    key: str
    name: str
    description: str | None


@dataclass(frozen=True, slots=True)
class ActionIntentRequest:
    message: str
    options: tuple[ActionIntentOption, ...]


@dataclass(frozen=True, slots=True)
class ActionIntentResult:
    selected_action_key: str | None
    confidence: float
    field_input: str | None = None


class ActionIntentProvider(Protocol):
    name: str

    async def route(self, request: ActionIntentRequest) -> ActionIntentResult: ...
