"""
Core schema abstractions for the Mimeia AI Agent Platform.

This module provides platform-agnostic base classes and types that enable
unified processing across multiple messaging platforms (WhatsApp, Telegram, Teams, Instagram).
"""

# Universal webhook interfaces for platform-agnostic handling
from .base_message import BaseMessage, BaseTextMessage
from .base_status import BaseMessageStatus
from .base_webhook import BaseWebhook

# Core types and base classes
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
from .webhook_interfaces import (
    AdReferralBase,
    BusinessContextBase,
    ConversationBase,
    ErrorDetailBase,
    ErrorWebhook,
    ForwardContextBase,
    # Universal webhook types (note: outgoing webhooks are actually status updates)
    IncomingMessageWebhook,
    StatusWebhook,
    # Base components
    TenantBase,
    UniversalWebhook,
    UserBase,
)

# Legacy WebhookEventData and MessageEventData removed - use Universal Webhook Interface

__all__ = [
    # Universal webhook interfaces
    "IncomingMessageWebhook",
    "StatusWebhook",
    "ErrorWebhook",
    "UniversalWebhook",
    # Base components
    "TenantBase",
    "UserBase",
    "BusinessContextBase",
    "ForwardContextBase",
    "AdReferralBase",
    "ConversationBase",
    "ErrorDetailBase",
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
    # Legacy WebhookEventData and MessageEventData removed
]
