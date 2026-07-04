"""Canonical communication channel types.

Single source of truth shared by the customer domain (channel identities) and
the integrations layer (channel adapters).
"""

import enum


class ChannelType(enum.StrEnum):
    WEB = "web"
    LINE = "line"
    FACEBOOK = "facebook"
    EMAIL = "email"
    WHATSAPP = "whatsapp"
    INSTAGRAM = "instagram"
    TELEGRAM = "telegram"
