"""
Wappa Webhook Schemas and Universal Interfaces

Provides clean access to webhook schemas and universal interfaces for
processing incoming webhooks from different messaging platforms.

Clean Architecture: Domain models and platform-agnostic interfaces.

Usage:
    # Universal webhook interfaces (user requested: quick access to webhook schemas)
    from wappa.webhooks import IncomingMessageWebhook, StatusWebhook, ErrorWebhook

    # WhatsApp webhook schemas
    from wappa.webhooks.whatsapp import WhatsAppWebhook, WhatsAppMetadata

    # Message type schemas
    from wappa.webhooks.whatsapp.message_types import TextMessage, ImageMessage
"""

# Universal Webhook Interfaces (User Request: Quick access to these)
from .core.base_webhook import BaseContact, BaseWebhook, BaseWebhookMetadata
from .core.types import PlatformType, UniversalMessageData, WebhookType
from .core.webhook_interfaces.universal_webhooks import (
    ErrorWebhook,
    IncomingMessageWebhook,
    StatusWebhook,
    UniversalWebhook,
)
from .whatsapp.base_models import (
    ContactProfile,
    Conversation,
    ErrorData,
    MessageContext,
    MessageError,
    Pricing,
    WhatsAppContact,
    WhatsAppMetadata,
)

# WhatsApp Webhook Schemas
from .whatsapp.webhook_container import WhatsAppWebhook

__all__ = [
    # Universal Interfaces (Clean Access as Requested)
    "UniversalWebhook",
    "IncomingMessageWebhook",
    "StatusWebhook",
    "ErrorWebhook",
    "UniversalMessageData",
    "PlatformType",
    "WebhookType",
    "BaseWebhook",
    "BaseWebhookMetadata",
    "BaseContact",
    # WhatsApp Core Schemas
    "WhatsAppWebhook",
    "WhatsAppMetadata",
    "WhatsAppContact",
    "ContactProfile",
    "MessageContext",
    "MessageError",
    "ErrorData",
    "Pricing",
    "Conversation",
]
