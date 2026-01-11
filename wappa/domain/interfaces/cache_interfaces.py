"""
Type-specific cache interfaces for Wappa framework.

Provides specialized interfaces for different cache types with appropriate
method signatures. These interfaces are the preferred way to define cache
contracts as they eliminate the N×M adapter problem.

Each interface defines methods specific to its domain:
- IUserCache: User-scoped data (identity implicit via constructor)
- IStateCache: Handler/session state (keyed by handler_name)
- ITableCache: Table/row data (composite key: table_name + pkid)
- IExpiryCache: Expiry triggers (composite key: action + identifier)
"""

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel


class IUserCache(ABC):
    """
    Interface for user-scoped cache operations.

    User identity is implicit - established via constructor parameters
    (tenant and user_id). All methods operate on the single user record.

    This interface eliminates the need for key parameters in basic operations
    since the user is identified at construction time.

    Example:
        user = RedisUser(tenant="myapp", user_id="user123")
        await user.upsert({"name": "Alice", "score": 100})
        data = await user.get()
        name = await user.get_field("name")
    """

    @abstractmethod
    async def get(self, models: type[BaseModel] | None = None) -> dict[str, Any] | None:
        """
        Get full user data.

        Args:
            models: Optional BaseModel class for deserialization

        Returns:
            User data dictionary or BaseModel instance, None if not found
        """
        pass

    @abstractmethod
    async def upsert(
        self, data: dict[str, Any] | BaseModel, ttl: int | None = None
    ) -> bool:
        """
        Create or update user data.

        Args:
            data: User data to store
            ttl: Time to live in seconds

        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    async def delete(self) -> int:
        """
        Delete user data.

        Returns:
            Number of keys deleted (1 if deleted, 0 if didn't exist)
        """
        pass

    @abstractmethod
    async def exists(self) -> bool:
        """
        Check if user data exists.

        Returns:
            True if exists, False otherwise
        """
        pass

    @abstractmethod
    async def get_field(self, field: str) -> Any | None:
        """
        Get a specific field from user data.

        Args:
            field: Field name

        Returns:
            Field value or None if not found
        """
        pass

    @abstractmethod
    async def update_field(
        self, field: str, value: Any, ttl: int | None = None
    ) -> bool:
        """
        Update a specific field in user data.

        Args:
            field: Field name
            value: New value
            ttl: Time to live in seconds

        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    async def increment_field(
        self, field: str, increment: int = 1, ttl: int | None = None
    ) -> int | None:
        """
        Atomically increment an integer field.

        Args:
            field: Field name
            increment: Amount to increment by
            ttl: Time to live in seconds

        Returns:
            New value after increment or None on error
        """
        pass

    @abstractmethod
    async def append_to_list(
        self, field: str, value: Any, ttl: int | None = None
    ) -> bool:
        """
        Append value to a list field.

        Args:
            field: Field name containing list
            value: Value to append
            ttl: Time to live in seconds

        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    async def get_ttl(self) -> int:
        """
        Get remaining time to live for user data.

        Returns:
            Remaining TTL in seconds, -1 if no expiry, -2 if doesn't exist
        """
        pass

    @abstractmethod
    async def renew_ttl(self, ttl: int) -> bool:
        """
        Renew time to live for user data.

        Args:
            ttl: New time to live in seconds

        Returns:
            True if successful, False otherwise
        """
        pass


class IStateCache(ABC):
    """
    Interface for handler/session state cache operations.

    State is keyed by handler_name, allowing multiple states per user.
    User identity is established via constructor parameters.

    Example:
        state = RedisStateHandler(tenant="myapp", user_id="user123")
        await state.upsert("chat_handler", {"step": 1, "context": "greeting"})
        data = await state.get("chat_handler")
    """

    @abstractmethod
    async def get(
        self, handler_name: str, models: type[BaseModel] | None = None
    ) -> dict[str, Any] | None:
        """
        Get handler state data.

        Args:
            handler_name: Handler name identifier
            models: Optional BaseModel class for deserialization

        Returns:
            Handler state data or None if not found
        """
        pass

    @abstractmethod
    async def upsert(
        self,
        handler_name: str,
        data: dict[str, Any] | BaseModel,
        ttl: int | None = None,
    ) -> bool:
        """
        Create or update handler state data.

        Args:
            handler_name: Handler name identifier
            data: State data to store
            ttl: Time to live in seconds

        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    async def delete(self, handler_name: str) -> int:
        """
        Delete handler state data.

        Args:
            handler_name: Handler name identifier

        Returns:
            Number of keys deleted (1 if deleted, 0 if didn't exist)
        """
        pass

    @abstractmethod
    async def exists(self, handler_name: str) -> bool:
        """
        Check if handler state exists.

        Args:
            handler_name: Handler name identifier

        Returns:
            True if exists, False otherwise
        """
        pass

    @abstractmethod
    async def get_field(self, handler_name: str, field: str) -> Any | None:
        """
        Get a specific field from handler state.

        Args:
            handler_name: Handler name identifier
            field: Field name

        Returns:
            Field value or None if not found
        """
        pass

    @abstractmethod
    async def update_field(
        self,
        handler_name: str,
        field: str,
        value: Any,
        ttl: int | None = None,
    ) -> bool:
        """
        Update a specific field in handler state.

        Args:
            handler_name: Handler name identifier
            field: Field name
            value: New value
            ttl: Time to live in seconds

        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    async def increment_field(
        self,
        handler_name: str,
        field: str,
        increment: int = 1,
        ttl: int | None = None,
    ) -> int | None:
        """
        Atomically increment an integer field in handler state.

        Args:
            handler_name: Handler name identifier
            field: Field name
            increment: Amount to increment by
            ttl: Time to live in seconds

        Returns:
            New value after increment or None on error
        """
        pass

    @abstractmethod
    async def append_to_list(
        self,
        handler_name: str,
        field: str,
        value: Any,
        ttl: int | None = None,
    ) -> bool:
        """
        Append value to a list field in handler state.

        Args:
            handler_name: Handler name identifier
            field: Field name containing list
            value: Value to append
            ttl: Time to live in seconds

        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    async def get_ttl(self, handler_name: str) -> int:
        """
        Get remaining time to live for handler state.

        Args:
            handler_name: Handler name identifier

        Returns:
            Remaining TTL in seconds, -1 if no expiry, -2 if doesn't exist
        """
        pass

    @abstractmethod
    async def renew_ttl(self, handler_name: str, ttl: int) -> bool:
        """
        Renew time to live for handler state.

        Args:
            handler_name: Handler name identifier
            ttl: New time to live in seconds

        Returns:
            True if successful, False otherwise
        """
        pass


class ITableCache(ABC):
    """
    Interface for table/row cache operations.

    Data is keyed by composite key (table_name + pkid).
    Tenant identity is established via constructor parameters.

    Example:
        table = RedisTable(tenant="myapp")
        await table.upsert("products", "sku123", {"name": "Widget", "price": 99})
        data = await table.get("products", "sku123")
    """

    @abstractmethod
    async def get(
        self,
        table_name: str,
        pkid: str,
        models: type[BaseModel] | None = None,
    ) -> dict[str, Any] | None:
        """
        Get table row data.

        Args:
            table_name: Table name identifier
            pkid: Primary key ID
            models: Optional BaseModel class for deserialization

        Returns:
            Table row data or None if not found
        """
        pass

    @abstractmethod
    async def upsert(
        self,
        table_name: str,
        pkid: str,
        data: dict[str, Any] | BaseModel,
        ttl: int | None = None,
    ) -> bool:
        """
        Create or update table row data.

        Args:
            table_name: Table name identifier
            pkid: Primary key ID
            data: Data to store
            ttl: Time to live in seconds

        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    async def delete(self, table_name: str, pkid: str) -> int:
        """
        Delete table row data.

        Args:
            table_name: Table name identifier
            pkid: Primary key ID

        Returns:
            Number of keys deleted (1 if deleted, 0 if didn't exist)
        """
        pass

    @abstractmethod
    async def exists(self, table_name: str, pkid: str) -> bool:
        """
        Check if table row exists.

        Args:
            table_name: Table name identifier
            pkid: Primary key ID

        Returns:
            True if exists, False otherwise
        """
        pass

    @abstractmethod
    async def get_field(self, table_name: str, pkid: str, field: str) -> Any | None:
        """
        Get a specific field from table row.

        Args:
            table_name: Table name identifier
            pkid: Primary key ID
            field: Field name

        Returns:
            Field value or None if not found
        """
        pass

    @abstractmethod
    async def update_field(
        self,
        table_name: str,
        pkid: str,
        field: str,
        value: Any,
        ttl: int | None = None,
    ) -> bool:
        """
        Update a specific field in table row.

        Args:
            table_name: Table name identifier
            pkid: Primary key ID
            field: Field name
            value: New value
            ttl: Time to live in seconds

        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    async def increment_field(
        self,
        table_name: str,
        pkid: str,
        field: str,
        increment: int = 1,
        ttl: int | None = None,
    ) -> int | None:
        """
        Atomically increment an integer field in table row.

        Args:
            table_name: Table name identifier
            pkid: Primary key ID
            field: Field name
            increment: Amount to increment by
            ttl: Time to live in seconds

        Returns:
            New value after increment or None on error
        """
        pass

    @abstractmethod
    async def append_to_list(
        self,
        table_name: str,
        pkid: str,
        field: str,
        value: Any,
        ttl: int | None = None,
    ) -> bool:
        """
        Append value to a list field in table row.

        Args:
            table_name: Table name identifier
            pkid: Primary key ID
            field: Field name containing list
            value: Value to append
            ttl: Time to live in seconds

        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    async def get_ttl(self, table_name: str, pkid: str) -> int:
        """
        Get remaining time to live for table row.

        Args:
            table_name: Table name identifier
            pkid: Primary key ID

        Returns:
            Remaining TTL in seconds, -1 if no expiry, -2 if doesn't exist
        """
        pass

    @abstractmethod
    async def renew_ttl(self, table_name: str, pkid: str, ttl: int) -> bool:
        """
        Renew time to live for table row.

        Args:
            table_name: Table name identifier
            pkid: Primary key ID
            ttl: New time to live in seconds

        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    async def get_all(
        self,
        table_name: str,
        models: type[BaseModel] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Get all rows for a table.

        Args:
            table_name: Table name identifier
            models: Optional BaseModel class for deserialization

        Returns:
            List of table row data dictionaries
        """
        pass


class IExpiryCache(ABC):
    """
    Interface for expiry trigger cache operations.

    Expiry triggers are simple key-value pairs with TTL that fire notifications
    when they expire. Used for time-based automation (reminders, timeouts, etc.).

    The key is composite: (action, identifier)
    - action: Type of trigger (e.g., "payment_reminder")
    - identifier: Unique ID (e.g., "TXN_12345")

    Triggers are fire-and-forget - no data retrieval needed. When a trigger
    expires, a registered handler is called with the identifier.

    Example:
        expiry = RedisExpiry(tenant="myapp", user_id="user123")
        await expiry.set("payment_reminder", "TXN_123", ttl_seconds=1800)
        # After 30 minutes, handler for "payment_reminder" is called
        # with identifier="TXN_123"
    """

    @abstractmethod
    async def set(self, action: str, identifier: str, ttl_seconds: int) -> bool:
        """
        Create expiry trigger that fires after TTL expires.

        Args:
            action: Action name (e.g., "reservation_reminder")
            identifier: Unique identifier (e.g., "TXN_12345")
            ttl_seconds: Time-to-live in seconds

        Returns:
            True if trigger created successfully

        Example:
            await expiry_cache.set("payment_reminder", "TXN_123", 1800)
            # After 30 minutes, handler for "payment_reminder" will be called
            # with identifier="TXN_123"
        """
        pass

    @abstractmethod
    async def delete(self, action: str, identifier: str) -> int:
        """
        Delete specific trigger before it fires.

        Args:
            action: Action name
            identifier: Unique identifier

        Returns:
            Number of triggers deleted (0 or 1)

        Example:
            # Cancel payment reminder
            count = await expiry_cache.delete("payment_reminder", "TXN_123")
        """
        pass

    @abstractmethod
    async def delete_all_by_identifier(self, identifier: str) -> int:
        """
        Delete all triggers for an identifier (all actions).

        This is useful for cleaning up all triggers related to a transaction
        or entity when it's cancelled or completed.

        Args:
            identifier: Unique identifier

        Returns:
            Number of triggers deleted

        Example:
            # Delete all triggers for transaction (reminder, expiry, etc.)
            count = await expiry_cache.delete_all_by_identifier("TXN_123")
        """
        pass

    @abstractmethod
    async def exists(self, action: str, identifier: str) -> bool:
        """
        Check if trigger exists (hasn't fired yet).

        Args:
            action: Action name
            identifier: Unique identifier

        Returns:
            True if trigger exists, False otherwise

        Example:
            if await expiry_cache.exists("payment_reminder", "TXN_123"):
                print("Reminder is still scheduled")
        """
        pass

    @abstractmethod
    async def get_ttl(self, action: str, identifier: str) -> int:
        """
        Get remaining time-to-live in seconds.

        Args:
            action: Action name
            identifier: Unique identifier

        Returns:
            Positive int: Seconds remaining until trigger fires
            -1: Trigger doesn't exist
            -2: Trigger exists but has no expiry (shouldn't happen for triggers)

        Example:
            ttl = await expiry_cache.get_ttl("payment_reminder", "TXN_123")
            if ttl > 0:
                print(f"Reminder fires in {ttl} seconds")
        """
        pass


class IAIStateCache(ABC):
    """
    Interface for AI agent state cache operations.

    State shared among AI agents for context and coordination.
    Agent identity is established via agent_name parameter.

    Key pattern: {tenant}:aistate:{agent_name}:{user_id}
    Example: "wappa:aistate:summarizer:user123"
    """

    @abstractmethod
    async def get(
        self, agent_name: str, models: type[BaseModel] | None = None
    ) -> dict[str, Any] | None:
        """
        Get AI agent state data.

        Args:
            agent_name: Name of the AI agent
            models: Optional BaseModel class for full object reconstruction

        Returns:
            AI agent state dictionary or None if not found
        """
        pass

    @abstractmethod
    async def upsert(
        self, agent_name: str, data: dict[str, Any] | BaseModel, ttl: int | None = None
    ) -> bool:
        """
        Create or update AI agent state data.

        Args:
            agent_name: Name of the AI agent
            data: State data to store
            ttl: Time to live in seconds

        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    async def delete(self, agent_name: str) -> int:
        """
        Delete AI agent state data.

        Args:
            agent_name: Name of the AI agent

        Returns:
            Number of keys deleted (1 if deleted, 0 if didn't exist)
        """
        pass

    @abstractmethod
    async def exists(self, agent_name: str) -> bool:
        """
        Check if AI agent state exists.

        Args:
            agent_name: Name of the AI agent

        Returns:
            True if exists, False otherwise
        """
        pass

    @abstractmethod
    async def get_field(self, agent_name: str, field: str) -> Any | None:
        """
        Get specific field from AI agent state.

        Args:
            agent_name: Name of the AI agent
            field: Field name

        Returns:
            Field value or None if not found
        """
        pass

    @abstractmethod
    async def update_field(
        self, agent_name: str, field: str, value: Any, ttl: int | None = None
    ) -> bool:
        """
        Update specific field in AI agent state.

        Args:
            agent_name: Name of the AI agent
            field: Field name
            value: New value
            ttl: Time to live in seconds

        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    async def increment_field(
        self, agent_name: str, field: str, increment: int = 1, ttl: int | None = None
    ) -> int | None:
        """
        Atomically increment integer field in AI agent state.

        Args:
            agent_name: Name of the AI agent
            field: Field name
            increment: Amount to increment by
            ttl: Time to live in seconds

        Returns:
            New value after increment or None on error
        """
        pass

    @abstractmethod
    async def append_to_list(
        self, agent_name: str, field: str, value: Any, ttl: int | None = None
    ) -> bool:
        """
        Append value to list field in AI agent state.

        Args:
            agent_name: Name of the AI agent
            field: Field name containing list
            value: Value to append
            ttl: Time to live in seconds

        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    async def get_ttl(self, agent_name: str) -> int:
        """
        Get remaining TTL for AI agent state.

        Args:
            agent_name: Name of the AI agent

        Returns:
            Remaining TTL in seconds, -1 if no expiry, -2 if doesn't exist
        """
        pass

    @abstractmethod
    async def renew_ttl(self, agent_name: str, ttl: int) -> bool:
        """
        Renew TTL for AI agent state.

        Args:
            agent_name: Name of the AI agent
            ttl: New time to live in seconds

        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    async def merge(
        self,
        agent_name: str,
        state_data: dict[str, Any],
        ttl: int | None = None,
        models: type[BaseModel] | None = None,
    ) -> dict[str, Any] | None:
        """
        Merge new data with existing AI agent state.

        Args:
            agent_name: Name of the AI agent
            state_data: New state data to merge
            ttl: Optional TTL override
            models: Optional mapping for BaseModel deserialization

        Returns:
            Final merged state or None on failure
        """
        pass
