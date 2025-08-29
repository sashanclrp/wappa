"""
JSON cache factory implementation for Wappa framework.

Creates JSON-backed cache instances using file-based storage
with ICache adapters for uniform interface.
"""

from ...domain.interfaces.cache_factory import ICacheFactory
from ...domain.interfaces.cache_interface import ICache
from .cache_adapters import (
    JSONStateCacheAdapter,
    JSONTableCacheAdapter,
    JSONUserCacheAdapter,
)


class JSONCacheFactory(ICacheFactory):
    """
    Factory for creating JSON-backed cache instances.

    Uses file-based JSON storage with proper file management:
    - State cache: Uses states subdirectory
    - User cache: Uses users subdirectory  
    - Table cache: Uses tables subdirectory

    All instances implement the ICache interface through adapters.

    Context (tenant_id, user_id) is injected at construction time, eliminating
    manual parameter passing.

    Cache files are automatically created in {project_root}/cache/ directory structure.
    """

    def __init__(self, tenant_id: str, user_id: str):
        """Initialize JSON cache factory with context injection."""
        super().__init__(tenant_id, user_id)

    def create_state_cache(self) -> ICache:
        """
        Create JSON state cache instance.

        Uses context (tenant_id, user_id) injected at construction time.
        Stores data in {project_root}/cache/states/ directory.

        Returns:
            ICache adapter wrapping JSONStateHandler
        """
        return JSONStateCacheAdapter(
            tenant_id=self.tenant_id, user_id=self.user_id
        )

    def create_user_cache(self) -> ICache:
        """
        Create JSON user cache instance.

        Uses context (tenant_id, user_id) injected at construction time.
        Stores data in {project_root}/cache/users/ directory.

        Returns:
            ICache adapter wrapping JSONUser
        """
        return JSONUserCacheAdapter(
            tenant_id=self.tenant_id, user_id=self.user_id
        )

    def create_table_cache(self) -> ICache:
        """
        Create JSON table cache instance.

        Uses context (tenant_id) injected at construction time.
        Stores data in {project_root}/cache/tables/ directory.

        Returns:
            ICache adapter wrapping JSONTable
        """
        return JSONTableCacheAdapter(tenant_id=self.tenant_id)