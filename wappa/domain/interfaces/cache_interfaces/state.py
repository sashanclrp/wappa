"""Handler/session state cache interface (keyed by handler_name)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel


class IStateCache(ABC):
    """
    Interface for handler/session state cache operations.

    State is keyed by handler_name, allowing multiple states per user.
    User identity is established via constructor parameters.

    Example:
        state = RedisStateHandler(inbox="myapp", user_id="user123")
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

    @abstractmethod
    async def delete_all_for_user(self) -> int:
        """
        Delete every handler state entry for this cache's user_id,
        regardless of handler name.

        Pattern matched: {inbox}:state:*:{user_id}

        Returns:
            Count of deleted entries
        """
        pass

    @abstractmethod
    async def delete_by_handler_prefix(self, prefix: str) -> int:
        """
        Delete every handler entry whose name starts with prefix, scoped to
        this cache's user_id.

        Pattern matched: {inbox}:state:{prefix}*:{user_id}

        Args:
            prefix: Handler name prefix (must be non-empty)

        Returns:
            Count of deleted entries

        Raises:
            ValueError: If prefix is empty

        Example:
            count = await state_cache.delete_by_handler_prefix("template-")
        """
        pass

    @abstractmethod
    async def list_handlers(self, prefix: str | None = None) -> list[str]:
        """
        Return handler_names currently stored for this user.

        Args:
            prefix: Optional filter — only handlers starting with this are returned.
                    Pass None to list all handlers for this user.

        Returns:
            List of handler name strings

        Example:
            all_handlers = await state_cache.list_handlers()
            template_handlers = await state_cache.list_handlers("template-")
        """
        pass

    @classmethod
    @abstractmethod
    async def list_users_with_handler(
        cls, inbox_id: str, handler_name: str
    ) -> list[str]:
        """
        Return every user_id that has a state entry for handler_name under
        inbox_id. Inbox-scoped inverse of list_handlers().

        This is a classmethod so it can be called without binding to a specific
        user — it intentionally scans across all users for the inbox.

        Pattern matched: {inbox}:state:{handler_name}:*

        Args:
            inbox_id: Inbox identifier
            handler_name: Exact handler name to look up

        Returns:
            List of user_id strings that have state for this handler

        Example:
            active = await RedisStateHandler.list_users_with_handler(
                inbox_id="myapp", handler_name="human_takeover"
            )
        """
        pass
