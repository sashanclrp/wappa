"""
Universal Webhook Interface system for platform-agnostic webhook handling.

This module provides universal webhook interfaces that all messaging platforms
must adapt to, using WhatsApp as the comprehensive template. The system uses
5 universal webhook types that work across all platforms:

1. InboundMessageWebhook - All incoming messages from users
2. CallWebhook - Connected, terminated, and call-status events
3. StatusWebhook - Message delivery status updates (includes "outgoing" status)
4. ErrorWebhook - System, app, and account-level errors
5. SystemWebhook - Platform-level account/identity events
6. CustomWebhook - App-registered custom event payload envelope

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
    InboxBase,
    SystemEventDetail,
    UserBase,
)
from .universal_webhooks import (
    CallWebhook,
    CustomWebhook,
    ErrorWebhook,
    InboundMessageWebhook,
    StatusWebhook,
    SystemEventType,
    SystemWebhook,
    UniversalWebhook,
    WhatsAppIncomingWebhookData,
)

__all__ = [
    # Base components
    "InboxBase",
    "UserBase",
    "BusinessContextBase",
    "ForwardContextBase",
    "AdReferralBase",
    "ConversationBase",
    "ErrorDetailBase",
    "SystemEventDetail",
    # Universal webhook interfaces
    "InboundMessageWebhook",
    "CallWebhook",
    "WhatsAppIncomingWebhookData",
    "StatusWebhook",
    "ErrorWebhook",
    "SystemWebhook",
    "SystemEventType",
    "CustomWebhook",
    "UniversalWebhook",
]
