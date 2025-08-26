"""
Universal Webhook Interface system for platform-agnostic webhook handling.

This module provides universal webhook interfaces that all messaging platforms
must adapt to, using WhatsApp as the comprehensive template. The system uses
3 universal webhook types that work across all platforms:

1. IncomingMessageWebhook - All incoming messages from users
2. StatusWebhook - Message delivery status updates (includes "outgoing" status)
3. ErrorWebhook - System, app, and account-level errors

Note: "Outgoing message" webhooks are actually status updates that use StatusWebhook.

All platforms (WhatsApp, Teams, Telegram, Instagram) must transform their
platform-specific webhooks into these universal interfaces via processor adapters.
"""

from .base_components import (
    AdReferralBase,
    BusinessContextBase,
    ConversationBase,
    ErrorDetailBase,
    ForwardContextBase,
    TenantBase,
    UserBase,
)
from .universal_webhooks import (
    ErrorWebhook,
    IncomingMessageWebhook,
    StatusWebhook,
    UniversalWebhook,
)

__all__ = [
    # Base components
    "TenantBase",
    "UserBase",
    "BusinessContextBase",
    "ForwardContextBase",
    "AdReferralBase",
    "ConversationBase",
    "ErrorDetailBase",
    # Universal webhook interfaces
    "IncomingMessageWebhook",
    "StatusWebhook",
    "ErrorWebhook",
    "UniversalWebhook",
]
