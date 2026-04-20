import logging
from typing import Any

from pydantic import BaseModel

from .handlers.utils.memory_store import get_memory_store

logger = logging.getLogger("MemoryStorageManager")


class MemoryStorageManager:
    def __init__(self):
        self.memory_store = get_memory_store()

    @staticmethod
    def _serialize_data(data: Any) -> Any:
        return data.model_dump() if isinstance(data, BaseModel) else data

    @staticmethod
    def _deserialize_data(data: Any, model: type[BaseModel] | None = None) -> Any:
        if data is None:
            return None
        if model is not None and isinstance(data, dict):
            return model.model_validate(data)
        return data

    @staticmethod
    def _build_context_key(cache_type: str, tenant_id: str, user_id: str | None) -> str:
        if cache_type == "tables":
            return tenant_id
        if cache_type in {"users", "states", "ai_states"}:
            if not user_id:
                raise ValueError(f"user_id is required for {cache_type} cache")
            return f"{tenant_id}_{user_id}"
        raise ValueError(f"Invalid cache_type: {cache_type}")

    async def get(
        self,
        cache_type: str,
        tenant_id: str,
        user_id: str | None,
        key: str,
        model: type[BaseModel] | None = None,
    ) -> Any:
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
        try:
            context_key = self._build_context_key(cache_type, tenant_id, user_id)
            return await self.memory_store.set(
                cache_type, context_key, key, self._serialize_data(value), ttl
            )
        except Exception as e:
            logger.error(f"Failed to set key '{key}' in {cache_type} cache: {e}")
            return False

    async def delete(
        self, cache_type: str, tenant_id: str, user_id: str | None, key: str
    ) -> bool:
        try:
            context_key = self._build_context_key(cache_type, tenant_id, user_id)
            return await self.memory_store.delete(cache_type, context_key, key)
        except Exception as e:
            logger.error(f"Failed to delete key '{key}' from {cache_type} cache: {e}")
            return False

    async def exists(
        self, cache_type: str, tenant_id: str, user_id: str | None, key: str
    ) -> bool:
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
        try:
            context_key = self._build_context_key(cache_type, tenant_id, user_id)
            return await self.memory_store.get_all_keys(cache_type, context_key)
        except Exception as e:
            logger.error(f"Failed to get all keys from {cache_type} cache: {e}")
            return {}


storage_manager = MemoryStorageManager()
