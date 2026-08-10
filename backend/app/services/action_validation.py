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
        normalized, missing, invalid = self.validate_partial(definition, payload)
        if missing or invalid:
            details = {"missing_fields": missing}
            if invalid:
                details["invalid_fields"] = sorted(invalid)
            raise ActionPayloadValidationError(details=details)
        return normalized

    def validate_partial(
        self, definition: ActionDefinition, payload: dict[str, Any]
    ) -> tuple[dict[str, Any], list[str], dict[str, str]]:
        fields = [*definition.required_fields, *definition.optional_fields]
        specifications = {field["key"]: field for field in fields}
        unknown = sorted(set(payload) - set(specifications))
        system = sorted(self._SYSTEM_FIELDS.intersection(payload))
        if unknown or system:
            missing = [
                field["key"]
                for field in definition.required_fields
                if field["key"] not in payload
            ]
            raise ActionPayloadValidationError(
                details={
                    "missing_fields": missing,
                    "unknown_fields": sorted(set(unknown + system)),
                }
            )
        normalized: dict[str, Any] = {}
        invalid: dict[str, str] = {}
        for key, value in payload.items():
            specification = specifications[key]
            if not self._valid_type(specification["type"], value):
                invalid[key] = "invalid type or empty value"
                continue
            if specification["type"] == "enum" and value not in specification.get(
                "values", []
            ):
                invalid[key] = "unsupported enum value"
                continue
            normalized[key] = value.strip() if isinstance(value, str) else value
        missing = [
            field["key"]
            for field in definition.required_fields
            if field["key"] not in normalized and field["key"] not in invalid
        ]
        return normalized, missing, invalid

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
