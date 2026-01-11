"""
JSON cache factory implementation for Wappa framework.

Creates JSON-backed cache instances using file-based storage
with handlers implementing type-specific interfaces directly.
"""

from ...domain.interfaces.cache_factory import ICacheFactory
from ...domain.interfaces.cache_interfaces import (
    IAIStateCache,
    IStateCache,
    ITableCache,
    IUserCache,
)
from .handlers.ai_state import JSONAIState
from .handlers.state_handler import JSONStateHandler
from .handlers.table_handler import JSONTable
from .handlers.user_handler import JSONUser


class JSONCacheFactory(ICacheFactory):
    """
    Factory for creating JSON-backed cache instances.

    Uses file-based JSON storage with proper file management:
    - State cache: Uses states subdirectory
    - User cache: Uses users subdirectory
    - Table cache: Uses tables subdirectory
    - AI State cache: Uses ai_states subdirectory

    All instances implement the type-specific cache interfaces directly.

    Context (tenant_id, user_id) is injected at construction time, eliminating
    manual parameter passing.

    Cache files are automatically created in {project_root}/cache/ directory structure.
    """

    def __init__(self, tenant_id: str, user_id: str):
        """Initialize JSON cache factory with context injection."""
        super().__init__(tenant_id, user_id)

    def create_state_cache(self) -> IStateCache:
        """
        Create JSON state cache instance.

        Uses context (tenant_id, user_id) injected at construction time.
        Stores data in {project_root}/cache/states/ directory.

        Returns:
            JSONStateHandler implementing IStateCache
        """
        return JSONStateHandler(tenant=self.tenant_id, user_id=self.user_id)

    def create_user_cache(self) -> IUserCache:
        """
        Create JSON user cache instance.

        Uses context (tenant_id, user_id) injected at construction time.
        Stores data in {project_root}/cache/users/ directory.

        Returns:
            JSONUser implementing IUserCache
        """
        return JSONUser(tenant=self.tenant_id, user_id=self.user_id)

    def create_table_cache(self) -> ITableCache:
        """
        Create JSON table cache instance.

        Uses context (tenant_id) injected at construction time.
        Stores data in {project_root}/cache/tables/ directory.

        Returns:
            JSONTable implementing ITableCache
        """
        return JSONTable(tenant=self.tenant_id)

    def create_ai_state_cache(self) -> IAIStateCache:
        """
        Create JSON AI state cache instance.

        Uses context (tenant_id, user_id) injected at construction time.
        Stores data in {project_root}/cache/ai_states/ directory.

        Returns:
            JSONAIState implementing IAIStateCache
        """
        return JSONAIState(tenant=self.tenant_id, user_id=self.user_id)
