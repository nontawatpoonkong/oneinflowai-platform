"""Channel connection API schemas without credential response fields."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.channels import ChannelType
from app.models.channel import ChannelConnectionStatus, ChannelDeliveryStatus


class LineConnectionCreate(BaseModel):
    display_name: str = Field(min_length=1, max_length=160)
    external_account_id: str = Field(min_length=1, max_length=255)
    external_account_name: str | None = Field(default=None, max_length=255)
    channel_access_token: str = Field(min_length=1, max_length=4096)
    channel_secret: str = Field(min_length=1, max_length=1024)


class FacebookConnectionCreate(BaseModel):
    display_name: str = Field(min_length=1, max_length=160)
    external_account_id: str = Field(min_length=1, max_length=255)
    external_account_name: str | None = Field(default=None, max_length=255)
    page_access_token: str = Field(min_length=1, max_length=4096)
    app_secret: str = Field(min_length=1, max_length=1024)
    verify_token: str = Field(min_length=16, max_length=1024)


class ChannelConnectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    workspace_id: uuid.UUID
    provider: ChannelType
    display_name: str
    external_account_id: str
    external_account_name: str | None
    status: ChannelConnectionStatus
    connected_at: datetime | None
    last_verified_at: datetime | None
    last_error_code: str | None
    created_at: datetime
    updated_at: datetime


class ChannelDeliveryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    status: ChannelDeliveryStatus
    provider_message_id: str | None
    last_error_code: str | None
    sent_at: datetime | None
