"""
Memory cache factory implementation for Wappa framework.

Creates memory-backed cache instances using in-memory storage
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
from .handlers.ai_state import MemoryAIState
from .handlers.state_handler import MemoryStateHandler
from .handlers.table_handler import MemoryTable
from .handlers.user_handler import MemoryUser


class MemoryCacheFactory(ICacheFactory):
    """
    Factory for creating memory-backed cache instances with hybrid pattern support.

    Uses thread-safe in-memory storage with TTL support:
    - State cache: Uses states namespace with automatic TTL cleanup
    - User cache: Uses users namespace with context isolation
    - Table cache: Uses tables namespace with tenant isolation
    - AI State cache: Uses ai_states namespace with automatic TTL cleanup

    All instances implement the type-specific cache interfaces directly.

    HYBRID PATTERN: Context (tenant_id, user_id) can be:
    1. Used from defaults set at construction (most common - webhook flow)
    2. Overridden per-call (for API events with different user context)

    Cache data is stored in memory with automatic background cleanup of expired entries.
    """

    def create_state_cache(
        self,
        tenant_id: str | None = None,
        user_id: str | None = None,
    ) -> IStateCache:
        """
        Create Memory state cache instance.

        Args:
            tenant_id: Optional override (uses default if None)
            user_id: Optional override (uses default if None)

        Returns:
            MemoryStateHandler implementing IStateCache
        """
        effective_tenant, effective_user = self._resolve_context(tenant_id, user_id)
        return MemoryStateHandler(tenant=effective_tenant, user_id=effective_user)

    def create_user_cache(
        self,
        tenant_id: str | None = None,
        user_id: str | None = None,
    ) -> IUserCache:
        """
        Create Memory user cache instance.

        Args:
            tenant_id: Optional override (uses default if None)
            user_id: Optional override (uses default if None)

        Returns:
            MemoryUser implementing IUserCache
        """
        effective_tenant, effective_user = self._resolve_context(tenant_id, user_id)
        return MemoryUser(tenant=effective_tenant, user_id=effective_user)

    def create_table_cache(
        self,
        tenant_id: str | None = None,
    ) -> ITableCache:
        """
        Create Memory table cache instance.

        Args:
            tenant_id: Optional override (uses default if None)

        Returns:
            MemoryTable implementing ITableCache
        """
        effective_tenant, _ = self._resolve_context(tenant_id, None)
        return MemoryTable(tenant=effective_tenant)

    def create_expiry_cache(
        self,
        tenant_id: str | None = None,
        user_id: str | None = None,
    ) -> IExpiryCache:
        """
        Create Memory expiry cache instance.

        NOTE: Memory backend does not support expiry trigger functionality.
        Use Redis backend for time-based automation features.

        Args:
            tenant_id: Optional override (uses default if None)
            user_id: Optional override (uses default if None)

        Raises:
            NotImplementedError: Memory backend does not support expiry triggers
        """
        raise NotImplementedError(
            "Memory cache backend does not support expiry trigger functionality. "
            "Use Redis backend (cache='redis') for time-based automation features."
        )

    def create_ai_state_cache(
        self,
        tenant_id: str | None = None,
        user_id: str | None = None,
    ) -> IAIStateCache:
        """
        Create Memory AI state cache instance.

        Args:
            tenant_id: Optional override (uses default if None)
            user_id: Optional override (uses default if None)

        Returns:
            MemoryAIState implementing IAIStateCache
        """
        effective_tenant, effective_user = self._resolve_context(tenant_id, user_id)
        return MemoryAIState(tenant=effective_tenant, user_id=effective_user)
