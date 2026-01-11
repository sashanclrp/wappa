"""
Cache factory interface definition for Wappa framework.

Defines the contract for creating context-aware cache instances.
"""

from abc import ABC, abstractmethod

from .cache_interfaces import (
    IAIStateCache,
    IExpiryCache,
    IStateCache,
    ITableCache,
    IUserCache,
)


class ICacheFactory(ABC):
    """
    Interface for creating context-aware cache instances.

    Cache factories create cache instances bound to specific tenants and users,
    ensuring proper data isolation and context management.

    Context (tenant_id, user_id) is injected at construction time, eliminating
    the need for manual parameter passing in cache creation methods.

    The factory returns type-specific cache interfaces (IUserCache, IStateCache,
    ITableCache) which provide domain-appropriate method signatures rather than
    the generic ICache interface.
    """

    def __init__(self, tenant_id: str, user_id: str):
        """
        Initialize cache factory with request context.

        This eliminates the need for manual parameter passing in cache methods.
        Context is injected once at construction and used throughout the factory lifetime.

        Args:
            tenant_id: Tenant identifier for namespace isolation
            user_id: User identifier for user-specific caches

        Raises:
            ValueError: If tenant_id or user_id is None or empty
        """
        self.tenant_id = tenant_id
        self.user_id = user_id
        self._validate_context()

    def _validate_context(self) -> None:
        """Validate that required context is available."""
        if not self.tenant_id or not self.user_id:
            raise ValueError(
                f"Missing required context: tenant_id={self.tenant_id}, user_id={self.user_id}"
            )

    @abstractmethod
    def create_state_cache(self) -> IStateCache:
        """
        Create state cache instance with context binding.

        Used for handler state management and conversation state tracking.
        Context (tenant_id, user_id) is automatically injected from constructor.

        Returns:
            Context-bound state cache instance implementing IStateCache
        """
        pass

    @abstractmethod
    def create_user_cache(self) -> IUserCache:
        """
        Create user cache instance with context binding.

        Used for user profile data, preferences, and user-specific information.
        Context (tenant_id, user_id) is automatically injected from constructor.

        Returns:
            Context-bound user cache instance implementing IUserCache
        """
        pass

    @abstractmethod
    def create_table_cache(self) -> ITableCache:
        """
        Create table cache instance with context binding.

        Used for shared data, lookup tables, and tenant-wide information.
        Context (tenant_id) is automatically injected from constructor.

        Returns:
            Context-bound table cache instance implementing ITableCache
        """
        pass

    @abstractmethod
    def create_expiry_cache(self) -> IExpiryCache:
        """
        Create expiry trigger cache instance with context binding.

        Used for time-based automation (reminders, timeouts, scheduled actions).
        Context (tenant_id, user_id) is automatically injected from constructor.

        Returns:
            Context-bound expiry cache instance implementing IExpiryCache

        Example:
            factory = RedisCacheFactory(tenant_id="wappa", user_id="user_123")
            expiry_cache = factory.create_expiry_cache()
            await expiry_cache.set("payment_reminder", "TXN_123", 1800)
        """
        pass

    @abstractmethod
    def create_ai_state_cache(self) -> IAIStateCache:
        """
        Create AI state cache instance with context binding.

        Used for AI agent state management and context sharing.
        Context (tenant_id, user_id) is automatically injected from constructor.

        Returns:
            Context-bound AI state cache instance implementing IAIStateCache

        Example:
            factory = RedisCacheFactory(tenant_id="wappa", user_id="user_123")
            ai_state = factory.create_ai_state_cache()
            await ai_state.upsert("summarizer", {"context": "meeting notes"})
        """
        pass
