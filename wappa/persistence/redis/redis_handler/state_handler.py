from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from ....domain.interfaces.cache_interfaces import IStateCache
from ..ops import hget, hincrby_with_expire, hset
from .utils.serde import dumps
from .utils.tenant_cache import TenantCache

logger = logging.getLogger("RedisStateHandler")


class RedisStateHandler(TenantCache, IStateCache):
    """
    Repository for handler state management.

    Extracted from RedisHandler SECTION: Handler State Management:
    - set_handler_state() -> upsert()
    - get_handler_state() -> get()
    - get_handler_state_field() -> get_field()
    - update_handler_state_field() -> update_field()
    - increment_handler_state_field() -> increment_field()
    - append_to_handler_state_list_field() -> append_to_list()
    - handler_exists() -> exists()
    - delete_handler_state() -> delete()
    - create_or_update_handler() -> merge()

    Single Responsibility: Handler state management only

    Example usage:
        handler = RedisStateHandler(tenant="mimeia", user_id="user123")
        await handler.upsert("chat_handler", {"step": 1, "context": "greeting"})
        state = await handler.get("chat_handler")
    """

    user_id: str = Field(..., min_length=1)
    redis_alias: str = "state_handler"

    def _key(self, handler_name: str) -> str:
        """Build handler key using KeyFactory"""
        return self.keys.handler(self.tenant, handler_name, self.user_id)

    # ---- Public API extracted from RedisHandler Handler methods -------------
    async def get(
        self, handler_name: str, models: type[BaseModel] | None = None
    ) -> dict[str, Any] | None:
        """
        Get full handler state hash (was get_handler_state)

        Args:
            handler_name: Name of the handler
            models: Optional BaseModel class for full object reconstruction
                   e.g., HandlerState (will automatically handle nested HandlerContext, HandlerMetadata)
        """
        key = self._key(handler_name)
        result = await self._get_hash(key, models=models)
        if not result:
            logger.debug(
                f"Handler state not found for '{handler_name}' (user: '{self.user_id}')"
            )
        return result

    async def upsert(
        self, handler_name: str, state_data: dict[str, Any], ttl: int | None = None
    ) -> bool:
        """Set handler state, overwriting existing (Redis HSET upsert behavior)"""
        key = self._key(handler_name)
        return await self._hset_with_ttl(key, state_data, ttl)

    async def get_field(self, handler_name: str, field: str) -> Any | None:
        """Get specific field from handler state (was get_handler_state_field)"""
        key = self._key(handler_name)
        return await hget(key, field, alias=self.redis_alias)

    async def update_field(
        self, handler_name: str, field: str, value: Any, ttl: int | None = None
    ) -> bool:
        """Update single field in handler state"""
        key = self._key(handler_name)

        if ttl:
            # Use inherited method with TTL renewal
            return await self._hset_with_ttl(key, {field: value}, ttl)
        else:
            # Use simple hset without TTL renewal
            serialized_value = dumps(value)
            result = await hset(
                key, field=field, value=serialized_value, alias=self.redis_alias
            )
            return result >= 0

    async def increment_field(
        self, handler_name: str, field: str, increment: int = 1, ttl: int | None = None
    ) -> int | None:
        """Atomically increment integer field (was increment_handler_state_field)"""
        key = self._key(handler_name)

        new_value, expire_res = await hincrby_with_expire(
            key=key,
            field=field,
            increment=increment,
            ttl=ttl or self.ttl_default,
            alias=self.redis_alias,
        )

        if new_value is not None and expire_res:
            return new_value
        else:
            logger.warning(
                f"Failed to increment handler field '{field}' for '{handler_name}' (user: '{self.user_id}')"
            )
            return None

    async def append_to_list(
        self, handler_name: str, field: str, value: Any, ttl: int | None = None
    ) -> bool:
        """Append value to list field (was append_to_handler_state_list_field)"""
        key = self._key(handler_name)
        return await self._append_to_list_field(key, field, value, ttl)

    async def exists(self, handler_name: str) -> bool:
        """Check if handler state exists (was handler_exists)"""
        key = self._key(handler_name)
        return await self.key_exists(key)

    async def delete(self, handler_name: str) -> int:
        """Delete handler state (was delete_handler_state)"""
        key = self._key(handler_name)
        return await self.delete_key(key)

    async def merge(
        self,
        handler_name: str,
        state_data: dict[str, Any],
        ttl: int | None = None,
        models: type[BaseModel] | None = None,
    ) -> dict[str, Any] | None:
        """
        Merge new data with existing state and save (was create_or_update_handler)
        Returns the final merged state or None on failure

        Args:
            handler_name: Name of the handler
            state_data: New state data to merge
            ttl: Optional TTL override
            models: Optional mapping for BaseModel deserialization when reading existing state
        """
        logger.debug(f"Upsert handler '{handler_name}' for user '{self.user_id}'")

        # Get existing state with optional BaseModel deserialization
        existing_state = await self.get(handler_name, models=models) or {}

        # Merge new data with existing
        new_state = {
            **existing_state,
            **state_data,
            "handler_type": handler_name,
            "timestamp": datetime.utcnow().isoformat(),
        }

        # Save merged state
        success = await self.upsert(handler_name, new_state, ttl)

        if success:
            logger.debug(
                f"Successfully upserted handler '{handler_name}' for user '{self.user_id}'"
            )
            return new_state
        else:
            logger.error(
                f"Failed to upsert handler '{handler_name}' for user '{self.user_id}'"
            )
            return None

    async def get_ttl(self, handler_name: str) -> int:
        """
        Get remaining time to live for handler state.

        Args:
            handler_name: Handler name identifier

        Returns:
            Remaining TTL in seconds, -1 if no expiry, -2 if doesn't exist
        """
        key = self._key(handler_name)
        return await super().get_ttl(key)

    async def renew_ttl(self, handler_name: str, ttl: int) -> bool:
        """
        Renew time to live for handler state.

        Args:
            handler_name: Handler name identifier
            ttl: New time to live in seconds

        Returns:
            True if successful, False otherwise
        """
        key = self._key(handler_name)
        return await super().renew_ttl(key, ttl)
