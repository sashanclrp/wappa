"""
User repository interface.

Defines contract for user state management in Redis.
"""

from abc import abstractmethod
from datetime import timedelta
from typing import Any

from pydantic import BaseModel

from .base_repository import IBaseRepository


class IUserRepository(IBaseRepository):
    """
    Interface for user state management.

    Handles user-specific data with context binding (tenant_id + user_id).
    Uses the 'user' Redis pool (database 1).
    """

    @abstractmethod
    async def get_user_data(
        self, models: type[BaseModel] | None = None
    ) -> dict[str, Any] | None:
        """
        Get complete user data hash with optional BaseModel deserialization.

        Args:
            models: Optional BaseModel class for full object reconstruction
                   e.g., User (will automatically handle nested UserContact, UserLocation)

        Returns:
            User data dictionary or None if not found
        """
        pass

    @abstractmethod
    async def set_user_data(
        self, data: dict[str, Any], ttl: timedelta | None = None
    ) -> bool:
        """
        Set complete user data hash.

        Args:
            data: User data dictionary
            ttl: Optional time-to-live

        Returns:
            True if successful
        """
        pass

    @abstractmethod
    async def get_user_field(self, field: str) -> Any | None:
        """
        Get specific field from user data.

        Args:
            field: Field name

        Returns:
            Field value or None if not found
        """
        pass

    @abstractmethod
    async def set_user_field(self, field: str, value: Any) -> bool:
        """
        Set specific field in user data.

        Args:
            field: Field name
            value: Field value

        Returns:
            True if successful
        """
        pass

    @abstractmethod
    async def delete_user_field(self, field: str) -> bool:
        """
        Delete specific field from user data.

        Args:
            field: Field name

        Returns:
            True if field was deleted
        """
        pass

    @abstractmethod
    async def user_exists(self) -> bool:
        """
        Check if user data exists.

        Returns:
            True if user data exists
        """
        pass

    @abstractmethod
    async def delete_user(self) -> bool:
        """
        Delete all user data.

        Returns:
            True if user was deleted
        """
        pass
