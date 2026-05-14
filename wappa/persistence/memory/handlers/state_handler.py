"""
Memory State handler - mirrors Redis state handler functionality.

Provides state cache operations using in-memory storage.
"""

import logging
from typing import Any

from pydantic import BaseModel

from ....domain.interfaces.cache_interfaces import IStateCache
from ..storage_manager import storage_manager
from .utils.key_factory import default_key_factory

logger = logging.getLogger("MemoryStateHandler")


class MemoryStateHandler(IStateCache):
    """
    Memory-based state cache handler.

    Mirrors RedisStateHandler functionality using in-memory storage.
    Maintains the same API for seamless cache backend switching.
    """

    def __init__(self, tenant: str, user_id: str):
        """
        Initialize Memory state handler.

        Args:
            tenant: Tenant identifier
            user_id: User identifier
        """
        if not tenant or not user_id:
            raise ValueError(
                f"Missing required parameters: tenant={tenant}, user_id={user_id}"
            )

        self.tenant = tenant
        self.user_id = user_id
        self.keys = default_key_factory

    def _key(self, handler_name: str) -> str:
        """Build handler key using KeyFactory (same as Redis)."""
        return self.keys.handler(self.tenant, handler_name, self.user_id)

    # ---- Public API matching RedisStateHandler ----
    async def get(
        self, handler_name: str, models: type[BaseModel] | None = None
    ) -> dict[str, Any] | None:
        """
        Get handler state data.

        Args:
            handler_name: Handler name
            models: Optional BaseModel class for deserialization

        Returns:
            Handler state data or None if not found
        """
        key = self._key(handler_name)
        return await storage_manager.get(
            "states", self.tenant, self.user_id, key, models
        )

    async def upsert(
        self,
        handler_name: str,
        data: dict[str, Any] | BaseModel,
        ttl: int | None = None,
    ) -> bool:
        """
        Create or update handler state data.

        Args:
            handler_name: Handler name
            data: State data to store
            ttl: Time to live in seconds

        Returns:
            True if successful, False otherwise
        """
        key = self._key(handler_name)
        return await storage_manager.set(
            "states", self.tenant, self.user_id, key, data, ttl
        )

    async def delete(self, handler_name: str) -> int:
        """
        Delete handler state data.

        Args:
            handler_name: Handler name

        Returns:
            1 if deleted, 0 if didn't exist
        """
        key = self._key(handler_name)
        success = await storage_manager.delete("states", self.tenant, self.user_id, key)
        return 1 if success else 0

    async def exists(self, handler_name: str) -> bool:
        """
        Check if handler state exists.

        Args:
            handler_name: Handler name

        Returns:
            True if exists, False otherwise
        """
        key = self._key(handler_name)
        return await storage_manager.exists("states", self.tenant, self.user_id, key)

    async def get_field(self, handler_name: str, field: str) -> Any | None:
        """
        Get a specific field from handler state.

        Args:
            handler_name: Handler name
            field: Field name

        Returns:
            Field value or None if not found
        """
        state_data = await self.get(handler_name)
        if state_data is None:
            return None

        if isinstance(state_data, dict):
            return state_data.get(field)
        else:
            # BaseModel instance
            return getattr(state_data, field, None)

    async def update_field(
        self,
        handler_name: str,
        field: str,
        value: Any,
        ttl: int | None = None,
    ) -> bool:
        """
        Update a specific field in handler state.

        Args:
            handler_name: Handler name
            field: Field name
            value: New value
            ttl: Time to live in seconds

        Returns:
            True if successful, False otherwise
        """
        state_data = await self.get(handler_name)
        if state_data is None:
            state_data = {}

        if isinstance(state_data, BaseModel):
            state_data = state_data.model_dump()

        state_data[field] = value
        return await self.upsert(handler_name, state_data, ttl)

    async def increment_field(
        self,
        handler_name: str,
        field: str,
        increment: int = 1,
        ttl: int | None = None,
    ) -> int | None:
        """
        Atomically increment an integer field in handler state.

        Args:
            handler_name: Handler name
            field: Field name
            increment: Amount to increment by
            ttl: Time to live in seconds

        Returns:
            New value after increment or None on error
        """
        state_data = await self.get(handler_name)
        if state_data is None:
            state_data = {}

        if isinstance(state_data, BaseModel):
            state_data = state_data.model_dump()

        current_value = state_data.get(field, 0)
        if not isinstance(current_value, int | float):
            logger.warning(
                f"Cannot increment non-numeric field '{field}': {current_value}"
            )
            return None

        new_value = int(current_value) + increment
        state_data[field] = new_value

        success = await self.upsert(handler_name, state_data, ttl)
        return new_value if success else None

    async def append_to_list(
        self,
        handler_name: str,
        field: str,
        value: Any,
        ttl: int | None = None,
    ) -> bool:
        """
        Append value to a list field in handler state.

        Args:
            handler_name: Handler name
            field: Field name containing list
            value: Value to append
            ttl: Time to live in seconds

        Returns:
            True if successful, False otherwise
        """
        state_data = await self.get(handler_name)
        if state_data is None:
            state_data = {}

        if isinstance(state_data, BaseModel):
            state_data = state_data.model_dump()

        current_list = state_data.get(field, [])
        if not isinstance(current_list, list):
            current_list = []

        current_list.append(value)
        state_data[field] = current_list

        return await self.upsert(handler_name, state_data, ttl)

    async def get_ttl(self, handler_name: str) -> int:
        """
        Get remaining time to live for handler state.

        Args:
            handler_name: Handler name identifier

        Returns:
            Remaining TTL in seconds, -1 if no expiry, -2 if doesn't exist
        """
        key = self._key(handler_name)
        return await storage_manager.get_ttl("states", self.tenant, self.user_id, key)

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
        return await storage_manager.set_ttl(
            "states", self.tenant, self.user_id, key, ttl
        )

    async def delete_all_for_user(self) -> int:
        all_keys = await storage_manager.get_all_keys("states", self.tenant, self.user_id)
        for key in all_keys:
            await storage_manager.delete("states", self.tenant, self.user_id, key)
        return len(all_keys)

    async def delete_by_handler_prefix(self, prefix: str) -> int:
        if not prefix:
            raise ValueError("prefix must not be empty")
        all_keys = await storage_manager.get_all_keys("states", self.tenant, self.user_id)
        key_prefix = f"{self.tenant}:{self.keys.handler_prefix}:{prefix}"
        key_suffix = f":{self.user_id}"
        count = 0
        for key in list(all_keys):
            if key.startswith(key_prefix) and key.endswith(key_suffix):
                await storage_manager.delete("states", self.tenant, self.user_id, key)
                count += 1
        return count

    async def list_handlers(self, prefix: str | None = None) -> list[str]:
        all_keys = await storage_manager.get_all_keys("states", self.tenant, self.user_id)
        key_prefix = f"{self.tenant}:{self.keys.handler_prefix}:"
        key_suffix = f":{self.user_id}"
        safe_prefix = prefix or ""
        names = []
        for key in all_keys:
            if key.startswith(key_prefix) and key.endswith(key_suffix):
                name = key[len(key_prefix) : -len(key_suffix)]
                if name.startswith(safe_prefix):
                    names.append(name)
        return names

    @classmethod
    async def list_users_with_handler(cls, tenant_id: str, handler_name: str) -> list[str]:
        from .utils.memory_store import get_memory_store
        from ...redis.redis_handler.utils.key_factory import default_key_factory as kf

        store = get_memory_store()
        key_prefix = f"{tenant_id}:{kf.handler_prefix}:{handler_name}:"
        ctx_prefix = f"{tenant_id}_"
        user_ids: list[str] = []
        async with store._locks["states"]:
            for context_key, context_store in store._store["states"].items():
                if not context_key.startswith(ctx_prefix):
                    continue
                for key in context_store:
                    if key.startswith(key_prefix):
                        user_ids.append(key[len(key_prefix) :])
                        break
        return user_ids
