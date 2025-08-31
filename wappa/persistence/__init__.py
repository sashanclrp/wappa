"""
Wappa Persistence Layer

Provides access to cache factories and storage implementations for different
persistence backends including Redis, JSON file, and in-memory storage.

Clean Architecture: Infrastructure layer with cache and repository abstractions.

Usage (User Request: Quick access to create_cache_factory):
    # Cache factory (main request)
    from wappa.persistence import create_cache_factory, get_cache_factory

    # Cache interfaces
    from wappa.persistence import ICacheFactory, IStateRepository

    # Specific implementations
    from wappa.persistence.redis import RedisCacheFactory, RedisClient
    from wappa.persistence.json import JSONCacheFactory
    from wappa.persistence.memory import MemoryCacheFactory
"""

# Cache Factory Functions (User Request: Quick access to create_cache_factory)
# Cache Interfaces
from ..domain.interfaces.cache_factory import ICacheFactory
from ..domain.interfaces.cache_interface import ICache
from ..domain.interfaces.expiry_repository import IExpiryRepository
from ..domain.interfaces.pubsub_repository import IPubSubRepository

# Repository Factory Interface
from ..domain.interfaces.repository_factory import IRepositoryFactory
from ..domain.interfaces.shared_state_repository import ISharedStateRepository
from ..domain.interfaces.state_repository import IStateRepository
from ..domain.interfaces.tables_repository import ITablesRepository
from ..domain.interfaces.user_repository import IUserRepository
from .cache_factory import create_cache_factory, get_cache_factory

__all__ = [
    # Cache Factory Functions (User Request: Main access point)
    "create_cache_factory",
    "get_cache_factory",
    # Core Interfaces
    "ICacheFactory",
    "ICache",
    "IRepositoryFactory",
    # Repository Interfaces
    "IStateRepository",
    "IUserRepository",
    "ITablesRepository",
    "IPubSubRepository",
    "IExpiryRepository",
    "ISharedStateRepository",
]
