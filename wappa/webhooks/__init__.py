"""Webhook schemas and parsers for Wappa framework."""

from .core.types import UniversalMessageData
from .core.webhook_interfaces.universal_webhooks import (
    ErrorWebhook,
    IncomingMessageWebhook,
    StatusWebhook,
    UniversalWebhook,
)

__all__ = [
    "UniversalWebhook",
    "IncomingMessageWebhook",
    "StatusWebhook",
    "ErrorWebhook",
    "UniversalMessageData",
]
