"""
Wappa Webhook Schemas and Universal Interfaces

Provides a stable import surface for universal webhook models and
platform-specific webhook schemas.

Usage:
    # Universal webhook interfaces
    from wappa.webhooks import InboundMessageWebhook, StatusWebhook, ErrorWebhook, SystemWebhook

    # WhatsApp webhook schemas
    from wappa.webhooks.whatsapp import WhatsAppWebhook, WhatsAppMetadata

    # Message type schemas
    from wappa.webhooks.whatsapp.message_types import TextMessage, ImageMessage
"""

from wappa.schemas.core.types import PlatformType, UniversalMessageData, WebhookType

from .core.base_message import BaseMessage
from .core.base_webhook import BaseContact, BaseWebhook, BaseWebhookMetadata
from .core.webhook_interfaces.base_components import InboxBase, SystemEventDetail
from .core.webhook_interfaces.universal_webhooks import (
    CallWebhook,
    CustomWebhook,
    ErrorWebhook,
    InboundMessageWebhook,
    StatusWebhook,
    SystemEventType,
    SystemWebhook,
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
from .whatsapp.webhook_container import WhatsAppWebhook

__all__ = [
    "UniversalWebhook",
    "InboundMessageWebhook",
    "CallWebhook",
    "StatusWebhook",
    "ErrorWebhook",
    "SystemWebhook",
    "SystemEventType",
    "CustomWebhook",
    "UniversalMessageData",
    "PlatformType",
    "WebhookType",
    "BaseWebhook",
    "BaseWebhookMetadata",
    "BaseContact",
    "WhatsAppWebhook",
    "WhatsAppMetadata",
    "WhatsAppContact",
    "ContactProfile",
    "MessageContext",
    "MessageError",
    "ErrorData",
    "Pricing",
    "Conversation",
    # Base message and webhook components
    "BaseMessage",
    "InboxBase",
    "SystemEventDetail",
]
