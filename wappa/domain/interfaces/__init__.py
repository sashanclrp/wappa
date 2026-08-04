"""
Domain interfaces.

Defines the contracts that infrastructure layer must implement.
"""

from .cache_factory import ICacheFactory
from .cache_interfaces import IExpiryCache, IStateCache, ITableCache, IUserCache
from .identity_resolver import IIdentityResolver, PassthroughIdentityResolver
from .inbox_credential_store import (
    IInboxCredentialStore,
    InboxCredentials,
    InboxNotFoundError,
)
from .media_interface import IMediaHandler
from .messaging_interface import IMessenger
from .pubsub_interface import IPubSubPublisher, PubSubEventType
from .session_provider import (
    HTTPSessionClosedError,
    RuntimeDrainingError,
    validate_session,
)
from .webhook_processor import IWebhookProcessor

__all__ = [
    "IMessenger",
    "IMediaHandler",
    # Identity resolution
    "IIdentityResolver",
    "PassthroughIdentityResolver",
    # Inbox credentials
    "IInboxCredentialStore",
    "InboxCredentials",
    "InboxNotFoundError",
    # Cache interfaces (type-specific - preferred)
    "IExpiryCache",
    "IUserCache",
    "IStateCache",
    "ITableCache",
    "ICacheFactory",
    # PubSub interface
    "IPubSubPublisher",
    "PubSubEventType",
    # External webhook processor
    "IWebhookProcessor",
    # HTTP session lifecycle
    "HTTPSessionClosedError",
    "RuntimeDrainingError",
    "validate_session",
]
