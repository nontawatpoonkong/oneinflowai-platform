"""Strict provider-neutral action payload validation."""

from typing import Any

from app.core.exceptions import ActionPayloadValidationError
from app.models.action import ActionDefinition


class ActionPayloadValidator:
    _SYSTEM_FIELDS = {
        "workspace_id",
        "status",
        "priority",
        "assigned_to_user_id",
        "created_by_type",
    }

    def validate(
        self, definition: ActionDefinition, payload: dict[str, Any]
    ) -> dict[str, Any]:
        fields = [*definition.required_fields, *definition.optional_fields]
        specifications = {field["key"]: field for field in fields}
        missing = [
            field["key"]
            for field in definition.required_fields
            if field["key"] not in payload
        ]
        unknown = sorted(set(payload) - set(specifications))
        if missing or unknown or self._SYSTEM_FIELDS.intersection(payload):
            raise ActionPayloadValidationError(
                details={"missing_fields": missing, "unknown_fields": unknown}
            )
        normalized = {}
        errors = []
        for key, value in payload.items():
            specification = specifications[key]
            if not self._valid_type(specification["type"], value):
                errors.append(key)
                continue
            if specification["type"] == "enum" and value not in specification.get(
                "values", []
            ):
                errors.append(key)
                continue
            normalized[key] = value.strip() if isinstance(value, str) else value
        if errors:
            raise ActionPayloadValidationError(details={"invalid_fields": errors})
        return normalized

    @staticmethod
    def _valid_type(field_type: str, value: Any) -> bool:
        if field_type == "string":
            return isinstance(value, str) and bool(value.strip())
        if field_type == "integer":
            return isinstance(value, int) and not isinstance(value, bool)
        if field_type == "number":
            return isinstance(value, (int, float)) and not isinstance(value, bool)
        if field_type == "boolean":
            return isinstance(value, bool)
        return field_type == "enum"
