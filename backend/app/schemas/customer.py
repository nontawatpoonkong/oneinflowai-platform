"""Customer schemas: create/update requests, response, list params, paging."""

import enum
import re
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.customer import CustomerStatus

_PHONE_RE = re.compile(r"^\+?[0-9][0-9\s\-()]{5,19}$")


def _trim_optional(value: str | None) -> str | None:
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def _validate_phone(value: str | None) -> str | None:
    if value is None:
        return None
    if not _PHONE_RE.match(value):
        raise ValueError("Invalid phone number format")
    return value


class CustomerSortField(enum.StrEnum):
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"
    DISPLAY_NAME = "display_name"


class SortOrder(enum.StrEnum):
    ASC = "asc"
    DESC = "desc"


class CustomerCreate(BaseModel):
    display_name: str = Field(max_length=150)
    full_name: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=32)
    email: EmailStr | None = None
    avatar_url: str | None = Field(default=None, max_length=1024)
    notes: str | None = None
    status: CustomerStatus = CustomerStatus.ACTIVE

    @field_validator("display_name", mode="before")
    @classmethod
    def _validate_display_name(cls, value: object) -> object:
        if isinstance(value, str):
            trimmed = value.strip()
            if not trimmed:
                raise ValueError("display_name cannot be empty")
            return trimmed
        return value

    @field_validator("full_name", "phone", "avatar_url", "notes", mode="before")
    @classmethod
    def _trim(cls, value: object) -> object:
        return _trim_optional(value) if isinstance(value, str) else value

    @field_validator("phone")
    @classmethod
    def _phone(cls, value: str | None) -> str | None:
        return _validate_phone(value)


class CustomerUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=150)
    full_name: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=32)
    email: EmailStr | None = None
    avatar_url: str | None = Field(default=None, max_length=1024)
    notes: str | None = None
    status: CustomerStatus | None = None

    @field_validator("display_name", mode="before")
    @classmethod
    def _validate_display_name(cls, value: object) -> object:
        if isinstance(value, str):
            trimmed = value.strip()
            if not trimmed:
                raise ValueError("display_name cannot be empty")
            return trimmed
        return value

    @field_validator("full_name", "phone", "avatar_url", "notes", mode="before")
    @classmethod
    def _trim(cls, value: object) -> object:
        return _trim_optional(value) if isinstance(value, str) else value

    @field_validator("phone")
    @classmethod
    def _phone(cls, value: str | None) -> str | None:
        return _validate_phone(value)


class CustomerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    display_name: str
    full_name: str | None
    phone: str | None
    email: str | None
    avatar_url: str | None
    notes: str | None
    status: CustomerStatus
    created_at: datetime
    updated_at: datetime


class CustomerListResponse(BaseModel):
    items: list[CustomerResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
