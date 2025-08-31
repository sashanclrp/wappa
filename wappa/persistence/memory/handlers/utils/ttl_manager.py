"""
TTL management utilities for memory cache.

Provides additional TTL management functionality beyond the basic
memory store implementation.
"""

import logging
from datetime import datetime, timedelta

from .memory_store import get_memory_store

logger = logging.getLogger("TTLManager")


class TTLManager:
    """
    Advanced TTL management for memory cache.

    Provides utilities for TTL monitoring, batch operations,
    and advanced expiration handling.
    """

    def __init__(self):
        self.memory_store = get_memory_store()

    async def get_ttl_info(self, namespace: str, context_key: str, key: str) -> dict:
        """
        Get detailed TTL information for a key.

        Args:
            namespace: Cache namespace
            context_key: Context identifier
            key: Cache key

        Returns:
            Dictionary with TTL details
        """
        ttl_seconds = await self.memory_store.get_ttl(namespace, context_key, key)

        info = {
            "key": key,
            "namespace": namespace,
            "context_key": context_key,
            "ttl_seconds": ttl_seconds,
            "status": "unknown",
        }

        if ttl_seconds == -2:
            info["status"] = "not_found"
            info["message"] = "Key does not exist"
        elif ttl_seconds == -1:
            info["status"] = "no_expiry"
            info["message"] = "Key exists with no expiration"
        else:
            info["status"] = "expires"
            info["expires_at"] = datetime.now() + timedelta(seconds=ttl_seconds)
            info["message"] = f"Key expires in {ttl_seconds} seconds"

        return info

    async def extend_ttl(
        self, namespace: str, context_key: str, key: str, additional_seconds: int
    ) -> bool:
        """
        Extend TTL by adding additional seconds to current TTL.

        Args:
            namespace: Cache namespace
            context_key: Context identifier
            key: Cache key
            additional_seconds: Seconds to add to current TTL

        Returns:
            True if successful, False otherwise
        """
        current_ttl = await self.memory_store.get_ttl(namespace, context_key, key)

        if current_ttl == -2:
            # Key doesn't exist
            return False
        elif current_ttl == -1:
            # No current expiry, set new TTL
            return await self.memory_store.set_ttl(
                namespace, context_key, key, additional_seconds
            )
        else:
            # Extend current TTL
            new_ttl = current_ttl + additional_seconds
            return await self.memory_store.set_ttl(namespace, context_key, key, new_ttl)

    async def refresh_ttl(
        self, namespace: str, context_key: str, key: str, ttl_seconds: int
    ) -> bool:
        """
        Refresh TTL to a new value (reset expiration timer).

        Args:
            namespace: Cache namespace
            context_key: Context identifier
            key: Cache key
            ttl_seconds: New TTL in seconds

        Returns:
            True if successful, False otherwise
        """
        return await self.memory_store.set_ttl(namespace, context_key, key, ttl_seconds)

    async def clear_ttl(self, namespace: str, context_key: str, key: str) -> bool:
        """
        Remove TTL from key (make it persistent).

        Note: This is achieved by setting a very long TTL (100 years).

        Args:
            namespace: Cache namespace
            context_key: Context identifier
            key: Cache key

        Returns:
            True if successful, False otherwise
        """
        # Set TTL to 100 years (effectively no expiry)
        very_long_ttl = 100 * 365 * 24 * 3600  # 100 years in seconds
        return await self.memory_store.set_ttl(
            namespace, context_key, key, very_long_ttl
        )

    async def get_expiring_keys(
        self, namespace: str, context_key: str, within_seconds: int = 300
    ) -> list[dict]:
        """
        Get keys that will expire within specified seconds.

        Args:
            namespace: Cache namespace
            context_key: Context identifier
            within_seconds: Time window in seconds (default: 5 minutes)

        Returns:
            List of dictionaries with key info for expiring keys
        """
        expiring_keys = []

        # Get all keys for the context
        all_keys = await self.memory_store.get_all_keys(namespace, context_key)

        for key in all_keys:
            ttl_info = await self.get_ttl_info(namespace, context_key, key)
            if (
                ttl_info["status"] == "expires"
                and ttl_info["ttl_seconds"] <= within_seconds
            ):
                expiring_keys.append(ttl_info)

        return expiring_keys

    async def batch_refresh_ttl(
        self, namespace: str, context_key: str, keys: list[str], ttl_seconds: int
    ) -> dict[str, bool]:
        """
        Refresh TTL for multiple keys in batch.

        Args:
            namespace: Cache namespace
            context_key: Context identifier
            keys: List of cache keys
            ttl_seconds: New TTL in seconds

        Returns:
            Dictionary mapping key -> success status
        """
        results = {}
        for key in keys:
            results[key] = await self.refresh_ttl(
                namespace, context_key, key, ttl_seconds
            )
        return results

    async def get_namespace_stats(self, namespace: str) -> dict:
        """
        Get statistics for a namespace.

        Args:
            namespace: Cache namespace

        Returns:
            Dictionary with namespace statistics
        """
        stats = {
            "namespace": namespace,
            "total_contexts": 0,
            "total_keys": 0,
            "keys_with_ttl": 0,
            "keys_persistent": 0,
            "estimated_cleanup_needed": 0,
        }

        # This would require access to the internal store structure
        # For now, we'll provide basic stats that can be calculated
        # without breaking encapsulation

        try:
            # Access the store directly for stats (this is a utility function)
            store = self.memory_store._store[namespace]
            stats["total_contexts"] = len(store)

            for context_key, context_store in store.items():
                stats["total_keys"] += len(context_store)

                for key in context_store:
                    ttl = await self.memory_store.get_ttl(namespace, context_key, key)
                    if ttl == -1:
                        stats["keys_persistent"] += 1
                    elif ttl >= 0:
                        stats["keys_with_ttl"] += 1
                    else:
                        stats["estimated_cleanup_needed"] += 1

        except Exception as e:
            logger.warning(f"Failed to calculate namespace stats for {namespace}: {e}")

        return stats


# Global TTL manager instance
ttl_manager = TTLManager()
