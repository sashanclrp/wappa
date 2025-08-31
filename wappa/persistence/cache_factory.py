"""
Main cache factory selector for Wappa framework.

Provides factory selector based on cache type configuration.
"""

from ..domain.interfaces.cache_factory import ICacheFactory


def create_cache_factory(cache_type: str) -> type[ICacheFactory]:
    """
    Create cache factory class based on cache type.

    Returns factory classes that can be instantiated with context parameters.
    This supports the new context-aware cache factory pattern where context
    (tenant_id, user_id) is injected at construction time.

    Args:
        cache_type: Type of cache to create ("redis", "json", "memory")

    Returns:
        Cache factory class for the specified type

    Raises:
        ValueError: If cache_type is not supported
        ImportError: If required dependencies are not available
    """
    if cache_type == "redis":
        try:
            from .redis.redis_cache_factory import RedisCacheFactory

            return RedisCacheFactory
        except ImportError as e:
            raise ImportError(
                f"Redis dependencies not available for cache_type='redis': {e}"
            ) from e

    elif cache_type == "json":
        try:
            from .json.json_cache_factory import JSONCacheFactory

            return JSONCacheFactory
        except ImportError as e:
            raise ImportError(
                f"JSON cache dependencies not available for cache_type='json': {e}"
            ) from e

    elif cache_type == "memory":
        try:
            from .memory.memory_cache_factory import MemoryCacheFactory

            return MemoryCacheFactory
        except ImportError as e:
            raise ImportError(
                f"Memory cache dependencies not available for cache_type='memory': {e}"
            ) from e

    else:
        raise ValueError(
            f"Unsupported cache_type: {cache_type}. "
            f"Supported types: 'redis', 'json', 'memory'"
        )


# Convenience function for getting cache factory with validation
def get_cache_factory(
    cache_type: str, *, validate_redis_url: bool = True
) -> type[ICacheFactory]:
    """
    Get cache factory class with validation.

    Args:
        cache_type: Type of cache to create
        validate_redis_url: Whether to validate Redis URL for redis cache type

    Returns:
        Configured cache factory class

    Raises:
        ValueError: If configuration is invalid
        ImportError: If required dependencies are not available
    """
    if cache_type == "redis" and validate_redis_url:
        from ..core.config.settings import settings

        if not settings.has_redis:
            raise ValueError(
                "Redis URL not configured. Set REDIS_URL environment variable "
                "or use a different cache_type"
            )

    return create_cache_factory(cache_type)
