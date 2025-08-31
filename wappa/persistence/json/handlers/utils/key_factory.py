"""
Key factory for JSON cache using Redis patterns.

Reuses the existing KeyFactory from Redis to maintain consistency
across all cache implementations.
"""

from ....redis.redis_handler.utils.key_factory import KeyFactory, default_key_factory

# Export the same key factory used by Redis for consistency
__all__ = ["KeyFactory", "default_key_factory"]
