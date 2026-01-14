"""
Redis cache factory implementation for Wappa framework.

Creates Redis-backed cache instances using the existing Redis handler infrastructure
with handlers implementing type-specific interfaces directly.
"""

from ...domain.interfaces.cache_factory import ICacheFactory
from ...domain.interfaces.cache_interfaces import (
    IAIStateCache,
    IExpiryCache,
    IStateCache,
    ITableCache,
    IUserCache,
)
from .redis_handler.ai_state import RedisAIState
from .redis_handler.expiry import RedisExpiry
from .redis_handler.state_handler import RedisStateHandler
from .redis_handler.table import RedisTable
from .redis_handler.user import RedisUser


class RedisCacheFactory(ICacheFactory):
    """
    Factory for creating Redis-backed cache instances with hybrid pattern support.

    Uses the existing Redis handler infrastructure with proper pool assignments:
    - State cache: Uses state_handler pool (db1)
    - User cache: Uses users pool (db0)
    - Table cache: Uses table pool (db2)
    - Expiry cache: Uses expiry pool (db3)
    - AI State cache: Uses ai_state pool (db4)

    All instances implement the type-specific cache interfaces directly.

    HYBRID PATTERN: Context (tenant_id, user_id) can be:
    1. Used from defaults set at construction (most common - webhook flow)
    2. Overridden per-call (for API events with different user context)

    Example:
        # Webhook flow - uses default context
        user_cache = factory.create_user_cache()

        # API flow - override user_id with recipient
        user_cache = factory.create_user_cache(user_id=event.recipient)
    """

    def create_state_cache(
        self,
        tenant_id: str | None = None,
        user_id: str | None = None,
    ) -> IStateCache:
        """
        Create Redis state cache instance.

        Args:
            tenant_id: Optional override (uses default if None)
            user_id: Optional override (uses default if None)

        Returns:
            RedisStateHandler implementing IStateCache configured for state_handler pool
        """
        effective_tenant, effective_user = self._resolve_context(tenant_id, user_id)
        return RedisStateHandler(
            tenant=effective_tenant, user_id=effective_user, redis_alias="state_handler"
        )

    def create_user_cache(
        self,
        tenant_id: str | None = None,
        user_id: str | None = None,
    ) -> IUserCache:
        """
        Create Redis user cache instance.

        Args:
            tenant_id: Optional override (uses default if None)
            user_id: Optional override (uses default if None)

        Returns:
            RedisUser implementing IUserCache configured for users pool
        """
        effective_tenant, effective_user = self._resolve_context(tenant_id, user_id)
        return RedisUser(
            tenant=effective_tenant, user_id=effective_user, redis_alias="users"
        )

    def create_table_cache(
        self,
        tenant_id: str | None = None,
    ) -> ITableCache:
        """
        Create Redis table cache instance.

        Args:
            tenant_id: Optional override (uses default if None)

        Returns:
            RedisTable implementing ITableCache configured for table pool
        """
        effective_tenant, _ = self._resolve_context(tenant_id, None)
        return RedisTable(tenant=effective_tenant, redis_alias="table")

    def create_expiry_cache(
        self,
        tenant_id: str | None = None,
        user_id: str | None = None,
    ) -> IExpiryCache:
        """
        Create Redis expiry trigger cache instance.

        Args:
            tenant_id: Optional override (uses default if None)
            user_id: Optional override (uses default if None)

        Returns:
            RedisExpiry implementing IExpiryCache configured for expiry pool

        Example:
            # Default context
            expiry_cache = factory.create_expiry_cache()
            await expiry_cache.set("payment_reminder", "TXN_123", 1800)

            # Override for specific user
            expiry_cache = factory.create_expiry_cache(user_id=recipient_id)
        """
        effective_tenant, effective_user = self._resolve_context(tenant_id, user_id)
        return RedisExpiry(
            tenant=effective_tenant, user_id=effective_user, redis_alias="expiry"
        )

    def create_ai_state_cache(
        self,
        tenant_id: str | None = None,
        user_id: str | None = None,
    ) -> IAIStateCache:
        """
        Create Redis AI state cache instance.

        Args:
            tenant_id: Optional override (uses default if None)
            user_id: Optional override (uses default if None)

        Returns:
            RedisAIState implementing IAIStateCache configured for ai_state pool

        Example:
            # Default context
            ai_state = factory.create_ai_state_cache()
            await ai_state.upsert("summarizer", {"context": "meeting notes"})

            # Override for specific user
            ai_state = factory.create_ai_state_cache(user_id=recipient_id)
        """
        effective_tenant, effective_user = self._resolve_context(tenant_id, user_id)
        return RedisAIState(
            tenant=effective_tenant, user_id=effective_user, redis_alias="ai_state"
        )
