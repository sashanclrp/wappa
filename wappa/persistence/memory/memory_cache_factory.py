"""
Memory cache factory implementation for Wappa framework.

Creates memory-backed cache instances using in-memory storage
with handlers implementing type-specific interfaces directly.
"""

from ...domain.interfaces.cache_factory import ICacheFactory
from ...domain.interfaces.cache_interfaces import IStateCache, ITableCache, IUserCache
from .handlers.state_handler import MemoryStateHandler
from .handlers.table_handler import MemoryTable
from .handlers.user_handler import MemoryUser


class MemoryCacheFactory(ICacheFactory):
    """
    Factory for creating memory-backed cache instances.

    Uses thread-safe in-memory storage with TTL support:
    - State cache: Uses states namespace with automatic TTL cleanup
    - User cache: Uses users namespace with context isolation
    - Table cache: Uses tables namespace with tenant isolation

    All instances implement the type-specific cache interfaces directly.

    Context (tenant_id, user_id) is injected at construction time, eliminating
    manual parameter passing.

    Cache data is stored in memory with automatic background cleanup of expired entries.
    """

    def __init__(self, tenant_id: str, user_id: str):
        """Initialize Memory cache factory with context injection."""
        super().__init__(tenant_id, user_id)

    def create_state_cache(self) -> IStateCache:
        """
        Create Memory state cache instance.

        Uses context (tenant_id, user_id) injected at construction time.
        Stores data in memory with namespace isolation and automatic TTL cleanup.

        Returns:
            MemoryStateHandler implementing IStateCache
        """
        return MemoryStateHandler(tenant=self.tenant_id, user_id=self.user_id)

    def create_user_cache(self) -> IUserCache:
        """
        Create Memory user cache instance.

        Uses context (tenant_id, user_id) injected at construction time.
        Stores data in memory with namespace isolation and automatic TTL cleanup.

        Returns:
            MemoryUser implementing IUserCache
        """
        return MemoryUser(tenant=self.tenant_id, user_id=self.user_id)

    def create_table_cache(self) -> ITableCache:
        """
        Create Memory table cache instance.

        Uses context (tenant_id) injected at construction time.
        Stores data in memory with namespace isolation and automatic TTL cleanup.

        Returns:
            MemoryTable implementing ITableCache
        """
        return MemoryTable(tenant=self.tenant_id)
