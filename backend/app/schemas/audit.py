"""Public contracts for audit history and bounded usage ingestion."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator

from app.models.audit import ProductFeature

SafePropertyValue = Annotated[str, Field(max_length=120)] | int | bool


class ProductUsageEventCreate(BaseModel):
    event_name: Literal["PAGE_VIEW"] = "PAGE_VIEW"
    navigation_id: uuid.UUID
    session_id: uuid.UUID | None = None
    page_path: Annotated[str, Field(min_length=1, max_length=255)]
    feature: ProductFeature
    safe_properties: dict[str, SafePropertyValue] = Field(default_factory=dict)
    occurred_at: datetime

    @field_validator("page_path")
    @classmethod
    def validate_page_path(cls, value: str) -> str:
        if not value.startswith("/dashboard") or "?" in value or "#" in value:
            raise ValueError("page_path must be a normalized dashboard path")
        return value

    @field_validator("occurred_at")
    @classmethod
    def validate_occurred_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("occurred_at must include a timezone")
        return value

    @field_validator("safe_properties")
    @classmethod
    def validate_safe_properties(cls, value):
        if value:
            raise ValueError("PAGE_VIEW does not accept additional properties")
        return value


class ProductUsageEventResponse(BaseModel):
    id: uuid.UUID
    event_name: str
    page_path: str
    feature: str | None
    occurred_at: datetime


class AuditActorResponse(BaseModel):
    id: uuid.UUID | None
    type: str
    name: str


class AuditEventResponse(BaseModel):
    id: uuid.UUID
    actor: AuditActorResponse
    action: str
    area: str
    resource_type: str
    resource_id: uuid.UUID | None
    route: str | None
    request_method: str | None
    result: str
    correlation_id: str | None
    safe_metadata: dict
    occurred_at: datetime


class AuditEventPage(BaseModel):
    items: list[AuditEventResponse]
    page: int
    page_size: int
    total: int
    pages: int
