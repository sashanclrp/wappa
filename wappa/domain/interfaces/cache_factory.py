"""
Cache factory interface definition for Wappa framework.

Defines the contract for creating context-aware cache instances.
"""

from abc import ABC, abstractmethod

from .cache_interface import ICache


class ICacheFactory(ABC):
    """
    Interface for creating context-aware cache instances.

    Cache factories create cache instances bound to specific tenants and users,
    ensuring proper data isolation and context management.
    """

    @abstractmethod
    def create_state_cache(self, tenant_id: str, user_id: str) -> ICache:
        """
        Create state cache instance with context binding.

        Used for handler state management and conversation state tracking.

        Args:
            tenant_id: Tenant identifier for namespace isolation
            user_id: User identifier for user-specific state

        Returns:
            Context-bound state cache instance
        """
        pass

    @abstractmethod
    def create_user_cache(self, tenant_id: str, user_id: str) -> ICache:
        """
        Create user cache instance with context binding.

        Used for user profile data, preferences, and user-specific information.

        Args:
            tenant_id: Tenant identifier for namespace isolation
            user_id: User identifier for user-specific data

        Returns:
            Context-bound user cache instance
        """
        pass

    @abstractmethod
    def create_table_cache(self, tenant_id: str) -> ICache:
        """
        Create table cache instance with context binding.

        Used for shared data, lookup tables, and tenant-wide information.

        Args:
            tenant_id: Tenant identifier for namespace isolation

        Returns:
            Context-bound table cache instance
        """
        pass
