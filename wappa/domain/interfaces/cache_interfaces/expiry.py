"""Expiry trigger cache interface (composite key: action + identifier)."""

from __future__ import annotations

from abc import ABC, abstractmethod


class ExpiryKeyConflictError(ValueError):
    """A rebind's destination Expiry Key already exists and was left untouched."""


class IExpiryCache(ABC):
    """
    Interface for expiry trigger cache operations.

    Expiry triggers are simple key-value pairs with TTL that fire notifications
    when they expire. Used for time-based automation (reminders, timeouts, etc.).

    The key is composite: (action, identifier)
    - action: Type of trigger (e.g., "payment_reminder")
    - identifier: Unique ID (e.g., "TXN_12345")

    Redis triggers also retain a pending occurrence for at-least-once recovery
    after process restart. The Host handler must keep side effects idempotent.

    Example:
        expiry = RedisExpiry(inbox="myapp", user_id="user123")
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

    # Note: there is deliberately no `delete_all_for_user()` here, unlike
    # IStateCache and IAIStateCache. A trigger key carries an action and an
    # identifier, never a user, so this interface cannot know which triggers a
    # user caused. The method that used to sit here matched
    # `{inbox}:EXPTRIGGER:*:{user_id}` — that is, triggers whose *identifier*
    # happened to be the user id — which is a different meaning under the same
    # name as its siblings. Callers that use the user id as the identifier say
    # so explicitly: `delete_all_by_identifier(cache.user_id)`.

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

    @abstractmethod
    async def rebind(
        self, action: str, old_identifier: str, new_identifier: str
    ) -> bool:
        """
        Move a pending trigger to a new identifier, keeping its remaining TTL.

        Args:
            action: Action name
            old_identifier: Identifier the trigger is armed under
            new_identifier: Identifier it should fire under

        Returns:
            True if a trigger now sits under ``new_identifier``, False if no
            trigger was armed under ``old_identifier``

        Raises:
            ExpiryKeyConflictError: A trigger already exists under
                ``new_identifier``; both keys are left unchanged.
        """
        pass
