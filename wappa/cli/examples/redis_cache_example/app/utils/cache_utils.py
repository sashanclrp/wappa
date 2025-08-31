"""
Cache utility functions following Single Responsibility Principle.

This module provides cache-related helper functions used across
different score modules for consistent cache management.
"""

import re


def generate_cache_key(prefix: str, identifier: str, suffix: str | None = None) -> str:
    """
    Generate a standardized cache key.

    Args:
        prefix: Cache type prefix (e.g., 'user', 'state', 'msg_history')
        identifier: Unique identifier (e.g., user_id, session_id)
        suffix: Optional suffix for additional specificity

    Returns:
        Properly formatted cache key

    Examples:
        >>> generate_cache_key('user', '1234567890')
        'user:1234567890'
        >>> generate_cache_key('msg_history', '1234567890', 'recent')
        'msg_history:1234567890:recent'
    """
    if not prefix or not identifier:
        raise ValueError("Both prefix and identifier are required")

    # Sanitize inputs
    prefix = sanitize_cache_component(prefix)
    identifier = sanitize_cache_component(identifier)

    key = f"{prefix}:{identifier}"

    if suffix:
        suffix = sanitize_cache_component(suffix)
        key += f":{suffix}"

    return key


def sanitize_cache_component(component: str) -> str:
    """
    Sanitize a cache key component by removing invalid characters.

    Args:
        component: Component string to sanitize

    Returns:
        Sanitized component safe for cache keys
    """
    # Remove spaces and special characters, keep alphanumeric, underscore, hyphen
    sanitized = re.sub(r"[^\w\-]", "_", str(component).strip())

    # Remove multiple consecutive underscores
    sanitized = re.sub(r"_+", "_", sanitized)

    # Remove leading/trailing underscores
    return sanitized.strip("_")


def get_cache_ttl(cache_type: str) -> int:
    """
    Get standard TTL (time-to-live) values for different cache types.

    Args:
        cache_type: Type of cache ('user', 'state', 'message', 'statistics')

    Returns:
        TTL in seconds

    Raises:
        ValueError: If cache_type is not recognized
    """
    ttl_mapping = {
        "user": 86400,  # 24 hours - User profiles
        "state": 3600,  # 1 hour - Command states
        "message": 604800,  # 7 days - Message history
        "statistics": 3600,  # 1 hour - Cache statistics
        "temporary": 600,  # 10 minutes - Temporary data
    }

    if cache_type not in ttl_mapping:
        raise ValueError(
            f"Unknown cache_type: {cache_type}. Valid types: {list(ttl_mapping.keys())}"
        )

    return ttl_mapping[cache_type]


def validate_cache_key(key: str) -> bool:
    """
    Validate if a cache key follows the expected format.

    Args:
        key: Cache key to validate

    Returns:
        True if valid, False otherwise
    """
    if not key or not isinstance(key, str):
        return False

    # Basic format check: should contain at least one colon
    if ":" not in key:
        return False

    # Check for invalid characters (spaces, special chars except : _ -)
    if re.search(r"[^\w:\-]", key):
        return False

    # Should not start or end with colon
    if key.startswith(":") or key.endswith(":"):
        return False

    # Should not have consecutive colons
    return "::" not in key


def create_user_profile_key(user_id: str) -> str:
    """Create standardized user profile cache key."""
    return generate_cache_key("user", user_id, "profile")


def create_message_history_key(user_id: str) -> str:
    """Create standardized message history cache key."""
    return generate_cache_key("msg_history", user_id)


def create_state_key(user_id: str, state_type: str = "wappa") -> str:
    """Create standardized state cache key."""
    return generate_cache_key("state", user_id, state_type)


def create_statistics_key(scope: str = "global") -> str:
    """Create standardized cache statistics key."""
    return generate_cache_key("stats", scope)


def format_cache_error(operation: str, key: str, error: Exception) -> str:
    """
    Format cache operation error messages consistently.

    Args:
        operation: Cache operation ('get', 'set', 'delete')
        key: Cache key that failed
        error: Exception that occurred

    Returns:
        Formatted error message
    """
    return f"Cache {operation} failed for key '{key}': {str(error)}"


def log_cache_operation(
    logger, operation: str, key: str, success: bool, duration_ms: float | None = None
) -> None:
    """
    Log cache operations consistently across score modules.

    Args:
        logger: Logger instance
        operation: Cache operation performed
        key: Cache key used
        success: Whether operation succeeded
        duration_ms: Optional operation duration in milliseconds
    """
    status = "✅" if success else "❌"
    duration_str = f" ({duration_ms:.1f}ms)" if duration_ms else ""

    logger.debug(f"{status} Cache {operation}: {key}{duration_str}")
