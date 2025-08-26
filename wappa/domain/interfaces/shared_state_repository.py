"""
Shared state repository interface.

Defines contract for shared state management in Redis.
"""

from abc import abstractmethod
from datetime import timedelta
from typing import Any

from pydantic import BaseModel

from .base_repository import IBaseRepository


class ISharedStateRepository(IBaseRepository):
    """
    Interface for shared state management.

    Handles shared state and tool scratch-space with context binding.
    Uses the 'symphony_shared_state' Redis pool (database 3).
    """

    @abstractmethod
    async def get_shared_state(
        self,
        state_name: str,
        models: type[BaseModel] | None = None,
    ) -> dict[str, Any] | None:
        """
        Get shared state for user with optional BaseModel deserialization.

        Args:
            state_name: Name of the state (e.g., 'conversation', 'context')
            models: Optional BaseModel class for full object reconstruction

        Returns:
            Shared state dictionary or None if not found
        """
        pass

    @abstractmethod
    async def set_shared_state(
        self,
        state_name: str,
        state_data: dict[str, Any],
        ttl: timedelta | None = None,
    ) -> bool:
        """
        Set shared state for user.

        Args:
            state_name: Name of the state
            state_data: State data dictionary
            ttl: Optional time-to-live

        Returns:
            True if successful
        """
        pass

    @abstractmethod
    async def get_state_field(self, state_name: str, field: str) -> Any | None:
        """
        Get specific field from shared state.

        Args:
            state_name: Name of the state
            field: Field name

        Returns:
            Field value or None if not found
        """
        pass

    @abstractmethod
    async def set_state_field(self, state_name: str, field: str, value: Any) -> bool:
        """
        Set specific field in shared state.

        Args:
            state_name: Name of the state
            field: Field name
            value: Field value

        Returns:
            True if successful
        """
        pass

    @abstractmethod
    async def delete_shared_state(self, state_name: str) -> bool:
        """
        Delete complete shared state.

        Args:
            state_name: Name of the state

        Returns:
            True if state was deleted
        """
        pass

    @abstractmethod
    async def get_user_states(self) -> list[str]:
        """
        Get all active state names for user.

        Returns:
            List of state names
        """
        pass

    @abstractmethod
    async def clear_user_states(self) -> bool:
        """
        Clear all shared states for user.

        Returns:
            True if states were cleared
        """
        pass
