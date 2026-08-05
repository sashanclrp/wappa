"""
Wappa Persistence Layer

Provides access to cache factories and storage implementations for different
persistence backends including Redis, JSON file, and in-memory storage.

Infrastructure layer with one cache contract family across all backends.

Usage (User Request: Quick access to create_cache_factory):
    # Cache factory (main request)
    from wappa.persistence import create_cache_factory, get_cache_factory

    # Cache interfaces
    from wappa.persistence import ICacheFactory, ITableCache

    # Specific implementations
    from wappa.persistence.redis import RedisCacheFactory, RedisClient
    from wappa.persistence.json import JSONCacheFactory
    from wappa.persistence.memory import MemoryCacheFactory
"""

# Cache Factory Functions (User Request: Quick access to create_cache_factory)
# Cache Interfaces
from ..domain.interfaces.cache_factory import ICacheFactory
from ..domain.interfaces.cache_interfaces import (
    IExpiryCache,
    IStateCache,
    ITableCache,
    IUserCache,
    TableRowTransition,
    TableTransitionResult,
)
from .cache_factory import create_cache_factory, get_cache_factory
from .cache_space import build_table_name

# Redis implementation re-exports
from .redis import RedisClient
from .redis import ops as redis_ops
from .redis.redis_cache_factory import RedisCacheFactory
from .typed_table_cache import TypedRowTransition, TypedTableCache
from .versioned_table_cache import VersionedTableCache

__all__ = [
    # Cache Factory Functions (User Request: Main access point)
    "create_cache_factory",
    "get_cache_factory",
    # Cache key composition
    "build_table_name",
    # Core Interfaces
    "ICacheFactory",
    "IUserCache",
    "IStateCache",
    "IExpiryCache",
    "ITableCache",
    "TypedTableCache",
    "VersionedTableCache",
    # Atomic row transitions
    "TableRowTransition",
    "TableTransitionResult",
    "TypedRowTransition",
    # Redis implementations
    "RedisCacheFactory",
    "RedisClient",
    "redis_ops",
]
