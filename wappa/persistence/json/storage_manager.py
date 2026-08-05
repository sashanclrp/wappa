import logging
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from .handlers.utils.file_manager import file_manager
from .handlers.utils.serialization import (
    create_cache_file_data,
    deserialize_from_json,
    extract_cache_file_data,
    serialize_for_json,
)

logger = logging.getLogger("JSONStorageManager")


class JSONStorageManager:
    def __init__(self) -> None:
        file_manager.ensure_cache_directories()

    async def _load_cache_data(
        self, file_path: Path, *, delete_if_expired: bool = True
    ) -> dict[str, Any] | None:
        """Return cache dict, None if file missing or expired (optionally deleting)."""
        file_data = await file_manager.read_file(file_path)
        if not file_data:
            return None
        cache_data = extract_cache_file_data(file_data)
        if cache_data is None:
            if delete_if_expired:
                await file_manager.delete_file(file_path)
            return None
        return cache_data

    async def get(
        self,
        cache_type: str,
        inbox_id: str,
        user_id: str | None,
        key: str,
        model: type[BaseModel] | None = None,
    ) -> Any:
        try:
            file_path = file_manager.get_cache_file_path(cache_type, inbox_id, user_id)
            cache_data = await self._load_cache_data(file_path)
            if cache_data is None or key not in cache_data:
                return None
            return deserialize_from_json(cache_data[key], model)
        except Exception as e:
            logger.error(f"Failed to get key '{key}' from {cache_type} cache: {e}")
            return None

    async def set(
        self,
        cache_type: str,
        inbox_id: str,
        user_id: str | None,
        key: str,
        value: Any,
        ttl: int | None = None,
    ) -> bool:
        try:
            file_path = file_manager.get_cache_file_path(cache_type, inbox_id, user_id)
            file_data = await file_manager.read_file(file_path)
            cache_data = extract_cache_file_data(file_data) if file_data else {}
            if cache_data is None:
                cache_data = {}

            cache_data[key] = serialize_for_json(value)
            return await file_manager.write_file(
                file_path, create_cache_file_data(cache_data, ttl)
            )
        except Exception as e:
            logger.error(f"Failed to set key '{key}' in {cache_type} cache: {e}")
            return False

    async def create_if_absent(
        self,
        cache_type: str,
        inbox_id: str,
        user_id: str | None,
        key: str,
        value: Any,
        ttl: int | None = None,
    ) -> tuple[bool, Any]:
        """Write a key only when the file holds no live entry for it.

        Returns ``(created, existing)``. The read and the write share one file
        lock, so two coroutines cannot both conclude the key was absent.
        """
        file_path = file_manager.get_cache_file_path(cache_type, inbox_id, user_id)
        async with file_manager.locked(file_path):
            cache_data = await self._read_live_data(file_path)
            existing = cache_data.get(key)
            if existing is not None:
                return False, deserialize_from_json(existing)

            cache_data[key] = serialize_for_json(value)
            await file_manager.write_unlocked(
                file_path, create_cache_file_data(cache_data, ttl)
            )
            return True, None

    async def replace_if(
        self,
        cache_type: str,
        inbox_id: str,
        user_id: str | None,
        key: str,
        value: Any,
        matches: Callable[[Any], bool],
        ttl: int | None = None,
    ) -> tuple[str, Any]:
        """Replace a live entry only when ``matches`` accepts the current one.

        Returns ``("replaced" | "condition_not_met" | "missing", current)``. A
        refused replacement writes nothing, so the file's expiry survives it.
        """
        file_path = file_manager.get_cache_file_path(cache_type, inbox_id, user_id)
        async with file_manager.locked(file_path):
            cache_data = await self._read_live_data(file_path)
            stored = cache_data.get(key)
            if stored is None:
                return "missing", None

            current = deserialize_from_json(stored)
            if not matches(current):
                return "condition_not_met", current

            cache_data[key] = serialize_for_json(value)
            await file_manager.write_unlocked(
                file_path, create_cache_file_data(cache_data, ttl)
            )
            return "replaced", None

    async def _read_live_data(self, file_path: Path) -> dict[str, Any]:
        """Read unexpired cache contents while the file lock is already held."""
        file_data = await file_manager.read_unlocked(file_path)
        if not file_data:
            return {}
        return extract_cache_file_data(file_data) or {}

    async def delete(
        self, cache_type: str, inbox_id: str, user_id: str | None, key: str
    ) -> bool:
        try:
            file_path = file_manager.get_cache_file_path(cache_type, inbox_id, user_id)
            file_data = await file_manager.read_file(file_path)
            if not file_data:
                return True

            cache_data = extract_cache_file_data(file_data)
            if cache_data is None or key not in cache_data:
                return True

            del cache_data[key]

            if not cache_data:
                return await file_manager.delete_file(file_path)

            return await file_manager.write_file(
                file_path, create_cache_file_data(cache_data)
            )
        except Exception as e:
            logger.error(f"Failed to delete key '{key}' from {cache_type} cache: {e}")
            return False

    async def exists(
        self, cache_type: str, inbox_id: str, user_id: str | None, key: str
    ) -> bool:
        try:
            file_path = file_manager.get_cache_file_path(cache_type, inbox_id, user_id)
            cache_data = await self._load_cache_data(file_path)
            return cache_data is not None and key in cache_data
        except Exception as e:
            logger.error(
                f"Failed to check existence of key '{key}' in {cache_type} cache: {e}"
            )
            return False

    async def get_ttl(
        self,
        cache_type: str,
        inbox_id: str,
        user_id: str | None,
        key: str | None = None,
    ) -> int:
        try:
            file_path = file_manager.get_cache_file_path(cache_type, inbox_id, user_id)
            file_data = await file_manager.read_file(file_path)

            if not file_data:
                return -2

            expires_at_str = file_data.get("_metadata", {}).get("expires_at")
            if not expires_at_str:
                return -1

            try:
                expires_at = datetime.fromisoformat(expires_at_str)
            except ValueError:
                return -1

            now = datetime.now()
            if now >= expires_at:
                return -2
            return int((expires_at - now).total_seconds())
        except Exception as e:
            logger.error(f"Failed to get TTL for {cache_type} cache: {e}")
            return -2

    async def set_ttl(
        self,
        cache_type: str,
        inbox_id: str,
        user_id: str | None,
        key_or_ttl: str | int,
        ttl: int | None = None,
    ) -> bool:
        try:
            effective_ttl = key_or_ttl if isinstance(key_or_ttl, int) else ttl
            if effective_ttl is None:
                raise ValueError("ttl is required for set_ttl")

            file_path = file_manager.get_cache_file_path(cache_type, inbox_id, user_id)
            cache_data = await self._load_cache_data(file_path, delete_if_expired=False)
            if cache_data is None:
                return False

            return await file_manager.write_file(
                file_path, create_cache_file_data(cache_data, effective_ttl)
            )
        except Exception as e:
            logger.error(f"Failed to set TTL for {cache_type} cache: {e}")
            return False

    async def get_all_keys(
        self, cache_type: str, inbox_id: str, user_id: str | None
    ) -> dict[str, Any]:
        try:
            file_path = file_manager.get_cache_file_path(cache_type, inbox_id, user_id)
            cache_data = await self._load_cache_data(file_path)
            return cache_data or {}
        except Exception as e:
            logger.error(f"Failed to get all keys from {cache_type} cache: {e}")
            return {}


storage_manager = JSONStorageManager()
