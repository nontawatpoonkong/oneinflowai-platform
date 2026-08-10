"""Provider-neutral contracts for untrusted action field extraction."""

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class ActionFieldExtractionRequest:
    field_schema: tuple[dict[str, Any], ...]
    user_input: str
    collected_payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ActionFieldExtractionResult:
    provider: str
    candidates: dict[str, Any]


class ActionFieldExtractionProvider(Protocol):
    name: str

    async def extract(
        self, request: ActionFieldExtractionRequest
    ) -> ActionFieldExtractionResult: ...
