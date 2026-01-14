"""
Cache factory interface definition for Wappa framework.

Defines the contract for creating context-aware cache instances with hybrid pattern support.
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

    HYBRID PATTERN: Context (tenant_id, user_id) can be:
    1. Injected at construction time (default context for most operations)
    2. Overridden per-call when creating cache instances (for special cases like API events)

    This pattern supports:
    - Webhook processing: Uses default context (sender as user_id)
    - API processing: Overrides user_id with recipient
    - Both scenarios using the SAME factory instance

    The factory returns type-specific cache interfaces (IUserCache, IStateCache,
    ITableCache) which provide domain-appropriate method signatures rather than
    the generic ICache interface.

    Example:
        # Webhook flow - uses default context
        cache = factory.create_user_cache()

        # API flow - overrides user_id with recipient
        cache = factory.create_user_cache(user_id=event.recipient)
    """

    def __init__(self, tenant_id: str, user_id: str):
        """
        Initialize cache factory with default request context.

        This eliminates the need for manual parameter passing in most cases.
        Context can be overridden per-call when needed (e.g., API events).

        Args:
            tenant_id: Default tenant identifier for namespace isolation
            user_id: Default user identifier for user-specific caches

        Raises:
            ValueError: If tenant_id or user_id is None or empty
        """
        if not tenant_id or not user_id:
            raise ValueError(
                f"Missing required context: tenant_id={tenant_id}, user_id={user_id}"
            )
        self.tenant_id = tenant_id
        self.user_id = user_id

    def _resolve_context(
        self,
        tenant_id: str | None = None,
        user_id: str | None = None,
    ) -> tuple[str, str]:
        """
        Resolve effective tenant_id and user_id using override or default.

        Args:
            tenant_id: Optional override for tenant_id (uses default if None)
            user_id: Optional override for user_id (uses default if None)

        Returns:
            Tuple of (effective_tenant_id, effective_user_id)
        """
        return (
            tenant_id if tenant_id is not None else self.tenant_id,
            user_id if user_id is not None else self.user_id,
        )

    @abstractmethod
    def create_state_cache(
        self,
        tenant_id: str | None = None,
        user_id: str | None = None,
    ) -> IStateCache:
        """
        Create state cache instance with context binding.

        Used for handler state management and conversation state tracking.

        Args:
            tenant_id: Optional override (uses default if None)
            user_id: Optional override (uses default if None)

        Returns:
            Context-bound state cache instance implementing IStateCache

        Example:
            # Use default context (webhook flow)
            cache = factory.create_state_cache()

            # Override user_id (API flow with different recipient)
            cache = factory.create_state_cache(user_id=event.recipient)
        """
        pass

    @abstractmethod
    def create_user_cache(
        self,
        tenant_id: str | None = None,
        user_id: str | None = None,
    ) -> IUserCache:
        """
        Create user cache instance with context binding.

        Used for user profile data, preferences, and user-specific information.

        Args:
            tenant_id: Optional override (uses default if None)
            user_id: Optional override (uses default if None)

        Returns:
            Context-bound user cache instance implementing IUserCache

        Example:
            # Use default context (webhook flow)
            cache = factory.create_user_cache()

            # Override user_id (API flow with different recipient)
            cache = factory.create_user_cache(user_id=event.recipient)
        """
        pass

    @abstractmethod
    def create_table_cache(
        self,
        tenant_id: str | None = None,
    ) -> ITableCache:
        """
        Create table cache instance with context binding.

        Used for shared data, lookup tables, and tenant-wide information.

        Args:
            tenant_id: Optional override (uses default if None)

        Returns:
            Context-bound table cache instance implementing ITableCache
        """
        pass

    @abstractmethod
    def create_expiry_cache(
        self,
        tenant_id: str | None = None,
        user_id: str | None = None,
    ) -> IExpiryCache:
        """
        Create expiry trigger cache instance with context binding.

        Used for time-based automation (reminders, timeouts, scheduled actions).

        Args:
            tenant_id: Optional override (uses default if None)
            user_id: Optional override (uses default if None)

        Returns:
            Context-bound expiry cache instance implementing IExpiryCache

        Example:
            # Use default context
            expiry_cache = factory.create_expiry_cache()
            await expiry_cache.set("payment_reminder", "TXN_123", 1800)

            # Override for specific user
            expiry_cache = factory.create_expiry_cache(user_id=recipient_id)
        """
        pass

    @abstractmethod
    def create_ai_state_cache(
        self,
        tenant_id: str | None = None,
        user_id: str | None = None,
    ) -> IAIStateCache:
        """
        Create AI state cache instance with context binding.

        Used for AI agent state management and context sharing.

        Args:
            tenant_id: Optional override (uses default if None)
            user_id: Optional override (uses default if None)

        Returns:
            Context-bound AI state cache instance implementing IAIStateCache

        Example:
            # Use default context
            ai_state = factory.create_ai_state_cache()
            await ai_state.upsert("summarizer", {"context": "meeting notes"})

            # Override for specific user
            ai_state = factory.create_ai_state_cache(user_id=recipient_id)
        """
        pass
