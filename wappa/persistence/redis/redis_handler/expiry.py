from __future__ import annotations

import logging

from pydantic import Field

from ....domain.interfaces.cache_interfaces import (
    ExpiryKeyConflictError,
    IExpiryCache,
)
from ..expiry_index import RedisExpiryIndex
from ..ops import exists, get_ttl
from ..redis_client import PoolAlias, RedisClient
from .utils.inbox_cache import InboxCache

logger = logging.getLogger("RedisExpiry")


class RedisExpiry(InboxCache, IExpiryCache):
    """
    Repository for expiry trigger operations.

    Expiry triggers are time-based automation keys that fire notifications
    when they expire. Used for reminders, timeouts, and scheduled actions.

    Key pattern: {inbox}:EXPTRIGGER:{action}:{identifier}
    Example: "wappa:EXPTRIGGER:payment_reminder:TXN_12345"

    When a trigger expires, Redis publishes to __keyevent@{db}__:expired,
    which the expiry listener detects and dispatches to registered handlers.

    Single Responsibility: Expiry trigger lifecycle management only

    Example usage:
        expiry = RedisExpiry(inbox="wappa", user_id="user123")
        # Set trigger that fires in 30 minutes
        await expiry.set("payment_reminder", "TXN_123", ttl_seconds=1800)
        # Check if trigger exists
        exists = await expiry.exists("payment_reminder", "TXN_123")
        # Cancel trigger
        await expiry.delete("payment_reminder", "TXN_123")
    """

    user_id: str = Field(..., min_length=1)
    redis_alias: PoolAlias = "expiry"  # Uses expiry pool (db=3)
    ttl_default: int = 0  # Not used (TTL is per-trigger)

    def _key(self, action: str, identifier: str) -> str:
        """Build trigger key using KeyFactory"""
        return self.keys.trigger(self.inbox, action, identifier)

    # ---- Public API implementing IExpiryCache ------------------------------

    async def set(self, action: str, identifier: str, ttl_seconds: int) -> bool:
        """
        Create expiry trigger with TTL.

        Atomically creates the TTL key and a durable due-index occurrence.
        Redis time sets the deadline; renewal replaces the occurrence generation.

        Args:
            action: Action name (e.g., "payment_reminder")
            identifier: Unique identifier (e.g., "TXN_12345")
            ttl_seconds: Time-to-live in seconds

        Returns:
            True if trigger created successfully, False otherwise

        Example:
            # Create reminder that fires in 25 minutes
            success = await expiry.set("payment_reminder", "TXN_123", 1500)
        """
        key = self._key(action, identifier)
        index = RedisExpiryIndex(await RedisClient.get(self.redis_alias))
        result = await index.arm(key, ttl_seconds)

        if result:
            logger.info(
                f"✓ Expiry trigger created: action='{action}', identifier='{identifier}', "
                f"fires in {ttl_seconds}s"
            )
        else:
            logger.error(
                f"✗ Failed to create expiry trigger: action='{action}', "
                f"identifier='{identifier}'"
            )

        return result

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
            count = await expiry.delete("payment_reminder", "TXN_123")
        """
        key = self._key(action, identifier)

        logger.debug(
            f"Deleting expiry trigger: action='{action}', identifier='{identifier}', "
            f"key='{key}'"
        )

        count = await RedisExpiryIndex(await RedisClient.get(self.redis_alias)).cancel(
            key
        )

        if count > 0:
            logger.info(
                f"✓ Expiry trigger deleted: action='{action}', identifier='{identifier}'"
            )
        else:
            logger.debug(
                f"Expiry trigger not found: action='{action}', identifier='{identifier}'"
            )

        return count

    async def delete_all_by_identifier(self, identifier: str) -> int:
        """
        Delete all triggers for an identifier using pattern match.

        Pattern: {inbox}:EXPTRIGGER:*:{safe_identifier}

        This is useful for cleaning up all triggers related to a transaction
        when it's cancelled or completed.

        Args:
            identifier: Unique identifier

        Returns:
            Number of triggers deleted

        Example:
            # Delete all triggers for transaction (reminder, expiry, etc.)
            count = await expiry.delete_all_by_identifier("TXN_123")
        """
        pattern = self.keys.trigger_pattern(self.inbox, ident=identifier)

        logger.debug(
            f"Deleting all expiry triggers for identifier '{identifier}' "
            f"(pattern: '{pattern}')"
        )

        count = await RedisExpiryIndex(
            await RedisClient.get(self.redis_alias)
        ).cancel_matching(pattern)

        if count > 0:
            logger.info(
                f"✓ Deleted {count} expiry trigger(s) for identifier '{identifier}'"
            )
        else:
            logger.debug(f"No expiry triggers found for identifier '{identifier}'")

        return count

    async def exists(self, action: str, identifier: str) -> bool:
        """
        Check if trigger exists (hasn't fired yet).

        Args:
            action: Action name
            identifier: Unique identifier

        Returns:
            True if trigger exists, False otherwise

        Example:
            if await expiry.exists("payment_reminder", "TXN_123"):
                print("Reminder is still scheduled")
        """
        key = self._key(action, identifier)
        return await exists(key, alias=self.redis_alias) > 0

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
            ttl = await expiry.get_ttl("payment_reminder", "TXN_123")
            if ttl > 0:
                print(f"Reminder fires in {ttl} seconds")
            elif ttl == -1:
                print("Trigger not found (may have already fired)")
        """
        key = self._key(action, identifier)
        return await get_ttl(key, alias=self.redis_alias)

    async def rebind(
        self, action: str, old_identifier: str, new_identifier: str
    ) -> bool:
        """
        Move a pending trigger to a new identifier, keeping its remaining TTL.

        For Host identity changes: the Host supplies the authoritative old and
        new identifiers and calls this once per action it arms. The trigger fires
        on time, under the new identifier. Atomic, including the durable due-index occurrence.

        Args:
            action: Action name
            old_identifier: Identifier the trigger is armed under
            new_identifier: Identifier it should fire under

        Returns:
            True if a trigger now sits under ``new_identifier``, False if no
            trigger was armed under ``old_identifier``

        Raises:
            ExpiryKeyConflictError: A trigger already exists under
                ``new_identifier``. Both keys are left unchanged; the Host decides
                which one to keep.
        """
        old_key = self._key(action, old_identifier)
        new_key = self._key(action, new_identifier)
        if old_key == new_key:
            return await exists(old_key, alias=self.redis_alias) > 0

        renamed = await RedisExpiryIndex(
            await RedisClient.get(self.redis_alias)
        ).rebind(old_key, new_key)
        if renamed == -1:
            raise ExpiryKeyConflictError(
                f"Expiry trigger already exists for action '{action}' under "
                f"identifier '{new_identifier}'"
            )
        return renamed == 1
