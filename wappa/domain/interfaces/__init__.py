"""
Domain interfaces.

Defines the contracts that infrastructure layer must implement.
"""

from .base_repository import IBaseRepository
from .cache_factory import ICacheFactory
from .cache_interface import ICache
from .expiry_repository import IExpiryRepository
from .media_interface import IMediaHandler
from .messaging_interface import IMessenger
from .pubsub_repository import IPubSubRepository
from .repository_factory import IRepositoryFactory
from .shared_state_repository import ISharedStateRepository
from .state_repository import IStateRepository
from .user_repository import IUserRepository

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
    # Cache interfaces
    "ICache",
    "ICacheFactory",
]
