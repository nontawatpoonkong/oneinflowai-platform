"""Typed contracts for the deliberately bounded automation foundation."""

import enum
import re
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.automation import (
    AutomationActionType,
    AutomationScheduleMode,
)

SUPPORTED_EVENTS = frozenset(
    {
        "hotel.booking.confirmed",
        "hotel.booking.cancelled",
        "hotel.booking.expired",
        "hotel.payment.verified",
        "hotel.payment.requires_review",
        "hotel.stay.created",
        "hotel.stay.checked_in",
        "hotel.stay.checked_out",
        "hotel.stay.no_show",
        "hotel.room.dirty",
        "hotel.housekeeping.completed",
        "hotel.room.ready",
    }
)
CONDITION_FIELDS = frozenset(
    {
        "property_id",
        "currency",
        "total_amount",
        "booking_id",
        "customer_id",
        "conversation_id",
        "room_id",
        "stay_id",
    }
)
TEMPLATE_VARIABLES = frozenset(
    {
        "customer_name",
        "booking_reference",
        "check_in",
        "check_out",
        "property_name",
        "currency",
        "total_amount",
    }
)
_TEMPLATE_RE = re.compile(r"{{\s*([a-z_][a-z0-9_]*)\s*}}")
_UNSAFE_TEMPLATE_RE = re.compile(r"{%|{#")


class ConditionOperator(enum.StrEnum):
    EQ = "EQ"
    NE = "NE"
    IN = "IN"
    GTE = "GTE"
    LTE = "LTE"


class AutomationCondition(BaseModel):
    field: str
    operator: ConditionOperator
    value: str | int | float | Decimal | bool | list[str | int | float | bool]

    @field_validator("field")
    @classmethod
    def supported_field(cls, value: str) -> str:
        if value not in CONDITION_FIELDS:
            raise ValueError("Unsupported condition field")
        return value

    @model_validator(mode="after")
    def operator_value_shape(self):
        if self.operator is ConditionOperator.IN and not isinstance(self.value, list):
            raise ValueError("IN requires a non-empty list")
        if self.operator is ConditionOperator.IN and not self.value:
            raise ValueError("IN requires a non-empty list")
        if self.operator is not ConditionOperator.IN and isinstance(self.value, list):
            raise ValueError("Only IN accepts a list")
        return self


class AutomationDefinitionInput(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    active: bool = False
    trigger_event_type: str
    trigger_version: Literal[1] = 1
    conditions: list[AutomationCondition] = Field(default_factory=list, max_length=10)
    action_type: AutomationActionType
    action_config: dict[str, Any]
    schedule_mode: AutomationScheduleMode = AutomationScheduleMode.IMMEDIATE
    schedule_config: dict[str, Any] = Field(default_factory=dict)

    @field_validator("trigger_event_type")
    @classmethod
    def supported_trigger(cls, value: str) -> str:
        if value not in SUPPORTED_EVENTS:
            raise ValueError("Unsupported automation trigger")
        return value

    @model_validator(mode="after")
    def validate_bounded_config(self):
        if self.action_type is AutomationActionType.CUSTOMER_MESSAGE:
            if set(self.action_config) != {"template"}:
                raise ValueError("Customer message config accepts only template")
            validate_template(self.action_config.get("template"))
        elif self.action_type is AutomationActionType.INTERNAL_NOTIFICATION:
            allowed = {"title", "body", "recipient", "notification_type"}
            if set(self.action_config) - allowed:
                raise ValueError("Unsupported notification action config")
            for required in ("title", "body"):
                value = self.action_config.get(required)
                if not isinstance(value, str) or not value.strip():
                    raise ValueError(f"{required} is required")
                validate_template(value)
            if (
                self.action_config.get("recipient", "administrators")
                != "administrators"
            ):
                raise ValueError("Only administrative recipients are supported")
        mode = self.schedule_mode
        config = self.schedule_config
        if mode is AutomationScheduleMode.IMMEDIATE:
            if config:
                raise ValueError("Immediate schedule has no configuration")
        elif mode is AutomationScheduleMode.DELAY_AFTER_EVENT:
            if set(config) != {"delay_seconds"} or not isinstance(
                config.get("delay_seconds"), int
            ):
                raise ValueError("Delay schedule requires delay_seconds")
            if not 0 <= config["delay_seconds"] <= 2_592_000:
                raise ValueError("delay_seconds is outside the supported range")
        else:
            if set(config) != {"date_field", "offset_seconds", "local_time"}:
                raise ValueError(
                    "Date schedule requires date_field, offset_seconds, local_time"
                )
            if config["date_field"] not in {"check_in", "check_out"}:
                raise ValueError("Unsupported schedule date field")
            if not isinstance(config["offset_seconds"], int):
                raise ValueError("offset_seconds must be an integer")
            if not re.fullmatch(
                r"(?:[01]\d|2[0-3]):[0-5]\d", str(config["local_time"])
            ):
                raise ValueError("local_time must be HH:MM")
        return self


class AutomationDefinitionCreate(AutomationDefinitionInput):
    pass


class AutomationDefinitionPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    active: bool | None = None
    trigger_event_type: str | None = None
    trigger_version: Literal[1] | None = None
    conditions: list[AutomationCondition] | None = Field(default=None, max_length=10)
    action_type: AutomationActionType | None = None
    action_config: dict[str, Any] | None = None
    schedule_mode: AutomationScheduleMode | None = None
    schedule_config: dict[str, Any] | None = None


class AutomationDefinitionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    active: bool
    trigger_event_type: str
    trigger_version: int
    conditions: list[dict[str, Any]]
    action_type: str
    action_config: dict[str, Any]
    schedule_mode: str
    schedule_config: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class AutomationExecutionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    workspace_id: uuid.UUID
    automation_id: uuid.UUID
    event_id: uuid.UUID
    status: str
    scheduled_for: datetime
    started_at: datetime | None
    completed_at: datetime | None
    attempt_count: int
    manual_retry_count: int
    last_error_code: str | None
    terminal_failure: bool
    claimed_by_worker_id: str | None
    last_recovered_at: datetime | None
    failure_history: list[dict[str, Any]]
    created_at: datetime
    updated_at: datetime


def validate_template(value: Any) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= 1000:
        raise ValueError("Template must contain 1-1000 characters")
    if _UNSAFE_TEMPLATE_RE.search(value):
        raise ValueError("Unsafe template syntax")
    unknown = set(_TEMPLATE_RE.findall(value)) - TEMPLATE_VARIABLES
    if unknown:
        raise ValueError(f"Unknown template variable: {sorted(unknown)[0]}")
    residue = _TEMPLATE_RE.sub("", value)
    if "{{" in residue or "}}" in residue:
        raise ValueError("Invalid template syntax")
    return value
