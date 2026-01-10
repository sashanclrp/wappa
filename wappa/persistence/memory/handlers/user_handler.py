"""
Memory User handler - mirrors Redis user handler functionality.

Provides user-specific cache operations using in-memory storage.
"""

import logging
from typing import Any

from pydantic import BaseModel

from ....domain.interfaces.cache_interfaces import IUserCache
from ..storage_manager import storage_manager
from .utils.key_factory import default_key_factory

logger = logging.getLogger("MemoryUser")


class MemoryUser(IUserCache):
    """
    Memory-based user cache handler.

    Mirrors RedisUser functionality using in-memory storage.
    Maintains the same API for seamless cache backend switching.
    """

    def __init__(self, tenant: str, user_id: str):
        """
        Initialize Memory user handler.

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

    def _key(self) -> str:
        """Build user key using KeyFactory (same as Redis)."""
        return self.keys.user(self.tenant, self.user_id)

    # ---- Public API matching RedisUser ----
    async def get(self, models: type[BaseModel] | None = None) -> dict[str, Any] | None:
        """
        Get full user data.

        Args:
            models: Optional BaseModel class for deserialization

        Returns:
            User data dictionary or BaseModel instance, None if not found
        """
        key = self._key()
        return await storage_manager.get(
            "users", self.tenant, self.user_id, key, models
        )

    async def upsert(
        self, data: dict[str, Any] | BaseModel, ttl: int | None = None
    ) -> bool:
        """
        Create or update user data.

        Args:
            data: User data to store
            ttl: Time to live in seconds

        Returns:
            True if successful, False otherwise
        """
        key = self._key()
        return await storage_manager.set(
            "users", self.tenant, self.user_id, key, data, ttl
        )

    async def delete(self) -> int:
        """
        Delete user data.

        Returns:
            1 if deleted, 0 if didn't exist
        """
        key = self._key()
        success = await storage_manager.delete("users", self.tenant, self.user_id, key)
        return 1 if success else 0

    async def exists(self) -> bool:
        """
        Check if user data exists.

        Returns:
            True if exists, False otherwise
        """
        key = self._key()
        return await storage_manager.exists("users", self.tenant, self.user_id, key)

    async def get_field(self, field: str) -> Any | None:
        """
        Get a specific field from user data.

        Args:
            field: Field name

        Returns:
            Field value or None if not found
        """
        user_data = await self.get()
        if user_data is None:
            return None

        if isinstance(user_data, dict):
            return user_data.get(field)
        else:
            # BaseModel instance
            return getattr(user_data, field, None)

    async def update_field(
        self, field: str, value: Any, ttl: int | None = None
    ) -> bool:
        """
        Update a specific field in user data.

        Args:
            field: Field name
            value: New value
            ttl: Time to live in seconds

        Returns:
            True if successful, False otherwise
        """
        user_data = await self.get()
        if user_data is None:
            user_data = {}

        if isinstance(user_data, BaseModel):
            user_data = user_data.model_dump()

        user_data[field] = value
        return await self.upsert(user_data, ttl)

    async def increment_field(
        self, field: str, increment: int = 1, ttl: int | None = None
    ) -> int | None:
        """
        Atomically increment an integer field.

        Args:
            field: Field name
            increment: Amount to increment by
            ttl: Time to live in seconds

        Returns:
            New value after increment or None on error
        """
        user_data = await self.get()
        if user_data is None:
            user_data = {}

        if isinstance(user_data, BaseModel):
            user_data = user_data.model_dump()

        current_value = user_data.get(field, 0)
        if not isinstance(current_value, int | float):
            logger.warning(
                f"Cannot increment non-numeric field '{field}': {current_value}"
            )
            return None

        new_value = int(current_value) + increment
        user_data[field] = new_value

        success = await self.upsert(user_data, ttl)
        return new_value if success else None

    async def append_to_list(
        self, field: str, value: Any, ttl: int | None = None
    ) -> bool:
        """
        Append value to a list field.

        Args:
            field: Field name containing list
            value: Value to append
            ttl: Time to live in seconds

        Returns:
            True if successful, False otherwise
        """
        user_data = await self.get()
        if user_data is None:
            user_data = {}

        if isinstance(user_data, BaseModel):
            user_data = user_data.model_dump()

        current_list = user_data.get(field, [])
        if not isinstance(current_list, list):
            current_list = []

        current_list.append(value)
        user_data[field] = current_list

        return await self.upsert(user_data, ttl)

    async def get_ttl(self) -> int:
        """
        Get remaining time to live for user data.

        Returns:
            Remaining TTL in seconds, -1 if no expiry, -2 if doesn't exist
        """
        return await storage_manager.get_ttl(
            "users", self.tenant, self.user_id, self._key()
        )

    async def renew_ttl(self, ttl: int) -> bool:
        """
        Renew time to live for user data.

        Args:
            ttl: New time to live in seconds

        Returns:
            True if successful, False otherwise
        """
        return await storage_manager.set_ttl(
            "users", self.tenant, self.user_id, self._key(), ttl
        )
