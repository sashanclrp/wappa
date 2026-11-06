"""
Unified data types and enums for cross-platform messaging compatibility.

This module defines the common types used across all messaging platforms
to ensure consistent data handling regardless of the underlying platform.
"""

from enum import StrEnum
from typing import Any


class PlatformType(StrEnum):
    """Supported messaging platforms in the Mimeia platform."""

    WHATSAPP = "whatsapp"
    TELEGRAM = "telegram"
    TEAMS = "teams"
    INSTAGRAM = "instagram"


class MessageType(StrEnum):
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
    EDIT = "edit"  # A user replaced the contents of an earlier message
    REVOKE = "revoke"  # A user removed an earlier message
    SHARE = "share"  # Shared post/Reel/story reference (Instagram)
    STORY_MENTION = "story_mention"  # User mentioned the account in their story
    UNSUPPORTED = "unsupported"  # Unsupported message types


class WebhookType(StrEnum):
    """Types of webhook events that platforms can send."""

    INCOMING_MESSAGES = "incoming_messages"
    STATUS_UPDATES = "status_updates"
    ERRORS = "errors"
    MEMBER_UPDATES = "member_updates"  # For group/channel management
    SYSTEM_EVENTS = "system_events"


class MessageStatus(StrEnum):
    """Universal message delivery status across platforms."""

    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    PLAYED = "played"
    FAILED = "failed"
    DELETED = "deleted"
    PENDING = "pending"


class InteractiveType(StrEnum):
    """Types of interactive elements across platforms."""

    BUTTON_REPLY = "button_reply"
    LIST_REPLY = "list_reply"
    CALL_PERMISSION_REPLY = "call_permission_reply"
    FLOW_REPLY = "nfm_reply"  # a completed WhatsApp Flow
    QUICK_REPLY = "quick_reply"
    INLINE_KEYBOARD = "inline_keyboard"  # Telegram inline keyboards
    CAROUSEL = "carousel"
    MENU = "menu"


class MediaType(StrEnum):
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


class ConversationType(StrEnum):
    """Types of conversations across platforms."""

    PRIVATE = "private"  # 1-on-1 conversation
    GROUP = "group"  # Group chat
    CHANNEL = "channel"  # Broadcast channel
    BUSINESS = "business"  # Business conversation (WhatsApp Business)


# Type aliases for complex types
PlatformData = dict[str, Any]
MessageMetadata = dict[str, Any]
UniversalMessageData = dict[str, Any]


class ErrorCode(StrEnum):
    """Universal error codes for webhook processing."""

    VALIDATION_ERROR = "validation_error"
    AUTHENTICATION_ERROR = "authentication_error"
    RATE_LIMIT_ERROR = "rate_limit_error"
    PLATFORM_ERROR = "platform_error"
    NETWORK_ERROR = "network_error"
    PROCESSING_ERROR = "processing_error"
    UNKNOWN_MESSAGE_TYPE = "unknown_message_type"
    SIGNATURE_VALIDATION_FAILED = "signature_validation_failed"
