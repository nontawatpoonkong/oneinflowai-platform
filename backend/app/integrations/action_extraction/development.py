"""Deterministic, no-network action extraction provider for development/tests."""

import json

from app.core.exceptions import ActionCollectionProviderError
from app.integrations.action_extraction.base import (
    ActionFieldExtractionRequest,
    ActionFieldExtractionResult,
)


class DevelopmentActionFieldExtractionProvider:
    name = "development"

    async def extract(
        self, request: ActionFieldExtractionRequest
    ) -> ActionFieldExtractionResult:
        try:
            value = json.loads(request.user_input)
        except (json.JSONDecodeError, TypeError) as exc:
            raise ActionCollectionProviderError() from exc
        if not isinstance(value, dict):
            raise ActionCollectionProviderError()
        return ActionFieldExtractionResult(provider=self.name, candidates=value)
