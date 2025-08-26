"""
State repository interface.

Defines contract for handler state management in Redis.
"""

from abc import abstractmethod
from datetime import timedelta
from typing import Any

from pydantic import BaseModel

from .base_repository import IBaseRepository


class IStateRepository(IBaseRepository):
    """
    Interface for handler state management.

    Handles flow states and handler-specific data with context binding.
    Uses the 'handlers' Redis pool (database 2).
    """

    @abstractmethod
    async def get_handler_state(
        self,
        handler_type: str,
        models: type[BaseModel] | None = None,
    ) -> dict[str, Any] | None:
        """
        Get handler state for user with optional BaseModel deserialization.

        Args:
            handler_type: Type of handler (e.g., 'registration', 'reservation')
            models: Optional BaseModel class for full object reconstruction
                   e.g., DemoHotelRegistrationState (will automatically handle nested models)

        Returns:
            Handler state dictionary or None if not found
        """
        pass

    @abstractmethod
    async def set_handler_state(
        self,
        handler_type: str,
        state_data: dict[str, Any],
        ttl: timedelta | None = None,
    ) -> bool:
        """
        Set handler state for user.

        Args:
            handler_type: Type of handler
            state_data: State data dictionary
            ttl: Optional time-to-live

        Returns:
            True if successful
        """
        pass

    @abstractmethod
    async def get_state_field(self, handler_type: str, field: str) -> Any | None:
        """
        Get specific field from handler state.

        Args:
            handler_type: Type of handler
            field: Field name

        Returns:
            Field value or None if not found
        """
        pass

    @abstractmethod
    async def set_state_field(self, handler_type: str, field: str, value: Any) -> bool:
        """
        Set specific field in handler state.

        Args:
            handler_type: Type of handler
            field: Field name
            value: Field value

        Returns:
            True if successful
        """
        pass

    @abstractmethod
    async def delete_handler_state(self, handler_type: str) -> bool:
        """
        Delete complete handler state.

        Args:
            handler_type: Type of handler

        Returns:
            True if state was deleted
        """
        pass

    @abstractmethod
    async def get_user_handlers(self) -> list[str]:
        """
        Get all active handler types for user.

        Returns:
            List of handler type names
        """
        pass

    @abstractmethod
    async def clear_user_states(self) -> bool:
        """
        Clear all handler states for user.

        Returns:
            True if states were cleared
        """
        pass
