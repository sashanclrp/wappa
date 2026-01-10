"""
Redis cache factory implementation for Wappa framework.

Creates Redis-backed cache instances using the existing Redis handler infrastructure
with handlers implementing type-specific interfaces directly.
"""

from ...domain.interfaces.cache_factory import ICacheFactory
from ...domain.interfaces.cache_interfaces import IStateCache, ITableCache, IUserCache
from .redis_handler.state_handler import RedisStateHandler
from .redis_handler.table import RedisTable
from .redis_handler.user import RedisUser


class RedisCacheFactory(ICacheFactory):
    """
    Factory for creating Redis-backed cache instances.

    Uses the existing Redis handler infrastructure with proper pool assignments:
    - State cache: Uses state_handler pool (db1)
    - User cache: Uses users pool (db0)
    - Table cache: Uses table pool (db2)

    All instances implement the type-specific cache interfaces directly.

    Context (tenant_id, user_id) is injected at construction time, eliminating
    manual parameter passing.
    """

    def __init__(self, tenant_id: str, user_id: str):
        """Initialize Redis cache factory with context injection."""
        super().__init__(tenant_id, user_id)

    def create_state_cache(self) -> IStateCache:
        """
        Create Redis state cache instance.

        Uses context (tenant_id, user_id) injected at construction time.

        Returns:
            RedisStateHandler implementing IStateCache configured for state_handler pool
        """
        return RedisStateHandler(
            tenant=self.tenant_id, user_id=self.user_id, redis_alias="state_handler"
        )

    def create_user_cache(self) -> IUserCache:
        """
        Create Redis user cache instance.

        Uses context (tenant_id, user_id) injected at construction time.

        Returns:
            RedisUser implementing IUserCache configured for users pool
        """
        return RedisUser(
            tenant=self.tenant_id, user_id=self.user_id, redis_alias="users"
        )

    def create_table_cache(self) -> ITableCache:
        """
        Create Redis table cache instance.

        Uses context (tenant_id) injected at construction time.

        Returns:
            RedisTable implementing ITableCache configured for table pool
        """
        return RedisTable(tenant=self.tenant_id, redis_alias="table")
