"""Deterministic non-intelligent generation provider for local use and tests."""

from app.integrations.generation.base import GenerationRequest, GenerationResult


class DevelopmentGenerationProvider:
    name = "development"

    def __init__(self, model: str = "development-grounded-v1") -> None:
        self.model = model

    async def generate(self, prompt: GenerationRequest) -> GenerationResult:
        if not prompt.system_prompt or not prompt.user_prompt:
            raise ValueError("generation prompts must not be empty")
        return GenerationResult(
            text="Development grounded response [S1]",
            model=self.model,
            provider=self.name,
            finish_reason="stop",
        )
