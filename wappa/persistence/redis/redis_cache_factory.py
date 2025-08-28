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

    Context (tenant_id, user_id) is injected at construction time, eliminating
    manual parameter passing.
    """

    def __init__(self, tenant_id: str, user_id: str):
        """Initialize Redis cache factory with context injection."""
        super().__init__(tenant_id, user_id)

    def create_state_cache(self) -> ICache:
        """
        Create Redis state cache instance.

        Uses context (tenant_id, user_id) injected at construction time.

        Returns:
            ICache adapter wrapping RedisStateHandler configured for state_handler pool
        """
        return RedisStateCacheAdapter(
            tenant_id=self.tenant_id, user_id=self.user_id, redis_alias="state_handler"
        )

    def create_user_cache(self) -> ICache:
        """
        Create Redis user cache instance.

        Uses context (tenant_id, user_id) injected at construction time.

        Returns:
            ICache adapter wrapping RedisUser configured for users pool
        """
        return RedisUserCacheAdapter(
            tenant_id=self.tenant_id, user_id=self.user_id, redis_alias="users"
        )

    def create_table_cache(self) -> ICache:
        """
        Create Redis table cache instance.

        Uses context (tenant_id) injected at construction time.

        Returns:
            ICache adapter wrapping RedisTable configured for table pool
        """
        return RedisTableCacheAdapter(tenant_id=self.tenant_id, redis_alias="table")
