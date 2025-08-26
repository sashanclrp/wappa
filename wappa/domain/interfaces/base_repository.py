"""
Base repository interface.

Defines common contract for all Redis-based repositories.
"""

from abc import ABC, abstractmethod
from datetime import timedelta
from typing import Any

from pydantic import BaseModel


class IBaseRepository(ABC):
    """
    Base interface for all Redis repositories.

    Provides common contract for key-value operations, TTL management,
    and context-aware operations.
    """

    @abstractmethod
    async def get(self, key: str) -> Any | None:
        """Get value by key."""
        pass

    @abstractmethod
    async def set(self, key: str, value: Any, ttl: timedelta | None = None) -> bool:
        """Set value with optional TTL."""
        pass

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """Delete key."""
        pass

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Check if key exists."""
        pass

    @abstractmethod
    async def get_ttl(self, key: str) -> int | None:
        """Get TTL for key in seconds."""
        pass

    @abstractmethod
    async def set_ttl(self, key: str, ttl: timedelta) -> bool:
        """Set TTL for existing key."""
        pass

    @abstractmethod
    async def get_hash(
        self, key: str, models: type[BaseModel] | None = None
    ) -> dict[str, Any] | None:
        """
        Get hash value with optional BaseModel deserialization.

        Args:
            key: Redis key
            models: Optional BaseModel class for full object reconstruction
                   e.g., User (will automatically handle nested UserContact, UserLocation)

        Returns:
            Hash data dictionary or None if not found
        """
        pass

    @abstractmethod
    async def set_hash(
        self, key: str, data: dict[str, Any], ttl: timedelta | None = None
    ) -> bool:
        """Set hash value with optional TTL."""
        pass

    @abstractmethod
    async def get_hash_field(self, key: str, field: str) -> Any | None:
        """Get single field from hash."""
        pass

    @abstractmethod
    async def set_hash_field(self, key: str, field: str, value: Any) -> bool:
        """Set single field in hash."""
        pass

    @abstractmethod
    async def delete_hash_field(self, key: str, field: str) -> bool:
        """Delete field from hash."""
        pass

    @abstractmethod
    async def get_keys_pattern(self, pattern: str) -> list[str]:
        """Get keys matching pattern."""
        pass
