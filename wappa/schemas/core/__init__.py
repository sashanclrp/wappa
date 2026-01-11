"""
Core schema abstractions for the Mimeia AI Agent Platform.

This module provides platform-agnostic base classes and types that enable
unified processing across multiple messaging platforms (WhatsApp, Telegram, Teams, Instagram).

Note: Universal webhook interfaces (UserBase, StatusWebhook, etc.) have been moved to
wappa.webhooks.core.webhook_interfaces for better organization and BSUID support.
"""

# Platform-agnostic base classes
from .base_message import BaseMessage, BaseTextMessage
from .base_status import BaseMessageStatus
from .base_webhook import BaseWebhook

# Core types
from .types import (
    ConversationType,
    ErrorCode,
    InteractiveType,
    MediaType,
    MessageStatus,
    MessageType,
    PlatformType,
    WebhookType,
)

__all__ = [
    # Core types
    "PlatformType",
    "MessageType",
    "MessageStatus",
    "WebhookType",
    "InteractiveType",
    "MediaType",
    "ConversationType",
    "ErrorCode",
    # Base classes
    "BaseMessage",
    "BaseTextMessage",
    "BaseWebhook",
    "BaseMessageStatus",
]
