"""
Cache interface definition for Wappa framework.

DEPRECATED: This generic ICache interface is deprecated in favor of the
type-specific interfaces in cache_interfaces.py:
- IUserCache: For user-scoped data
- IStateCache: For handler/session state
- ITableCache: For table/row data

The type-specific interfaces provide domain-appropriate method signatures
and eliminate the N×M adapter problem. New code should use the type-specific
interfaces directly.

This interface is kept for backwards compatibility but may be removed in
a future version.
"""

import warnings
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel


class ICache(ABC):
    """
    Generic interface for cache implementations in the Wappa framework.

    DEPRECATED: Use type-specific interfaces instead:
    - IUserCache: For user-scoped data (identity implicit via constructor)
    - IStateCache: For handler/session state (keyed by handler_name)
    - ITableCache: For table/row data (composite key: table_name + pkid)

    This interface is maintained for backwards compatibility only.
    """

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        # Only warn for direct subclasses, not for the type-specific interfaces
        if cls.__module__.startswith("wappa."):
            warnings.warn(
                f"Class {cls.__name__} inherits from deprecated ICache interface. "
                "Use IUserCache, IStateCache, or ITableCache instead.",
                DeprecationWarning,
                stacklevel=2,
            )

    @abstractmethod
    async def get(
        self, key: str, models: type[BaseModel] | None = None
    ) -> dict[str, Any] | None:
        """
        Get cached data by key.

        Args:
            key: Cache key
            models: Optional BaseModel class for deserialization

        Returns:
            Cached data or None if not found
        """
        pass

    @abstractmethod
    async def set(self, key: str, data: dict[str, Any], ttl: int | None = None) -> bool:
        """
        Set cached data with optional TTL.

        Args:
            key: Cache key
            data: Data to cache
            ttl: Time to live in seconds

        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """
        Delete cached data by key.

        Args:
            key: Cache key to delete

        Returns:
            True if deleted, False if not found
        """
        pass

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """
        Check if key exists in cache.

        Args:
            key: Cache key to check

        Returns:
            True if exists, False otherwise
        """
        pass

    @abstractmethod
    async def get_field(self, key: str, field: str) -> Any | None:
        """
        Get a specific field from cached hash data.

        Args:
            key: Cache key
            field: Field name

        Returns:
            Field value or None if not found
        """
        pass

    @abstractmethod
    async def set_field(
        self, key: str, field: str, value: Any, ttl: int | None = None
    ) -> bool:
        """
        Set a specific field in cached hash data.

        Args:
            key: Cache key
            field: Field name
            value: Field value
            ttl: Time to live in seconds

        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    async def increment_field(
        self, key: str, field: str, increment: int = 1, ttl: int | None = None
    ) -> int | None:
        """
        Atomically increment an integer field.

        Args:
            key: Cache key
            field: Field name
            increment: Amount to increment by
            ttl: Time to live in seconds

        Returns:
            New value after increment or None on error
        """
        pass

    @abstractmethod
    async def append_to_list(
        self, key: str, field: str, value: Any, ttl: int | None = None
    ) -> bool:
        """
        Append value to a list field.

        Args:
            key: Cache key
            field: Field name containing list
            value: Value to append
            ttl: Time to live in seconds

        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    async def get_ttl(self, key: str) -> int:
        """
        Get remaining time to live for a key.

        Args:
            key: Cache key

        Returns:
            Remaining TTL in seconds, -1 if no expiry, -2 if key doesn't exist
        """
        pass

    @abstractmethod
    async def set_ttl(self, key: str, ttl: int) -> bool:
        """
        Set time to live for a key.

        Args:
            key: Cache key
            ttl: Time to live in seconds

        Returns:
            True if successful, False otherwise
        """
        pass

    @staticmethod
    def create_table_key(table_name: str, pkid: str) -> str:
        """
        Create a properly formatted table cache key.

        DEPRECATED: Use ITableCache.get(table_name, pkid) directly instead.

        This is a static utility method available on all cache implementations
        to ensure consistent key formatting across cache backends.

        Args:
            table_name: Name of the table (e.g., "user_profiles", "message_logs")
            pkid: Primary key ID (e.g., user_id, message_id)

        Returns:
            Formatted key string for use with cache methods

        Example:
            key = ICache.create_table_key("user_profiles", "12345")
            # Returns: "user_profiles:12345"
        """
        if not table_name or not pkid:
            raise ValueError("Both table_name and pkid must be provided and non-empty")

        # Sanitize inputs to avoid conflicts
        safe_table_name = str(table_name).replace(":", "_")
        safe_pkid = str(pkid).replace(":", "_")

        return f"{safe_table_name}:{safe_pkid}"
