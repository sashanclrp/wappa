"""
JSON storage manager for coordinating cache operations.

Provides high-level interface for JSON cache operations with TTL support,
BaseModel serialization, and atomic file operations.
"""

import logging
from datetime import datetime
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
    """High-level JSON storage operations manager."""

    def __init__(self):
        # Ensure cache directories exist on initialization
        file_manager.ensure_cache_directories()

    async def get(
        self,
        cache_type: str,
        tenant_id: str,
        user_id: str | None,
        key: str,
        model: type[BaseModel] | None = None,
    ) -> Any:
        """
        Get value from JSON cache.

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
            file_path = file_manager.get_cache_file_path(cache_type, tenant_id, user_id)
            file_data = await file_manager.read_file(file_path)

            if not file_data:
                return None

            # Extract data and check expiration
            cache_data = extract_cache_file_data(file_data)
            if cache_data is None:
                # Expired - delete the file
                await file_manager.delete_file(file_path)
                return None

            # Get specific key data
            if key not in cache_data:
                return None

            value_data = cache_data[key]
            return deserialize_from_json(value_data, model)

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
        Set value in JSON cache.

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
            file_path = file_manager.get_cache_file_path(cache_type, tenant_id, user_id)

            # Read existing data
            file_data = await file_manager.read_file(file_path)
            cache_data = extract_cache_file_data(file_data) if file_data else {}
            if cache_data is None:
                cache_data = {}

            # Update key
            cache_data[key] = serialize_for_json(value)

            # Create new file data with TTL
            new_file_data = create_cache_file_data(cache_data, ttl)

            # Write file
            return await file_manager.write_file(file_path, new_file_data)

        except Exception as e:
            logger.error(f"Failed to set key '{key}' in {cache_type} cache: {e}")
            return False

    async def delete(
        self, cache_type: str, tenant_id: str, user_id: str | None, key: str
    ) -> bool:
        """
        Delete key from JSON cache.

        Args:
            cache_type: "users", "tables", or "states"
            tenant_id: Tenant identifier
            user_id: User identifier (required for users/states)
            key: Cache key to delete

        Returns:
            True if deleted or didn't exist, False on error
        """
        try:
            file_path = file_manager.get_cache_file_path(cache_type, tenant_id, user_id)

            # Read existing data
            file_data = await file_manager.read_file(file_path)
            if not file_data:
                return True  # Already doesn't exist

            cache_data = extract_cache_file_data(file_data)
            if cache_data is None or key not in cache_data:
                return True  # Already doesn't exist

            # Remove key
            del cache_data[key]

            # If no keys left, delete the file
            if not cache_data:
                return await file_manager.delete_file(file_path)

            # Otherwise update file
            new_file_data = create_cache_file_data(cache_data)
            return await file_manager.write_file(file_path, new_file_data)

        except Exception as e:
            logger.error(f"Failed to delete key '{key}' from {cache_type} cache: {e}")
            return False

    async def exists(
        self, cache_type: str, tenant_id: str, user_id: str | None, key: str
    ) -> bool:
        """
        Check if key exists in JSON cache.

        Args:
            cache_type: "users", "tables", or "states"
            tenant_id: Tenant identifier
            user_id: User identifier (required for users/states)
            key: Cache key to check

        Returns:
            True if exists and not expired, False otherwise
        """
        try:
            file_path = file_manager.get_cache_file_path(cache_type, tenant_id, user_id)
            file_data = await file_manager.read_file(file_path)

            if not file_data:
                return False

            cache_data = extract_cache_file_data(file_data)
            if cache_data is None:
                # Expired - delete the file
                await file_manager.delete_file(file_path)
                return False

            return key in cache_data

        except Exception as e:
            logger.error(
                f"Failed to check existence of key '{key}' in {cache_type} cache: {e}"
            )
            return False

    async def get_ttl(
        self, cache_type: str, tenant_id: str, user_id: str | None
    ) -> int:
        """
        Get remaining TTL for cache file.

        Returns:
            Remaining TTL in seconds, -1 if no expiry, -2 if doesn't exist
        """
        try:
            file_path = file_manager.get_cache_file_path(cache_type, tenant_id, user_id)
            file_data = await file_manager.read_file(file_path)

            if not file_data:
                return -2  # Doesn't exist

            metadata = file_data.get("_metadata", {})
            expires_at_str = metadata.get("expires_at")

            if not expires_at_str:
                return -1  # No expiry

            try:
                expires_at = datetime.fromisoformat(expires_at_str)
                now = datetime.now()

                if now >= expires_at:
                    return -2  # Already expired

                return int((expires_at - now).total_seconds())

            except ValueError:
                return -1  # Invalid expiry format, treat as no expiry

        except Exception as e:
            logger.error(f"Failed to get TTL for {cache_type} cache: {e}")
            return -2

    async def set_ttl(
        self, cache_type: str, tenant_id: str, user_id: str | None, ttl: int
    ) -> bool:
        """
        Set TTL for cache file.

        Args:
            ttl: Time to live in seconds

        Returns:
            True if successful, False otherwise
        """
        try:
            file_path = file_manager.get_cache_file_path(cache_type, tenant_id, user_id)
            file_data = await file_manager.read_file(file_path)

            if not file_data:
                return False  # File doesn't exist

            cache_data = extract_cache_file_data(file_data)
            if cache_data is None:
                return False  # Already expired

            # Create new file data with updated TTL
            new_file_data = create_cache_file_data(cache_data, ttl)
            return await file_manager.write_file(file_path, new_file_data)

        except Exception as e:
            logger.error(f"Failed to set TTL for {cache_type} cache: {e}")
            return False

    async def get_all_keys(
        self, cache_type: str, tenant_id: str, user_id: str | None
    ) -> dict[str, Any]:
        """
        Get all keys for a cache file.

        Args:
            cache_type: "users", "tables", or "states"
            tenant_id: Tenant identifier
            user_id: User identifier (required for users/states)

        Returns:
            Dictionary of all non-expired key-value pairs
        """
        try:
            file_path = file_manager.get_cache_file_path(cache_type, tenant_id, user_id)
            file_data = await file_manager.read_file(file_path)

            if not file_data:
                return {}

            cache_data = extract_cache_file_data(file_data)
            if cache_data is None:
                # Expired - delete the file
                await file_manager.delete_file(file_path)
                return {}

            return cache_data

        except Exception as e:
            logger.error(f"Failed to get all keys from {cache_type} cache: {e}")
            return {}


# Global storage manager instance
storage_manager = JSONStorageManager()
