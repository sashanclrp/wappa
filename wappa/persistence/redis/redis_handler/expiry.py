from __future__ import annotations

import logging
from datetime import datetime, timezone

from pydantic import Field

from ....domain.interfaces.cache_interfaces import IExpiryCache
from ..ops import delete, exists, get_ttl, setex
from .utils.serde import dumps
from .utils.tenant_cache import TenantCache

logger = logging.getLogger("RedisExpiry")


class RedisExpiry(TenantCache, IExpiryCache):
    """
    Repository for expiry trigger operations.

    Expiry triggers are time-based automation keys that fire notifications
    when they expire. Used for reminders, timeouts, and scheduled actions.

    Key pattern: {tenant}:EXPTRIGGER:{action}:{identifier}
    Example: "wappa:EXPTRIGGER:payment_reminder:TXN_12345"

    When a trigger expires, Redis publishes to __keyevent@{db}__:expired,
    which the expiry listener detects and dispatches to registered handlers.

    Single Responsibility: Expiry trigger lifecycle management only

    Example usage:
        expiry = RedisExpiry(tenant="wappa", user_id="user123")
        # Set trigger that fires in 30 minutes
        await expiry.set("payment_reminder", "TXN_123", ttl_seconds=1800)
        # Check if trigger exists
        exists = await expiry.exists("payment_reminder", "TXN_123")
        # Cancel trigger
        await expiry.delete("payment_reminder", "TXN_123")
    """

    user_id: str = Field(..., min_length=1)
    redis_alias: str = "expiry"  # Uses expiry pool (db=3)
    ttl_default: int = 0  # Not used (TTL is per-trigger)

    def _key(self, action: str, identifier: str) -> str:
        """Build trigger key using KeyFactory"""
        return self.keys.trigger(self.tenant, action, identifier)

    # ---- Public API implementing IExpiryCache ------------------------------

    async def set(self, action: str, identifier: str, ttl_seconds: int) -> bool:
        """
        Create expiry trigger with TTL.

        Uses SETEX for atomic key creation with TTL. Value stores creation
        timestamp for debugging/auditing but is not used functionally.

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
        value = f"trigger:{datetime.now(timezone.utc).isoformat()}"
        serialized_value = dumps(value)

        logger.debug(
            f"Creating expiry trigger: action='{action}', identifier='{identifier}', "
            f"ttl={ttl_seconds}s, key='{key}'"
        )

        # SETEX: Set key with expiry in single atomic operation
        result = await setex(
            key=key,
            seconds=ttl_seconds,
            value=serialized_value,
            alias=self.redis_alias,
        )

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

        count = await delete(key, alias=self.redis_alias)

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

        Pattern: {tenant}:EXPTRIGGER:*:{safe_identifier}

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
        safe_ident = identifier.replace(":", "_")
        pattern = f"{self.tenant}:{self.keys.trigger_prefix}:*:{safe_ident}"

        logger.debug(
            f"Deleting all expiry triggers for identifier '{identifier}' "
            f"(pattern: '{pattern}')"
        )

        count = await self._delete_by_pattern(pattern)

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
        return await exists(key, alias=self.redis_alias)

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
