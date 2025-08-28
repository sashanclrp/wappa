"""
Expiry repository interface.

Defines contract for TTL-based workflow management in Redis.
"""

from abc import abstractmethod
from datetime import timedelta

from .base_repository import IBaseRepository


class IExpiryRepository(IBaseRepository):
    """
    Interface for TTL-based workflow management.

    Handles expiry triggers and time-based automation with context binding.
    Uses the 'expiry' Redis pool (database 8).

    This interface mirrors the RedisTrigger implementation:
    - create_expiry_trigger(action, identifier, ttl) -> set(action, identifier, ttl_seconds)
    - delete_expiry_trigger(action, identifier) -> delete(action, identifier)
    - delete_all_expiry_triggers_by_id(identifier) -> delete_all_by_identifier(identifier)
    """

    @abstractmethod
    async def create_expiry_trigger(
        self, action: str, identifier: str, ttl: timedelta
    ) -> str:
        """
        Create expiry trigger for automated workflow.

        Args:
            action: Action name to trigger when expired (e.g., "reservation_reminder")
            identifier: Unique identifier for this trigger (e.g., transaction_ref)
            ttl: Time until trigger fires

        Returns:
            Trigger key identifier
        """
        pass

    @abstractmethod
    async def delete_expiry_trigger(self, action: str, identifier: str) -> bool:
        """
        Delete specific expiry trigger.

        Args:
            action: Action name of the trigger
            identifier: Unique identifier of the trigger

        Returns:
            True if trigger was deleted
        """
        pass

    @abstractmethod
    async def delete_all_expiry_triggers_by_id(self, identifier: str) -> bool:
        """
        Delete all expiry triggers for a specific identifier.

        Args:
            identifier: Unique identifier to delete all triggers for

        Returns:
            True if triggers were deleted
        """
        pass
