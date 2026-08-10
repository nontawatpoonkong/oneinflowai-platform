"""Explicit-command action intent routing for deterministic development use."""

from app.integrations.action_intent.base import ActionIntentRequest, ActionIntentResult


class DevelopmentActionIntentProvider:
    name = "development"

    async def route(self, request: ActionIntentRequest) -> ActionIntentResult:
        message = request.message.strip()
        if not message.lower().startswith("action:"):
            return ActionIntentResult(None, 0.0)
        command, separator, field_input = message.partition(" ")
        key = command[7:].strip()
        if not key:
            return ActionIntentResult(None, 0.0)
        return ActionIntentResult(
            selected_action_key=key,
            confidence=1.0,
            field_input=field_input.strip() if separator else None,
        )
