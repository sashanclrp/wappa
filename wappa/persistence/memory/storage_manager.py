"""
Memory storage manager for coordinating cache operations.

Provides high-level interface for memory cache operations with TTL support,
BaseModel serialization, and thread-safe operations.
"""

import logging
from typing import Any

from pydantic import BaseModel

from .handlers.utils.memory_store import get_memory_store

logger = logging.getLogger("MemoryStorageManager")


class MemoryStorageManager:
    """High-level memory storage operations manager."""

    def __init__(self):
        self.memory_store = get_memory_store()

    def _serialize_data(self, data: Any) -> Any:
        """Serialize data for memory storage (BaseModel -> dict)."""
        if isinstance(data, BaseModel):
            return data.model_dump()
        return data

    def _deserialize_data(self, data: Any, model: type[BaseModel] | None = None) -> Any:
        """Deserialize data from memory storage."""
        if data is None:
            return None

        if model is not None and isinstance(data, dict):
            return model.model_validate(data)

        return data

    async def get(
        self,
        cache_type: str,
        tenant_id: str,
        user_id: str | None,
        key: str,
        model: type[BaseModel] | None = None,
    ) -> Any:
        """
        Get value from memory cache.

        Args:
            cache_type: "users", "tables", or "states"
            tenant_id: Tenant identifier
            user_id: User identifier (required for users/states)
            key: Cache key
            model: Optional BaseModel for deserialization

        Returns:
            Cached value or None if not found/expired
        """
        try:
            context_key = self._build_context_key(cache_type, tenant_id, user_id)
            data = await self.memory_store.get(cache_type, context_key, key)
            return self._deserialize_data(data, model)
        except Exception as e:
            logger.error(f"Failed to get key '{key}' from {cache_type} cache: {e}")
            return None

    async def set(
        self,
        cache_type: str,
        tenant_id: str,
        user_id: str | None,
        key: str,
        value: Any,
        ttl: int | None = None,
    ) -> bool:
        """
        Set value in memory cache.

        Args:
            cache_type: "users", "tables", or "states"
            tenant_id: Tenant identifier
            user_id: User identifier (required for users/states)
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds

        Returns:
            True if successful, False otherwise
        """
        try:
            context_key = self._build_context_key(cache_type, tenant_id, user_id)
            serialized_value = self._serialize_data(value)
            return await self.memory_store.set(
                cache_type, context_key, key, serialized_value, ttl
            )
        except Exception as e:
            logger.error(f"Failed to set key '{key}' in {cache_type} cache: {e}")
            return False

    async def delete(
        self, cache_type: str, tenant_id: str, user_id: str | None, key: str
    ) -> bool:
        """
        Delete key from memory cache.

        Args:
            cache_type: "users", "tables", or "states"
            tenant_id: Tenant identifier
            user_id: User identifier (required for users/states)
            key: Cache key to delete

        Returns:
            True if deleted or didn't exist, False on error
        """
        try:
            context_key = self._build_context_key(cache_type, tenant_id, user_id)
            return await self.memory_store.delete(cache_type, context_key, key)
        except Exception as e:
            logger.error(f"Failed to delete key '{key}' from {cache_type} cache: {e}")
            return False

    async def exists(
        self, cache_type: str, tenant_id: str, user_id: str | None, key: str
    ) -> bool:
        """
        Check if key exists in memory cache.

        Args:
            cache_type: "users", "tables", or "states"
            tenant_id: Tenant identifier
            user_id: User identifier (required for users/states)
            key: Cache key to check

        Returns:
            True if exists and not expired, False otherwise
        """
        try:
            context_key = self._build_context_key(cache_type, tenant_id, user_id)
            return await self.memory_store.exists(cache_type, context_key, key)
        except Exception as e:
            logger.error(
                f"Failed to check existence of key '{key}' in {cache_type} cache: {e}"
            )
            return False

    async def get_ttl(
        self, cache_type: str, tenant_id: str, user_id: str | None, key: str
    ) -> int:
        """
        Get remaining TTL for key.

        Returns:
            Remaining TTL in seconds, -1 if no expiry, -2 if doesn't exist
        """
        try:
            context_key = self._build_context_key(cache_type, tenant_id, user_id)
            return await self.memory_store.get_ttl(cache_type, context_key, key)
        except Exception as e:
            logger.error(
                f"Failed to get TTL for key '{key}' in {cache_type} cache: {e}"
            )
            return -2

    async def set_ttl(
        self, cache_type: str, tenant_id: str, user_id: str | None, key: str, ttl: int
    ) -> bool:
        """
        Set TTL for key.

        Args:
            ttl: Time to live in seconds

        Returns:
            True if successful, False otherwise
        """
        try:
            context_key = self._build_context_key(cache_type, tenant_id, user_id)
            return await self.memory_store.set_ttl(cache_type, context_key, key, ttl)
        except Exception as e:
            logger.error(
                f"Failed to set TTL for key '{key}' in {cache_type} cache: {e}"
            )
            return False

    async def get_all_keys(
        self, cache_type: str, tenant_id: str, user_id: str | None
    ) -> dict[str, Any]:
        """
        Get all keys for a context.

        Args:
            cache_type: "users", "tables", or "states"
            tenant_id: Tenant identifier
            user_id: User identifier (required for users/states)

        Returns:
            Dictionary of all non-expired key-value pairs
        """
        try:
            context_key = self._build_context_key(cache_type, tenant_id, user_id)
            return await self.memory_store.get_all_keys(cache_type, context_key)
        except Exception as e:
            logger.error(f"Failed to get all keys from {cache_type} cache: {e}")
            return {}

    def _build_context_key(
        self, cache_type: str, tenant_id: str, user_id: str | None
    ) -> str:
        """Build context key for isolation."""
        if cache_type == "tables":
            # Tables only use tenant_id for context
            return tenant_id
        elif cache_type in ["users", "states"]:
            # Users and states use tenant_id and user_id
            if not user_id:
                raise ValueError(f"user_id is required for {cache_type} cache")
            return f"{tenant_id}_{user_id}"
        else:
            raise ValueError(f"Invalid cache_type: {cache_type}")


# Global storage manager instance
storage_manager = MemoryStorageManager()
