"""
Redis cache factory implementation for Wappa framework.

Creates Redis-backed cache instances using the existing Redis handler infrastructure
with ICache adapters for uniform interface.
"""

from ...domain.interfaces.cache_factory import ICacheFactory
from ...domain.interfaces.cache_interface import ICache
from .cache_adapters import (
    RedisStateCacheAdapter,
    RedisTableCacheAdapter,
    RedisUserCacheAdapter,
)


class RedisCacheFactory(ICacheFactory):
    """
    Factory for creating Redis-backed cache instances.

    Uses the existing Redis handler infrastructure with proper pool assignments:
    - State cache: Uses state_handler pool (db1)
    - User cache: Uses users pool (db0)
    - Table cache: Uses table pool (db2)

    All instances implement the ICache interface through adapters.
    """

    def create_state_cache(self, tenant_id: str, user_id: str) -> ICache:
        """
        Create Redis state cache instance.

        Args:
            tenant_id: Tenant identifier for namespace isolation
            user_id: User identifier for user-specific state

        Returns:
            ICache adapter wrapping RedisStateHandler configured for state_handler pool
        """
        return RedisStateCacheAdapter(
            tenant_id=tenant_id, user_id=user_id, redis_alias="state_handler"
        )

    def create_user_cache(self, tenant_id: str, user_id: str) -> ICache:
        """
        Create Redis user cache instance.

        Args:
            tenant_id: Tenant identifier for namespace isolation
            user_id: User identifier for user-specific data

        Returns:
            ICache adapter wrapping RedisUser configured for users pool
        """
        return RedisUserCacheAdapter(
            tenant_id=tenant_id, user_id=user_id, redis_alias="users"
        )

    def create_table_cache(self, tenant_id: str) -> ICache:
        """
        Create Redis table cache instance.

        Args:
            tenant_id: Tenant identifier for namespace isolation

        Returns:
            ICache adapter wrapping RedisTable configured for table pool
        """
        return RedisTableCacheAdapter(tenant_id=tenant_id, redis_alias="table")
