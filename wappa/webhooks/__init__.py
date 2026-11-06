"""
Wappa Webhook Schemas and Universal Interfaces

Provides a stable import surface for the universal webhook models. Each
Platform's own schemas import from its adapter package
(``wappa.webhooks.whatsapp``, ``wappa.webhooks.instagram``).

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
from .core.webhook_interfaces.base_components import (
    ContactSync,
    GroupParticipant,
    GroupUpdate,
    InboxBase,
    SystemEventDetail,
    UserAction,
)
from .core.webhook_interfaces.conversation_webhooks import (
    CommentAuthor,
    CommentSource,
    EchoOrigin,
    EntryPointKind,
    EntryReferral,
    HistoryDirection,
    HistoryMessage,
    HistorySyncWebhook,
    HistoryThread,
    InboxConnectionState,
    InboxConnectionWebhook,
    IncomingCommentWebhook,
    MentionSubject,
    MentionWebhook,
    MessageUpdateKind,
    MessageUpdateWebhook,
    OutboundEchoWebhook,
)
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

__all__ = [
    "UniversalWebhook",
    "CommentAuthor",
    "CommentSource",
    "EntryPointKind",
    "EntryReferral",
    "IncomingCommentWebhook",
    "MentionSubject",
    "MentionWebhook",
    "EchoOrigin",
    "HistoryDirection",
    "HistoryMessage",
    "HistorySyncWebhook",
    "HistoryThread",
    "InboxConnectionState",
    "InboxConnectionWebhook",
    "ContactSync",
    "GroupParticipant",
    "GroupUpdate",
    "UserAction",
    "OutboundEchoWebhook",
    "MessageUpdateKind",
    "MessageUpdateWebhook",
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
    # Base message and webhook components
    "BaseMessage",
    "InboxBase",
    "SystemEventDetail",
]
