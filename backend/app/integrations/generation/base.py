"""Provider-neutral generation contracts."""

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class GenerationRequest:
    system_prompt: str
    user_prompt: str
    temperature: float
    max_output_tokens: int
    output_schema: dict[str, Any] | None = None
    output_schema_name: str | None = None


@dataclass(frozen=True, slots=True)
class GenerationResult:
    text: str
    model: str
    provider: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    finish_reason: str | None = None


class GenerationProvider(Protocol):
    name: str

    async def generate(self, prompt: GenerationRequest) -> GenerationResult: ...
