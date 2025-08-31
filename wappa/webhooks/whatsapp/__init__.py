"""
WhatsApp Webhook Schemas

Contains Pydantic models for processing WhatsApp Business Platform webhooks,
including all message types, status updates, and system events.

Domain Layer: WhatsApp-specific webhook models and validation.

Usage:
    from wappa.webhooks.whatsapp import WhatsAppWebhook, WhatsAppMetadata
    from wappa.webhooks.whatsapp.message_types import TextMessage, ImageMessage
"""

# Main webhook container
# Base models and metadata
from .base_models import (
    ContactProfile,
    Conversation,
    ErrorData,
    MessageContext,
    MessageError,
    Pricing,
    WhatsAppContact,
    WhatsAppMetadata,
)

# Status models
from .status_models import (
    DeliveryStatus,
    FailedStatus,
    MessageStatus,
    ReadStatus,
    SentStatus,
    StatusType,
)
from .webhook_container import WhatsAppWebhook

__all__ = [
    # Main webhook
    "WhatsAppWebhook",
    # Base models
    "WhatsAppMetadata",
    "WhatsAppContact",
    "ContactProfile",
    "MessageContext",
    "MessageError",
    "ErrorData",
    "Pricing",
    "Conversation",
    # Status models
    "MessageStatus",
    "StatusType",
    "DeliveryStatus",
    "ReadStatus",
    "SentStatus",
    "FailedStatus",
]
