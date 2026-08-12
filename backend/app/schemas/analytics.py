"""Typed aggregate analytics responses without customer-level PII."""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel


class CountPoint(BaseModel):
    date: date
    count: int


class NamedCount(BaseModel):
    key: str
    label: str | None = None
    count: int


class MoneyTotal(BaseModel):
    currency: str
    amount: Decimal


class AnalyticsRange(BaseModel):
    start: datetime
    end: datetime
    timezone: str = "UTC"


class AnalyticsOverview(BaseModel):
    range: AnalyticsRange
    kpis: dict[str, int | float]
    conversation_trend: list[CountPoint]
    conversations_by_channel: list[NamedCount]
    message_counts: list[NamedCount]
    handoff_reasons: list[NamedCount]
    actions_by_type: list[NamedCount]
    action_statuses: list[NamedCount]
    payment_statuses: list[NamedCount]
    verified_amounts: list[MoneyTotal]
    verification_statuses: list[NamedCount]
    current_queue: dict[str, int]
