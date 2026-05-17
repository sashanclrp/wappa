"""
Domain interfaces.

Defines the contracts that infrastructure layer must implement.
"""

from .base_repository import IBaseRepository
from .cache_factory import ICacheFactory
from .cache_interfaces import IStateCache, ITableCache, IUserCache
from .expiry_repository import IExpiryRepository
from .identity_resolver import IIdentityResolver, PassthroughIdentityResolver
from .media_interface import IMediaHandler
from .messaging_interface import IMessenger
from .pubsub_interface import IPubSubPublisher, PubSubEventType
from .pubsub_repository import IPubSubRepository
from .repository_factory import IRepositoryFactory
from .shared_state_repository import ISharedStateRepository
from .state_repository import IStateRepository
from .user_repository import IUserRepository
from .webhook_processor import IWebhookProcessor

__all__ = [
    "IBaseRepository",
    "IUserRepository",
    "IStateRepository",
    "ISharedStateRepository",
    "IExpiryRepository",
    "IPubSubRepository",
    "IRepositoryFactory",
    "IMessenger",
    "IMediaHandler",
    # Identity resolution
    "IIdentityResolver",
    "PassthroughIdentityResolver",
    # Cache interfaces (type-specific)
    "IUserCache",
    "IStateCache",
    "ITableCache",
    "ICacheFactory",
    # PubSub interface
    "IPubSubPublisher",
    "PubSubEventType",
    # External webhook processor
    "IWebhookProcessor",
]
