"""
WhatsApp message type schemas.

This package contains specific Pydantic models for each WhatsApp message type
including text, interactive, media, contact, location, and system messages.
"""

# Import all message type schemas
from .audio import AudioContent, WhatsAppAudioMessage
from .button import ButtonContent, WhatsAppButtonMessage
from .contact import (
    ContactAddress,
    ContactEmail,
    ContactInfo,
    ContactName,
    ContactOrganization,
    ContactPhone,
    ContactUrl,
    WhatsAppContactMessage,
)
from .document import DocumentContent, WhatsAppDocumentMessage
from .errors import WhatsAppWebhookError, create_webhook_error_from_raw
from .image import ImageContent, WhatsAppImageMessage
from .interactive import (
    ButtonReply,
    InteractiveContent,
    ListReply,
    WhatsAppInteractiveMessage,
)
from .location import LocationContent, WhatsAppLocationMessage
from .order import OrderContent, OrderProductItem, WhatsAppOrderMessage
from .reaction import ReactionContent, WhatsAppReactionMessage
from .sticker import StickerContent, WhatsAppStickerMessage
from .system import SystemContent, WhatsAppSystemMessage
from .text import TextContent, WhatsAppTextMessage
from .unsupported import WhatsAppUnsupportedMessage
from .video import VideoContent, WhatsAppVideoMessage

__all__ = [
    # Audio message schemas
    "AudioContent",
    "WhatsAppAudioMessage",
    # Button message schemas
    "ButtonContent",
    "WhatsAppButtonMessage",
    # Contact message schemas
    "ContactAddress",
    "ContactEmail",
    "ContactName",
    "ContactOrganization",
    "ContactPhone",
    "ContactUrl",
    "ContactInfo",
    "WhatsAppContactMessage",
    # Document message schemas
    "DocumentContent",
    "WhatsAppDocumentMessage",
    # Error schemas (webhook-level)
    "WhatsAppWebhookError",
    "create_webhook_error_from_raw",
    # Image message schemas
    "ImageContent",
    "WhatsAppImageMessage",
    # Interactive message schemas
    "ButtonReply",
    "ListReply",
    "InteractiveContent",
    "WhatsAppInteractiveMessage",
    # Location message schemas
    "LocationContent",
    "WhatsAppLocationMessage",
    # Order message schemas
    "OrderProductItem",
    "OrderContent",
    "WhatsAppOrderMessage",
    # Reaction message schemas
    "ReactionContent",
    "WhatsAppReactionMessage",
    # Sticker message schemas
    "StickerContent",
    "WhatsAppStickerMessage",
    # System message schemas
    "SystemContent",
    "WhatsAppSystemMessage",
    # Text message schemas
    "TextContent",
    "WhatsAppTextMessage",
    # Unsupported message schemas
    "WhatsAppUnsupportedMessage",
    # Video message schemas
    "VideoContent",
    "WhatsAppVideoMessage",
]
