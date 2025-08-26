"""
Unified data types and enums for cross-platform messaging compatibility.

This module defines the common types used across all messaging platforms
to ensure consistent data handling regardless of the underlying platform.
"""

from enum import Enum
from typing import Any


class PlatformType(str, Enum):
    """Supported messaging platforms in the Mimeia platform."""

    WHATSAPP = "whatsapp"
    TELEGRAM = "telegram"
    TEAMS = "teams"
    INSTAGRAM = "instagram"


class MessageType(str, Enum):
    """Universal message types across all platforms."""

    TEXT = "text"
    INTERACTIVE = "interactive"
    BUTTON = "button"  # Button reply messages (WhatsApp quick reply buttons)
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    DOCUMENT = "document"
    CONTACT = "contact"
    LOCATION = "location"
    ORDER = "order"  # Order/catalog messages
    STICKER = "sticker"
    REACTION = "reaction"
    SYSTEM = "system"  # System notifications, member joins, etc.
    UNSUPPORTED = "unsupported"  # Unsupported message types


class WebhookType(str, Enum):
    """Types of webhook events that platforms can send."""

    INCOMING_MESSAGES = "incoming_messages"
    STATUS_UPDATES = "status_updates"
    ERRORS = "errors"
    MEMBER_UPDATES = "member_updates"  # For group/channel management
    SYSTEM_EVENTS = "system_events"


class MessageStatus(str, Enum):
    """Universal message delivery status across platforms."""

    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"
    DELETED = "deleted"
    PENDING = "pending"


class InteractiveType(str, Enum):
    """Types of interactive elements across platforms."""

    BUTTON_REPLY = "button_reply"
    LIST_REPLY = "list_reply"
    QUICK_REPLY = "quick_reply"
    INLINE_KEYBOARD = "inline_keyboard"  # Telegram inline keyboards
    CAROUSEL = "carousel"
    MENU = "menu"


