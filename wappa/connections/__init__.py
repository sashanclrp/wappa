"""Inbox Connectors: connect Platform accounts as Wappa Inboxes (ADR-0017).

``IInboxConnector`` is the one contract; ``WhatsAppConnector`` (Embedded
Signup) and ``InstagramConnector`` (Unified Login) implement it on the shared
Meta Business Login core. Hosts compose them into their own authenticated
routes and transactions.
"""

from .contract import (
    ActivationResult,
    AuthorizationRequest,
    ConnectionCancelledError,
    ConnectionGrant,
    ConnectionIntent,
    ConnectionProviderError,
    ConnectionStateError,
    DiscoveredInbox,
    IConnectionIntentStore,
    IInboxConnector,
    InboxConnectionError,
    InboxReadiness,
    InMemoryConnectionIntentStore,
)
from .instagram import (
    InstagramConnector,
    InstagramSubscriptions,
    deauthorization_event,
)
from .meta_login import MetaLoginConfig, parse_signed_request
from .whatsapp import WhatsAppConnector

__all__ = [
    "deauthorization_event",
    "ActivationResult",
    "AuthorizationRequest",
    "ConnectionCancelledError",
    "ConnectionGrant",
    "ConnectionIntent",
    "ConnectionProviderError",
    "ConnectionStateError",
    "DiscoveredInbox",
    "IConnectionIntentStore",
    "IInboxConnector",
    "InMemoryConnectionIntentStore",
    "InboxConnectionError",
    "InboxReadiness",
    "InstagramConnector",
    "InstagramSubscriptions",
    "MetaLoginConfig",
    "WhatsAppConnector",
    "parse_signed_request",
]
