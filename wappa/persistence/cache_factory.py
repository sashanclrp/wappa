"""
Main cache factory selector for Wappa framework.

Provides factory selector based on cache type configuration.
"""

from ..domain.interfaces.cache_factory import ICacheFactory


def create_cache_factory(cache_type: str) -> ICacheFactory:
    """
    Create cache factory instance based on cache type.

    Args:
        cache_type: Type of cache to create ("redis", "json", "memory")

    Returns:
        Cache factory instance for the specified type

    Raises:
        ValueError: If cache_type is not supported
        ImportError: If required dependencies are not available
    """
    if cache_type == "redis":
        try:
            from .redis.redis_cache_factory import RedisCacheFactory

            return RedisCacheFactory()
        except ImportError as e:
            raise ImportError(
                f"Redis dependencies not available for cache_type='redis': {e}"
            ) from e

    elif cache_type == "json":
        # TODO: Implement JSON cache factory
        raise NotImplementedError(
            "JSON cache factory not yet implemented. "
            "Use cache_type='memory' or cache_type='redis'"
        )

    elif cache_type == "memory":
        # TODO: Implement memory cache factory
        raise NotImplementedError(
            "Memory cache factory not yet implemented. Use cache_type='redis' for now"
        )

    else:
        raise ValueError(
            f"Unsupported cache_type: {cache_type}. "
            f"Supported types: 'redis', 'json', 'memory'"
        )


# Convenience function for getting cache factory with validation
def get_cache_factory(
    cache_type: str, *, validate_redis_url: bool = True
) -> ICacheFactory:
    """
    Get cache factory with validation.

    Args:
        cache_type: Type of cache to create
        validate_redis_url: Whether to validate Redis URL for redis cache type

    Returns:
        Configured cache factory instance

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
