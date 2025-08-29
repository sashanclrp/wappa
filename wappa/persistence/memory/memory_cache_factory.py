"""
Memory cache factory implementation for Wappa framework.

Creates memory-backed cache instances using in-memory storage
with ICache adapters for uniform interface.
"""

from ...domain.interfaces.cache_factory import ICacheFactory
from ...domain.interfaces.cache_interface import ICache
from .cache_adapters import (
    MemoryStateCacheAdapter,
    MemoryTableCacheAdapter,
    MemoryUserCacheAdapter,
)


class MemoryCacheFactory(ICacheFactory):
    """
    Factory for creating memory-backed cache instances.

    Uses thread-safe in-memory storage with TTL support:
    - State cache: Uses states namespace with automatic TTL cleanup
    - User cache: Uses users namespace with context isolation
    - Table cache: Uses tables namespace with tenant isolation

    All instances implement the ICache interface through adapters.

    Context (tenant_id, user_id) is injected at construction time, eliminating
    manual parameter passing.

    Cache data is stored in memory with automatic background cleanup of expired entries.
    """

    def __init__(self, tenant_id: str, user_id: str):
        """Initialize Memory cache factory with context injection."""
        super().__init__(tenant_id, user_id)

    def create_state_cache(self) -> ICache:
        """
        Create Memory state cache instance.

        Uses context (tenant_id, user_id) injected at construction time.
        Stores data in memory with namespace isolation and automatic TTL cleanup.

        Returns:
            ICache adapter wrapping MemoryStateHandler
        """
        return MemoryStateCacheAdapter(
            tenant_id=self.tenant_id, user_id=self.user_id
        )

    def create_user_cache(self) -> ICache:
        """
        Create Memory user cache instance.

        Uses context (tenant_id, user_id) injected at construction time.
        Stores data in memory with namespace isolation and automatic TTL cleanup.

        Returns:
            ICache adapter wrapping MemoryUser
        """
        return MemoryUserCacheAdapter(
            tenant_id=self.tenant_id, user_id=self.user_id
        )

    def create_table_cache(self) -> ICache:
        """
        Create Memory table cache instance.

        Uses context (tenant_id) injected at construction time.
        Stores data in memory with namespace isolation and automatic TTL cleanup.

        Returns:
            ICache adapter wrapping MemoryTable
        """
        return MemoryTableCacheAdapter(tenant_id=self.tenant_id)