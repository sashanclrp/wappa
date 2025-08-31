"""
Thread-safe in-memory storage with TTL support.

Provides global singleton memory store with namespace isolation
and automatic expiration cleanup.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

logger = logging.getLogger("MemoryStore")


class MemoryStore:
    """
    Thread-safe in-memory store with TTL support.

    Storage Structure:
    {
        "users": {context_key: {key: (data, expires_at)}},
        "tables": {context_key: {key: (data, expires_at)}},
        "states": {context_key: {key: (data, expires_at)}}
    }

    Where context_key is typically "{tenant_id}_{user_id}" for isolation.
    """

    def __init__(self):
        self._store: dict[str, dict[str, dict[str, tuple[Any, datetime | None]]]] = {
            "users": {},
            "tables": {},
            "states": {},
        }
        self._locks = {
            "users": asyncio.Lock(),
            "tables": asyncio.Lock(),
            "states": asyncio.Lock(),
        }
        self._cleanup_task: asyncio.Task | None = None
        self._cleanup_interval = 300  # 5 minutes

    def start_cleanup_task(self):
        """Start background TTL cleanup task."""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_expired_entries())
            logger.info("Started memory store TTL cleanup task")

    def stop_cleanup_task(self):
        """Stop background TTL cleanup task."""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            logger.info("Stopped memory store TTL cleanup task")

    async def get(self, namespace: str, context_key: str, key: str) -> Any:
        """
        Get value with automatic expiration check.

        Args:
            namespace: Cache namespace ("users", "tables", "states")
            context_key: Context identifier (e.g., "{tenant_id}_{user_id}")
            key: Cache key

        Returns:
            Cached value or None if not found/expired
        """
        if namespace not in self._locks:
            raise ValueError(f"Invalid namespace: {namespace}")

        async with self._locks[namespace]:
            store = self._store[namespace]
            context_store = store.get(context_key, {})

            if key in context_store:
                data, expires_at = context_store[key]
                if expires_at and datetime.now() > expires_at:
                    # Expired, remove and return None
                    del context_store[key]
                    return None
                return data
            return None

    async def set(
        self,
        namespace: str,
        context_key: str,
        key: str,
        data: Any,
        ttl: int | None = None,
    ) -> bool:
        """
        Set value with optional TTL.

        Args:
            namespace: Cache namespace
            context_key: Context identifier
            key: Cache key
            data: Value to store
            ttl: Time to live in seconds

        Returns:
            True if successful, False otherwise
        """
        if namespace not in self._locks:
            raise ValueError(f"Invalid namespace: {namespace}")

        expires_at = None
        if ttl:
            expires_at = datetime.now() + timedelta(seconds=ttl)

        try:
            async with self._locks[namespace]:
                store = self._store[namespace]
                if context_key not in store:
                    store[context_key] = {}
                store[context_key][key] = (data, expires_at)

                # Start cleanup task if not running
                self.start_cleanup_task()
                return True
        except Exception as e:
            logger.error(f"Failed to set key '{key}' in {namespace}: {e}")
            return False

    async def delete(self, namespace: str, context_key: str, key: str) -> bool:
        """
        Delete key from store.

        Args:
            namespace: Cache namespace
            context_key: Context identifier
            key: Cache key

        Returns:
            True if deleted or didn't exist, False on error
        """
        if namespace not in self._locks:
            raise ValueError(f"Invalid namespace: {namespace}")

        try:
            async with self._locks[namespace]:
                store = self._store[namespace]
                context_store = store.get(context_key, {})
                if key in context_store:
                    del context_store[key]
                    # Clean up empty context store
                    if not context_store:
                        del store[context_key]
                return True
        except Exception as e:
            logger.error(f"Failed to delete key '{key}' from {namespace}: {e}")
            return False

    async def exists(self, namespace: str, context_key: str, key: str) -> bool:
        """
        Check if key exists and is not expired.

        Args:
            namespace: Cache namespace
            context_key: Context identifier
            key: Cache key

        Returns:
            True if exists and not expired, False otherwise
        """
        value = await self.get(namespace, context_key, key)
        return value is not None

    async def get_ttl(self, namespace: str, context_key: str, key: str) -> int:
        """
        Get remaining TTL for key.

        Returns:
            Remaining TTL in seconds, -1 if no expiry, -2 if doesn't exist
        """
        if namespace not in self._locks:
            return -2

        async with self._locks[namespace]:
            store = self._store[namespace]
            context_store = store.get(context_key, {})

            if key not in context_store:
                return -2  # Doesn't exist

            data, expires_at = context_store[key]

            if expires_at is None:
                return -1  # No expiry

            now = datetime.now()
            if now >= expires_at:
                # Already expired, clean up
                del context_store[key]
                return -2

            return int((expires_at - now).total_seconds())

    async def set_ttl(
        self, namespace: str, context_key: str, key: str, ttl: int
    ) -> bool:
        """
        Set TTL for existing key.

        Args:
            ttl: Time to live in seconds

        Returns:
            True if successful, False if key doesn't exist or error
        """
        if namespace not in self._locks:
            return False

        try:
            async with self._locks[namespace]:
                store = self._store[namespace]
                context_store = store.get(context_key, {})

                if key not in context_store:
                    return False  # Key doesn't exist

                data, _ = context_store[key]  # Get existing data, ignore old TTL
                expires_at = datetime.now() + timedelta(seconds=ttl)
                context_store[key] = (data, expires_at)
                return True
        except Exception as e:
            logger.error(f"Failed to set TTL for key '{key}' in {namespace}: {e}")
            return False

    async def get_all_keys(self, namespace: str, context_key: str) -> dict[str, Any]:
        """
        Get all non-expired keys for a context.

        Args:
            namespace: Cache namespace
            context_key: Context identifier

        Returns:
            Dictionary of all non-expired key-value pairs
        """
        if namespace not in self._locks:
            return {}

        async with self._locks[namespace]:
            store = self._store[namespace]
            context_store = store.get(context_key, {})

            result = {}
            now = datetime.now()
            expired_keys = []

            for key, (data, expires_at) in context_store.items():
                if expires_at and now > expires_at:
                    expired_keys.append(key)
                else:
                    result[key] = data

            # Clean up expired keys
            for key in expired_keys:
                del context_store[key]

            return result

    async def _cleanup_expired_entries(self):
        """Background task to clean up expired entries."""
        while True:
            try:
                await asyncio.sleep(self._cleanup_interval)

                now = datetime.now()
                total_cleaned = 0

                for namespace in ["users", "tables", "states"]:
                    async with self._locks[namespace]:
                        store = self._store[namespace]
                        empty_contexts = []

                        for context_key, context_store in store.items():
                            expired_keys = []

                            for key, (_, expires_at) in context_store.items():
                                if expires_at and now > expires_at:
                                    expired_keys.append(key)

                            # Remove expired keys
                            for key in expired_keys:
                                del context_store[key]
                                total_cleaned += 1

                            # Mark empty contexts for cleanup
                            if not context_store:
                                empty_contexts.append(context_key)

                        # Remove empty contexts
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
                # Continue running despite errors


# Global singleton memory store instance
_global_memory_store: MemoryStore | None = None


def get_memory_store() -> MemoryStore:
    """Get or create the global memory store singleton."""
    global _global_memory_store
    if _global_memory_store is None:
        _global_memory_store = MemoryStore()
    return _global_memory_store
