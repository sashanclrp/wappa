"""
JSON cache factory implementation for Wappa framework.

Creates JSON-backed cache instances using file-based storage
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
from .handlers.ai_state import JSONAIState
from .handlers.state_handler import JSONStateHandler
from .handlers.table_handler import JSONTable
from .handlers.user_handler import JSONUser


class JSONCacheFactory(ICacheFactory):
    """
    Factory for creating JSON-backed cache instances with hybrid pattern support.

    Uses file-based JSON storage with proper file management:
    - State cache: Uses states subdirectory
    - User cache: Uses users subdirectory
    - Table cache: Uses tables subdirectory
    - AI State cache: Uses ai_states subdirectory

    All instances implement the type-specific cache interfaces directly.

    HYBRID PATTERN: Context (tenant_id, user_id) can be:
    1. Used from defaults set at construction (most common - webhook flow)
    2. Overridden per-call (for API events with different user context)

    Cache files are automatically created in {project_root}/cache/ directory structure.
    """

    def create_state_cache(
        self,
        tenant_id: str | None = None,
        user_id: str | None = None,
    ) -> IStateCache:
        """
        Create JSON state cache instance.

        Args:
            tenant_id: Optional override (uses default if None)
            user_id: Optional override (uses default if None)

        Returns:
            JSONStateHandler implementing IStateCache
        """
        effective_tenant, effective_user = self._resolve_context(tenant_id, user_id)
        return JSONStateHandler(tenant=effective_tenant, user_id=effective_user)

    def create_user_cache(
        self,
        tenant_id: str | None = None,
        user_id: str | None = None,
    ) -> IUserCache:
        """
        Create JSON user cache instance.

        Args:
            tenant_id: Optional override (uses default if None)
            user_id: Optional override (uses default if None)

        Returns:
            JSONUser implementing IUserCache
        """
        effective_tenant, effective_user = self._resolve_context(tenant_id, user_id)
        return JSONUser(tenant=effective_tenant, user_id=effective_user)

    def create_table_cache(
        self,
        tenant_id: str | None = None,
    ) -> ITableCache:
        """
        Create JSON table cache instance.

        Args:
            tenant_id: Optional override (uses default if None)

        Returns:
            JSONTable implementing ITableCache
        """
        effective_tenant, _ = self._resolve_context(tenant_id, None)
        return JSONTable(tenant=effective_tenant)

    def create_expiry_cache(
        self,
        tenant_id: str | None = None,
        user_id: str | None = None,
    ) -> IExpiryCache:
        """
        Create JSON expiry cache instance.

        NOTE: JSON backend does not support expiry trigger functionality.
        Use Redis backend for time-based automation features.

        Args:
            tenant_id: Optional override (uses default if None)
            user_id: Optional override (uses default if None)

        Raises:
            NotImplementedError: JSON backend does not support expiry triggers
        """
        raise NotImplementedError(
            "JSON cache backend does not support expiry trigger functionality. "
            "Use Redis backend (cache='redis') for time-based automation features."
        )

    def create_ai_state_cache(
        self,
        tenant_id: str | None = None,
        user_id: str | None = None,
    ) -> IAIStateCache:
        """
        Create JSON AI state cache instance.

        Args:
            tenant_id: Optional override (uses default if None)
            user_id: Optional override (uses default if None)

        Returns:
            JSONAIState implementing IAIStateCache
        """
        effective_tenant, effective_user = self._resolve_context(tenant_id, user_id)
        return JSONAIState(tenant=effective_tenant, user_id=effective_user)
