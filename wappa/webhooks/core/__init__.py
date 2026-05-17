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
    CustomWebhook,
    ErrorDetailBase,
    ErrorWebhook,
    ForwardContextBase,
    InboundMessageWebhook,
    InboxBase,
    StatusWebhook,
    SystemEventType,
    SystemWebhook,
    UniversalWebhook,
    UserBase,
)

__all__ = [
    "InboundMessageWebhook",
    "StatusWebhook",
    "ErrorWebhook",
    "SystemWebhook",
    "SystemEventType",
    "CustomWebhook",
    "UniversalWebhook",
    "InboxBase",
    "UserBase",
    "BusinessContextBase",
    "ForwardContextBase",
    "AdReferralBase",
    "ConversationBase",
    "ErrorDetailBase",
    "PlatformType",
    "MessageType",
    "MessageStatus",
    "WebhookType",
    "InteractiveType",
    "MediaType",
    "ConversationType",
    "ErrorCode",
    "BaseMessage",
    "BaseTextMessage",
    "BaseWebhook",
    "BaseMessageStatus",
]
