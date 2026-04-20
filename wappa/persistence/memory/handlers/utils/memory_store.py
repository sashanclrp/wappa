import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

logger = logging.getLogger("MemoryStore")

_NAMESPACES = ("users", "tables", "states", "ai_states")


class MemoryStore:
    def __init__(self):
        self._store: dict[str, dict[str, dict[str, tuple[Any, datetime | None]]]] = {
            ns: {} for ns in _NAMESPACES
        }
        self._locks = {ns: asyncio.Lock() for ns in _NAMESPACES}
        self._cleanup_task: asyncio.Task | None = None
        self._cleanup_interval = 300  # 5 minutes

    def _require_namespace(self, namespace: str) -> None:
        if namespace not in self._locks:
            raise ValueError(f"Invalid namespace: {namespace}")

    def start_cleanup_task(self):
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_expired_entries())
            logger.info("Started memory store TTL cleanup task")

    def stop_cleanup_task(self):
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            logger.info("Stopped memory store TTL cleanup task")

    async def get(self, namespace: str, context_key: str, key: str) -> Any:
        self._require_namespace(namespace)

        async with self._locks[namespace]:
            context_store = self._store[namespace].get(context_key, {})
            if key not in context_store:
                return None
            data, expires_at = context_store[key]
            if expires_at and datetime.now() > expires_at:
                del context_store[key]
                return None
            return data

    async def set(
        self,
        namespace: str,
        context_key: str,
        key: str,
        data: Any,
        ttl: int | None = None,
    ) -> bool:
        self._require_namespace(namespace)

        expires_at = datetime.now() + timedelta(seconds=ttl) if ttl else None

        try:
            async with self._locks[namespace]:
                store = self._store[namespace]
                store.setdefault(context_key, {})[key] = (data, expires_at)
                self.start_cleanup_task()
                return True
        except Exception as e:
            logger.error(f"Failed to set key '{key}' in {namespace}: {e}")
            return False

    async def delete(self, namespace: str, context_key: str, key: str) -> bool:
        self._require_namespace(namespace)

        try:
            async with self._locks[namespace]:
                store = self._store[namespace]
                context_store = store.get(context_key, {})
                if key in context_store:
                    del context_store[key]
                    if not context_store:
                        del store[context_key]
                return True
        except Exception as e:
            logger.error(f"Failed to delete key '{key}' from {namespace}: {e}")
            return False

    async def exists(self, namespace: str, context_key: str, key: str) -> bool:
        return await self.get(namespace, context_key, key) is not None

    async def get_ttl(self, namespace: str, context_key: str, key: str) -> int:
        if namespace not in self._locks:
            return -2

        async with self._locks[namespace]:
            context_store = self._store[namespace].get(context_key, {})
            if key not in context_store:
                return -2

            _, expires_at = context_store[key]
            if expires_at is None:
                return -1

            now = datetime.now()
            if now >= expires_at:
                del context_store[key]
                return -2
            return int((expires_at - now).total_seconds())

    async def set_ttl(
        self, namespace: str, context_key: str, key: str, ttl: int
    ) -> bool:
        if namespace not in self._locks:
            return False

        try:
            async with self._locks[namespace]:
                context_store = self._store[namespace].get(context_key, {})
                if key not in context_store:
                    return False
                data, _ = context_store[key]
                context_store[key] = (data, datetime.now() + timedelta(seconds=ttl))
                return True
        except Exception as e:
            logger.error(f"Failed to set TTL for key '{key}' in {namespace}: {e}")
            return False

    async def get_all_keys(self, namespace: str, context_key: str) -> dict[str, Any]:
        if namespace not in self._locks:
            return {}

        async with self._locks[namespace]:
            context_store = self._store[namespace].get(context_key, {})
            now = datetime.now()
            result: dict[str, Any] = {}
            expired_keys: list[str] = []

            for key, (data, expires_at) in context_store.items():
                if expires_at and now > expires_at:
                    expired_keys.append(key)
                else:
                    result[key] = data

            for key in expired_keys:
                del context_store[key]

            return result

    async def _cleanup_expired_entries(self):
        while True:
            try:
                await asyncio.sleep(self._cleanup_interval)

                now = datetime.now()
                total_cleaned = 0

                for namespace in _NAMESPACES:
                    async with self._locks[namespace]:
                        store = self._store[namespace]
                        empty_contexts: list[str] = []

                        for context_key, context_store in store.items():
                            expired_keys = [
                                key
                                for key, (_, expires_at) in context_store.items()
                                if expires_at and now > expires_at
                            ]
                            for key in expired_keys:
                                del context_store[key]
                                total_cleaned += 1

                            if not context_store:
                                empty_contexts.append(context_key)

                        for context_key in empty_contexts:
                            del store[context_key]

                if total_cleaned > 0:
                    logger.debug(
                        f"Cleaned up {total_cleaned} expired entries from memory store"
                    )

            except asyncio.CancelledError:
                logger.info("Memory store cleanup task cancelled")
                break
            except Exception as e:
                logger.error(f"Error in memory store cleanup task: {e}")


_global_memory_store: MemoryStore | None = None


def get_memory_store() -> MemoryStore:
    global _global_memory_store
    if _global_memory_store is None:
        _global_memory_store = MemoryStore()
    return _global_memory_store
