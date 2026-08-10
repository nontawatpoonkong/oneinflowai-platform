"""Official OpenAI Responses API generation adapter."""

from typing import Any

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError,
    RateLimitError,
)

from app.core.exceptions import (
    GenerationAuthenticationError,
    GenerationMalformedResponseError,
    GenerationNetworkError,
    GenerationRateLimitError,
    GenerationServerError,
    GenerationTimeoutError,
)
from app.integrations.generation.base import GenerationRequest, GenerationResult


class OpenAIGenerationProvider:
    name = "openai"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout_seconds: float,
        client: AsyncOpenAI | Any | None = None,
    ) -> None:
        if not api_key or not model or timeout_seconds <= 0:
            raise ValueError("valid OpenAI generation configuration is required")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.client = client or AsyncOpenAI(api_key=api_key, timeout=timeout_seconds)

    async def generate(self, prompt: GenerationRequest) -> GenerationResult:
        try:
            response = await self.client.responses.create(
                model=self.model,
                instructions=prompt.system_prompt,
                input=prompt.user_prompt,
                temperature=prompt.temperature,
                max_output_tokens=prompt.max_output_tokens,
                timeout=self.timeout_seconds,
            )
        except AuthenticationError as exc:
            raise GenerationAuthenticationError() from exc
        except RateLimitError as exc:
            raise GenerationRateLimitError() from exc
        except APITimeoutError as exc:
            raise GenerationTimeoutError() from exc
        except APIConnectionError as exc:
            raise GenerationNetworkError() from exc
        except APIStatusError as exc:
            raise GenerationServerError() from exc

        text = getattr(response, "output_text", None)
        model = getattr(response, "model", None)
        if not isinstance(text, str) or not text.strip() or not isinstance(model, str):
            raise GenerationMalformedResponseError()
        usage = getattr(response, "usage", None)
        return GenerationResult(
            text=text.strip(),
            model=model,
            provider=self.name,
            input_tokens=getattr(usage, "input_tokens", None),
            output_tokens=getattr(usage, "output_tokens", None),
            total_tokens=getattr(usage, "total_tokens", None),
            finish_reason=getattr(response, "status", None),
        )
