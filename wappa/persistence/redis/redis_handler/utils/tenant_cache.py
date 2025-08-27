from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from ...ops import (
    delete,
    exists,
    expire,
    get_ttl,
    hget,
    hgetall,
    hset_with_expire,
    scan_keys,
)
from ...redis_client import PoolAlias
from .key_factory import KeyFactory
from .serde import dumps, dumps_hash, loads, loads_hash

logger = logging.getLogger("TenantCache")


class TenantCache(BaseModel):
    """
    Base class shared by all Wappa cache repositories.
    Handles tenant context, TTL management, and common Redis operations.

    Provides common functionality for cache repositories:
    - Tenant key building and namespace management
    - TTL management and automatic expiration
    - Common serialization patterns for cache data
    """

    tenant: str = Field(..., min_length=1)
    ttl_default: int = 86400  # 24 hours
    redis_alias: PoolAlias = "state_handler"  # Default pool
    keys: KeyFactory = Field(default_factory=KeyFactory)

    model_config = {"arbitrary_types_allowed": True}

    # --------- Low-level helpers extracted from RedisHandler ------------------
    async def _hset_with_ttl(
        self,
        key: str,
        data: dict[str, Any],
        ttl: int | None = None,
        *,
        alias: PoolAlias | None = None,
    ) -> bool:
        """Helper for atomic hash set with expiration"""
        _alias = alias or self.redis_alias
        payload = dumps_hash(data)
        if not payload:
            logger.warning(f"Setting key '{key}' with empty data. Deleting instead.")
            return await delete(key, alias=_alias) >= 0

        hset_res, expire_res = await hset_with_expire(
            key, payload, ttl or self.ttl_default, alias=_alias
        )
        success = hset_res is not None and expire_res
        if not success:
            logger.warning(
                f"Failed hset_with_expire for key '{key}'. HSET: {hset_res}, EXPIRE: {expire_res}"
            )
        return success

    async def _get_hash(
        self,
        key: str,
        models: type[BaseModel] | None = None,
        *,
        alias: PoolAlias | None = None,
    ) -> dict[str, Any] | None:
        """
        Helper to get and deserialize hash data

        Args:
            key: Redis key
            models: Optional BaseModel class for full object reconstruction
                   e.g., User (will automatically handle nested UserProfile, UserSettings)
            alias: Redis pool alias to use (defaults to self.redis_alias)
        """
        _alias = alias or self.redis_alias
        raw_data = await hgetall(key, alias=_alias)
        return loads_hash(raw_data, models=models) if raw_data else None

    async def _find_by_field(
        self,
        pattern: str,
        field: str,
        value: Any,
        models: type[BaseModel] | None = None,
        *,
        alias: PoolAlias | None = None,
    ) -> dict[str, Any] | None:
        """
        Find first hash matching pattern where field equals value.
        Extracted from _find_hash_by_field_internal in RedisHandler.

        Args:
            pattern: Redis key pattern to search
            field: Field name to match
            value: Value to match
            models: Optional mapping for BaseModel deserialization
            alias: Redis pool alias to use (defaults to self.redis_alias)
        """
        _alias = alias or self.redis_alias
        compare_value_str = dumps(value)
        logger.debug(
            f"Searching pattern '{pattern}' where field '{field}' == '{compare_value_str}'"
        )

        cursor = "0"
        try:
            while True:
                next_cursor, keys_batch = await scan_keys(
                    match_pattern=pattern, cursor=cursor, count=100, alias=_alias
                )

                for full_key in keys_batch:
                    current_value_str = await hget(full_key, field, alias=_alias)
                    if current_value_str == compare_value_str:
                        logger.info(
                            f"Match found for field '{field}' in key '{full_key}'"
                        )
                        return await self._get_hash(
                            full_key, models=models, alias=alias
                        )

                if next_cursor == "0":
                    logger.debug(
                        f"SCAN finished for pattern '{pattern}'. No match found."
                    )
                    return None
                cursor = next_cursor
        except Exception as e:
            logger.error(
                f"Error during find_by_field (pattern='{pattern}', field='{field}'): {e}",
                exc_info=True,
            )
            return None

    async def _delete_by_pattern(
        self, pattern: str, *, alias: PoolAlias | None = None
    ) -> int:
        """
        Delete all keys matching pattern.
        Extracted from _delete_keys_by_pattern_internal in RedisHandler.

        Args:
            pattern: Redis key pattern to delete
            alias: Redis pool alias to use (defaults to self.redis_alias)
        """
        _alias = alias or self.redis_alias
        total_deleted = 0
        cursor = "0"

        logger.debug(f"Deleting keys matching pattern '{pattern}'")
        try:
            while True:
                next_cursor, keys_batch = await scan_keys(
                    match_pattern=pattern, cursor=cursor, count=100, alias=_alias
                )

                if keys_batch:
                    logger.debug(f"Deleting batch of {len(keys_batch)} keys")
                    deleted_in_batch = await delete(*keys_batch, alias=_alias)
                    if deleted_in_batch >= 0:
                        total_deleted += deleted_in_batch

                if next_cursor == "0":
                    break
                cursor = next_cursor

            logger.info(f"Deleted {total_deleted} keys for pattern '{pattern}'")
        except Exception as e:
            logger.error(
                f"Error during delete_by_pattern '{pattern}': {e}", exc_info=True
            )

        return total_deleted

    async def _append_to_list_field(
        self,
        key: str,
        field: str,
        value: Any,
        ttl: int | None = None,
        *,
        alias: PoolAlias | None = None,
    ) -> bool:
        """
        Append to a list stored in a hash field.
        Extracted from _append_to_list_in_hash_field in RedisHandler.

        Args:
            key: Redis key
            field: Hash field name
            value: Value to append to the list
            ttl: Optional TTL override
            alias: Redis pool alias to use (defaults to self.redis_alias)
        """
        _alias = alias or self.redis_alias
        try:
            # Get current value
            current_raw = await hget(key, field, alias=_alias)
            current_list = []

            if current_raw:
                try:
                    deserialized = loads(current_raw)
                    if isinstance(deserialized, list):
                        current_list = deserialized
                    else:
                        logger.warning(
                            f"Field '{field}' in '{key}' is not a list. Overwriting."
                        )
                except Exception as e:
                    logger.warning(f"Could not deserialize list field '{field}': {e}")

            # Append and serialize
            current_list.append(value)
            serialized_list = dumps(current_list)

            # Write back atomically
            hset_res, expire_res = await hset_with_expire(
                key=key,
                mapping={field: serialized_list},
                ttl=ttl or self.ttl_default,
                alias=_alias,
            )

            success = hset_res is not None and expire_res
            if not success:
                logger.warning(f"Failed list append for field '{field}' in '{key}'")
            return success

        except Exception as e:
            logger.error(
                f"Error in append_to_list_field '{field}' in '{key}': {e}",
                exc_info=True,
            )
            return False

    # --------- Utility methods -----------------------------------------------
    async def key_exists(self, key: str, *, alias: PoolAlias | None = None) -> bool:
        """Check if key exists"""
        _alias = alias or self.redis_alias
        return await exists(key, alias=_alias) > 0

    async def renew_ttl(
        self, key: str, ttl: int | None = None, *, alias: PoolAlias | None = None
    ) -> bool:
        """Renew TTL for a key"""
        _alias = alias or self.redis_alias
        return await expire(key, ttl or self.ttl_default, alias=_alias)

    async def get_ttl(self, key: str, *, alias: PoolAlias | None = None) -> int:
        """Get remaining TTL for a key"""
        _alias = alias or self.redis_alias
        return await get_ttl(key, alias=_alias)

    async def delete_key(self, key: str, *, alias: PoolAlias | None = None) -> int:
        """Delete a key"""
        _alias = alias or self.redis_alias
        return await delete(key, alias=_alias)
