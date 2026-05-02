"""
Service for managing user state handler assignments via cache.

This service provides methods to set, retrieve, and delete state handlers
assigned to users through the cache layer. State handlers are used to route
user responses to specific event handlers after messages have been sent.

Identity scoping is delegated to an injected ``IIdentityResolver`` (default
passthrough), so host applications can map transport recipients (phone) to
canonical user ids without modifying framework code. Callers that already
hold a canonical id may pass ``user_id=`` explicitly to bypass the resolver.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from wappa.core.logging.logger import get_logger
from wappa.domain.interfaces.cache_factory import ICacheFactory
from wappa.domain.interfaces.identity_resolver import (
    IIdentityResolver,
    PassthroughIdentityResolver,
)


class HandlerStateService:
    """Service for managing user state handler assignments via cache."""

    STATE_KEY_PREFIX = "api-handler-"

    def __init__(
        self,
        cache_factory: ICacheFactory,
        identity_resolver: IIdentityResolver | None = None,
    ):
        """
        Initialize the handler state service.

        Args:
            cache_factory: Cache factory for creating user-scoped caches.
            identity_resolver: Maps transport recipients to canonical user
                ids for cache scoping. Defaults to passthrough (recipient
                used as-is), preserving pre-0.7.0 behavior.
        """
        self.cache_factory = cache_factory
        self.identity_resolver = identity_resolver or PassthroughIdentityResolver()
        self.logger = get_logger(__name__)

    def _make_state_key(self, handler_value: str) -> str:
        """Create cache key from handler value with API handler prefix."""
        return f"{self.STATE_KEY_PREFIX}{handler_value}"

    async def _resolve_user_id(self, recipient: str, user_id: str | None) -> str:
        """Return explicit ``user_id`` when provided, else resolver output."""
        return user_id or await self.identity_resolver.resolve(recipient)

    async def set_handler_state(
        self,
        recipient: str,
        handler_value: str,
        ttl_seconds: int,
        initial_context: dict[str, Any] | None = None,
        user_id: str | None = None,
    ) -> tuple[str, datetime]:
        """
        Set a state handler for a user using cache.

        The cache entry is keyed under ``user_id`` when provided, otherwise
        under whatever the configured ``IIdentityResolver`` returns for
        ``recipient``. The default resolver returns ``recipient`` unchanged.

        Args:
            recipient: Transport identifier (phone or BSUID).
            handler_value: Unique handler identifier.
            ttl_seconds: Time-to-live in seconds (60-86400).
            initial_context: Optional context data to seed the handler.
            user_id: Optional explicit canonical user id; bypasses resolver.

        Returns:
            Tuple of (cache_key, expiration_datetime).
        """
        cache_user_id = await self._resolve_user_id(recipient, user_id)
        cache_key = self._make_state_key(handler_value)
        expires_at = datetime.now(UTC) + timedelta(seconds=ttl_seconds)

        state_data = {
            "handler_value": handler_value,
            "recipient": recipient,
            "user_id": cache_user_id,
            "assigned_at": datetime.now(UTC).isoformat(),
            "expires_at": expires_at.isoformat(),
            **(initial_context or {}),
        }

        state_cache = self.cache_factory.create_state_cache(user_id=cache_user_id)
        await state_cache.upsert(cache_key, state_data, ttl_seconds)

        self.logger.info(
            f"Handler state set: {cache_key} for user_id={cache_user_id} "
            f"(recipient={recipient}), TTL: {ttl_seconds}s"
        )

        return cache_key, expires_at

    async def get_handler_state(
        self,
        recipient: str,
        handler_value: str,
        user_id: str | None = None,
    ) -> dict[str, Any] | None:
        """
        Get handler state for a user.

        Args:
            recipient: Transport identifier (phone or BSUID).
            handler_value: Unique handler identifier.
            user_id: Optional explicit canonical user id; bypasses resolver.

        Returns:
            State data dictionary if found, None otherwise.
        """
        cache_user_id = await self._resolve_user_id(recipient, user_id)
        cache_key = self._make_state_key(handler_value)
        state_cache = self.cache_factory.create_state_cache(user_id=cache_user_id)
        return await state_cache.get(cache_key)

    async def delete_handler_state(
        self,
        recipient: str,
        handler_value: str,
        user_id: str | None = None,
    ) -> bool:
        """
        Delete handler state for a user.

        Args:
            recipient: Transport identifier (phone or BSUID).
            handler_value: Unique handler identifier.
            user_id: Optional explicit canonical user id; bypasses resolver.

        Returns:
            True if deleted successfully.
        """
        cache_user_id = await self._resolve_user_id(recipient, user_id)
        cache_key = self._make_state_key(handler_value)
        state_cache = self.cache_factory.create_state_cache(user_id=cache_user_id)
        await state_cache.delete(cache_key)

        self.logger.info(
            f"Handler state deleted: {cache_key} for user_id={cache_user_id} "
            f"(recipient={recipient})"
        )
        return True

    async def handler_state_exists(
        self,
        recipient: str,
        handler_value: str,
        user_id: str | None = None,
    ) -> bool:
        """Check if handler state exists for a user."""
        state = await self.get_handler_state(recipient, handler_value, user_id=user_id)
        return state is not None
