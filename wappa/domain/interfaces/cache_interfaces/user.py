"""User-scoped cache interface (identity implicit via constructor)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel


class IUserCache(ABC):
    """
    Interface for user-scoped cache operations.

    User identity is implicit - established via constructor parameters
    (inbox and user_id). All methods operate on the single user record.

    This interface eliminates the need for key parameters in basic operations
    since the user is identified at construction time.

    Example:
        user = RedisUser(inbox="myapp", user_id="user123")
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
