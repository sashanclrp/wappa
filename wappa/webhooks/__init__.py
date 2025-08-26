"""Webhook schemas and parsers for Wappa framework."""

from .core.webhook_interfaces.universal_webhooks import (
    ErrorWebhook,
    IncomingMessageWebhook, 
    StatusWebhook,
    UniversalWebhook,
)
from .core.types import UniversalMessageData

__all__ = [
    "UniversalWebhook",
    "IncomingMessageWebhook",
    "StatusWebhook", 
    "ErrorWebhook",
    "UniversalMessageData",
]