class MediaType(str, Enum):
    """Media content types with MIME type mapping."""

    IMAGE_JPEG = "image/jpeg"
    IMAGE_PNG = "image/png"
    IMAGE_GIF = "image/gif"
    IMAGE_WEBP = "image/webp"

    AUDIO_AAC = "audio/aac"
    AUDIO_MP3 = "audio/mp3"
    AUDIO_OGG = "audio/ogg"
    AUDIO_WAV = "audio/wav"

    VIDEO_MP4 = "video/mp4"
    VIDEO_AVI = "video/avi"
    VIDEO_MOV = "video/mov"
    VIDEO_WEBM = "video/webm"

    DOCUMENT_PDF = "application/pdf"
    DOCUMENT_DOC = "application/msword"
    DOCUMENT_DOCX = (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    DOCUMENT_TXT = "text/plain"
    DOCUMENT_CSV = "text/csv"


class ConversationType(str, Enum):
    """Types of conversations across platforms."""

    PRIVATE = "private"  # 1-on-1 conversation
    GROUP = "group"  # Group chat
    CHANNEL = "channel"  # Broadcast channel
    BUSINESS = "business"  # Business conversation (WhatsApp Business)


class UserRole(str, Enum):
    """User roles in conversations."""

    MEMBER = "member"
    ADMIN = "admin"
    OWNER = "owner"
    MODERATOR = "moderator"
    BOT = "bot"


# Type aliases for complex types
PlatformData = dict[str, Any]
MessageMetadata = dict[str, Any]
UniversalMessageData = dict[str, str | int | bool | None | dict | list]


class ErrorCode(str, Enum):
    """Universal error codes for webhook processing."""

    VALIDATION_ERROR = "validation_error"
    AUTHENTICATION_ERROR = "authentication_error"
    RATE_LIMIT_ERROR = "rate_limit_error"
    PLATFORM_ERROR = "platform_error"
    NETWORK_ERROR = "network_error"
    PROCESSING_ERROR = "processing_error"
    UNKNOWN_MESSAGE_TYPE = "unknown_message_type"
    SIGNATURE_VALIDATION_FAILED = "signature_validation_failed"


class ProcessingPriority(str, Enum):
    """Priority levels for message processing."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


# Platform capability mapping
PLATFORM_CAPABILITIES = {
    PlatformType.WHATSAPP: {
        "message_types": {
            MessageType.TEXT,
            MessageType.INTERACTIVE,
            MessageType.BUTTON,
            MessageType.IMAGE,
            MessageType.AUDIO,
            MessageType.VIDEO,
            MessageType.DOCUMENT,
            MessageType.CONTACT,
            MessageType.LOCATION,
            MessageType.ORDER,
            MessageType.STICKER,
            MessageType.REACTION,
            MessageType.SYSTEM,
            MessageType.UNSUPPORTED,
        },
        "interactive_types": {InteractiveType.BUTTON_REPLY, InteractiveType.LIST_REPLY},
        "max_text_length": 4096,
        "max_media_size": 16 * 1024 * 1024,  # 16MB
        "supports_threads": False,
        "supports_reactions": True,
        "supports_editing": False,
    },
    PlatformType.TELEGRAM: {
        "message_types": {
            MessageType.TEXT,
            MessageType.INTERACTIVE,
            MessageType.IMAGE,
            MessageType.AUDIO,
            MessageType.VIDEO,
            MessageType.DOCUMENT,
            MessageType.CONTACT,
            MessageType.LOCATION,
            MessageType.STICKER,
        },
        "interactive_types": {
            InteractiveType.INLINE_KEYBOARD,
            InteractiveType.QUICK_REPLY,
        },
        "max_text_length": 4096,
        "max_media_size": 50 * 1024 * 1024,  # 50MB
        "supports_threads": True,
        "supports_reactions": True,
        "supports_editing": True,
    },
    PlatformType.TEAMS: {
        "message_types": {MessageType.TEXT, MessageType.IMAGE, MessageType.DOCUMENT},
        "interactive_types": {InteractiveType.BUTTON_REPLY, InteractiveType.CAROUSEL},
        "max_text_length": 28000,
        "max_media_size": 100 * 1024 * 1024,  # 100MB
        "supports_threads": True,
        "supports_reactions": True,
        "supports_editing": True,
    },
    PlatformType.INSTAGRAM: {
        "message_types": {
            MessageType.TEXT,
            MessageType.IMAGE,
            MessageType.VIDEO,
            MessageType.STICKER,
        },
        "interactive_types": {
            InteractiveType.QUICK_REPLY,
            InteractiveType.BUTTON_REPLY,
        },
        "max_text_length": 1000,
        "max_media_size": 8 * 1024 * 1024,  # 8MB
        "supports_threads": False,
        "supports_reactions": True,
        "supports_editing": False,
    },
}


def get_platform_capabilities(platform: PlatformType) -> dict[str, Any]:
    """Get capabilities for a specific platform."""
    return PLATFORM_CAPABILITIES.get(platform, {})


def is_message_type_supported(
    platform: PlatformType, message_type: MessageType
) -> bool:
    """Check if a message type is supported by a platform."""
    capabilities = get_platform_capabilities(platform)
    return message_type in capabilities.get("message_types", set())


def is_interactive_type_supported(
    platform: PlatformType, interactive_type: InteractiveType
) -> bool:
    """Check if an interactive type is supported by a platform."""
    capabilities = get_platform_capabilities(platform)
    return interactive_type in capabilities.get("interactive_types", set())


def get_max_text_length(platform: PlatformType) -> int:
    """Get maximum text length for a platform."""
    capabilities = get_platform_capabilities(platform)
    return capabilities.get("max_text_length", 4096)


def get_max_media_size(platform: PlatformType) -> int:
    """Get maximum media file size for a platform."""
    capabilities = get_platform_capabilities(platform)
    return capabilities.get("max_media_size", 16 * 1024 * 1024)
