"""
Core type definitions for Wappa framework.

This module contains common type definitions used throughout the Wappa framework.
"""

from enum import Enum
from typing import Literal


class CacheType(Enum):
    """
    Supported cache types for Wappa applications.

    This enum defines the cache backends that Wappa can use for state management,
    user data caching, and message logging.
    """

    MEMORY = "memory"
    """In-memory caching (default) - Fast but not persistent across restarts."""

    REDIS = "redis"
    """Redis-based caching - Persistent and scalable, requires Redis server."""

    JSON = "json"
    """JSON file-based caching - Persistent but single-process only."""


# Type alias for user-friendly type hints
CacheTypeOptions = Literal["memory", "redis", "json"]
"""
Type alias for cache type options that provides IDE autocompletion.

Use this in function parameters and class constructors where users specify
cache types as strings.

Example:
    def __init__(self, cache: CacheTypeOptions = "memory"):
        pass
"""


def validate_cache_type(cache_type: str) -> CacheType:
    """
    Validate and convert a cache type string to CacheType enum.

    Args:
        cache_type: String representation of cache type

    Returns:
        Validated CacheType enum value

    Raises:
        ValueError: If cache_type is not supported

    Example:
        >>> validate_cache_type("redis")
        CacheType.REDIS

        >>> validate_cache_type("invalid")
        ValueError: Unsupported cache type: invalid. Supported types: memory, redis, json
    """
    try:
        return CacheType(cache_type.lower())
    except ValueError as e:
        supported_types = [ct.value for ct in CacheType]
        raise ValueError(
            f"Unsupported cache type: {cache_type}. "
            f"Supported types: {', '.join(supported_types)}"
        ) from e


def get_supported_cache_types() -> list[str]:
    """
    Get list of all supported cache type strings.

    Returns:
        List of supported cache type strings

    Example:
        >>> get_supported_cache_types()
        ['memory', 'redis', 'json']
    """
    return [ct.value for ct in CacheType]


def is_cache_type_supported(cache_type: str) -> bool:
    """
    Check if a cache type string is supported.

    Args:
        cache_type: String to check

    Returns:
        True if cache type is supported, False otherwise

    Example:
        >>> is_cache_type_supported("redis")
        True

        >>> is_cache_type_supported("invalid")
        False
    """
    try:
        validate_cache_type(cache_type)
        return True
    except ValueError:
        return False
