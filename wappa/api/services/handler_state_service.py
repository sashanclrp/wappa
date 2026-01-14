"""
Service for managing user state handler assignments via cache.

This service provides methods to set, retrieve, and delete state handlers
assigned to users through the cache layer. State handlers are used to route
user responses to specific event handlers after messages have been sent.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from wappa.core.logging.logger import get_logger
from wappa.domain.interfaces.cache_factory import ICacheFactory


class HandlerStateService:
    """Service for managing user state handler assignments via cache."""

    STATE_KEY_PREFIX = "api-handler-"

    def __init__(self, cache_factory: ICacheFactory):
        """
        Initialize the handler state service.

        Args:
            cache_factory: Cache factory for creating user-scoped caches
        """
        self.cache_factory = cache_factory
        self.logger = get_logger(__name__)

    def _make_state_key(self, handler_value: str) -> str:
        """
        Create cache key from handler value with API handler prefix.

        This prefix distinguishes API handler states from other state cache entries
        and maintains backward compatibility with existing handler states.

        Args:
            handler_value: Unique handler identifier

        Returns:
            Prefixed cache key (e.g., "api-handler-reschedule_flow")
        """
        return f"{self.STATE_KEY_PREFIX}{handler_value}"

    async def set_handler_state(
        self,
        recipient: str,
        handler_value: str,
        ttl_seconds: int,
        initial_context: dict[str, Any] | None = None,
    ) -> tuple[str, datetime]:
        """
        Set a state handler for a user using cache.

        This creates a state cache entry scoped to the user's phone number.
        The cache entry stores the handler configuration along with any initial context data.

        Args:
            recipient: User phone number
            handler_value: Unique handler identifier
            ttl_seconds: Time-to-live in seconds (60-86400)
            initial_context: Optional context data to initialize the handler with

        Returns:
            Tuple of (cache_key, expiration_datetime)

        Example:
            >>> service = HandlerStateService(cache_factory)
            >>> key, expires = await service.set_handler_state(
            ...     recipient="+1234567890",
            ...     handler_value="reschedule_flow",
            ...     ttl_seconds=3600,
            ...     initial_context={"appointment_id": "12345"}
            ... )
            >>> print(key)
            'api-handler-reschedule_flow'
        """
        cache_key = self._make_state_key(handler_value)
        expires_at = datetime.now(UTC) + timedelta(seconds=ttl_seconds)

        state_data = {
            "handler_value": handler_value,
            "recipient": recipient,
            "assigned_at": datetime.now(UTC).isoformat(),
            "expires_at": expires_at.isoformat(),
            **(initial_context or {}),
        }

        state_cache = self.cache_factory.create_state_cache(user_id=recipient)
        await state_cache.upsert(cache_key, state_data, ttl_seconds)

        self.logger.info(
            f"Handler state set: {cache_key} for {recipient}, TTL: {ttl_seconds}s"
        )

        return cache_key, expires_at

    async def get_handler_state(
        self, recipient: str, handler_value: str
    ) -> dict[str, Any] | None:
        """
        Get handler state for a user.

        Args:
            recipient: User phone number
            handler_value: Unique handler identifier

        Returns:
            State data dictionary if found, None otherwise

        Example:
            >>> state = await service.get_handler_state("+1234567890", "reschedule_flow")
            >>> if state:
            ...     print(state["handler_value"])
            'reschedule_flow'
        """
        cache_key = self._make_state_key(handler_value)
        state_cache = self.cache_factory.create_state_cache(user_id=recipient)
        return await state_cache.get(cache_key)

    async def delete_handler_state(self, recipient: str, handler_value: str) -> bool:
        """
        Delete handler state for a user.

        Args:
            recipient: User phone number
            handler_value: Unique handler identifier

        Returns:
            True if deleted successfully

        Example:
            >>> await service.delete_handler_state("+1234567890", "reschedule_flow")
            True
        """
        cache_key = self._make_state_key(handler_value)
        state_cache = self.cache_factory.create_state_cache(user_id=recipient)
        await state_cache.delete(cache_key)

        self.logger.info(f"Handler state deleted: {cache_key} for {recipient}")

        return True

    async def handler_state_exists(self, recipient: str, handler_value: str) -> bool:
        """
        Check if handler state exists for a user.

        Args:
            recipient: User phone number
            handler_value: Unique handler identifier

        Returns:
            True if handler state exists, False otherwise

        Example:
            >>> exists = await service.handler_state_exists("+1234567890", "reschedule_flow")
            >>> print(exists)
            True
        """
        state = await self.get_handler_state(recipient, handler_value)
        return state is not None
