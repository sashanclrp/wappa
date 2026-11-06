"""Redis hash operations."""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from ..redis_client import PoolAlias, RedisClient
from ._shared import _await_command, logger


async def hset(
    key: str,
    field: str | None = None,
    value: str | None = None,
    mapping: Mapping[str, str] | None = None,
    *,
    alias: PoolAlias = "users",
) -> int:
    """
    Sets field in the hash stored at key to value.
    If mapping is provided, sets multiple fields and values.

    Args:
        key: The full Redis key of the hash.
        field: The field name (required if mapping is None).
        value: The string value for the field (required if mapping is None).
        mapping: A dictionary of field-value pairs (must be str:str).
        alias: Redis pool alias to use (default: "default").

    Returns:
        Integer reply: The number of fields that were added.
        Returns -1 on error or invalid arguments.
    """
    if mapping is None and (field is None or value is None):
        logger.error(
            f"HSET requires either 'field' and 'value', or 'mapping' for key '{key}'"
        )
        return -1  # Indicate error due to invalid arguments
    if mapping is not None and (field is not None or value is not None):
        logger.warning(
            f"HSET called with both ('field', 'value') and 'mapping' for key '{key}'. Using 'mapping'."
        )
        # Prioritize mapping if both are provided, clear field/value

    async with RedisClient.connection(alias=alias) as redis:
        try:
            # redis-py's hset handles both single field/value and mapping
            if mapping:
                # Ensure mapping values are strings (or bytes/int/float)
                checked_mapping = {}
                for k, v in mapping.items():
                    if not isinstance(v, str | bytes | int | float):
                        logger.warning(
                            f"RedisCoreMethods.hset received non-primitive type for field '{k}' in mapping for key '{key}'. Attempting str conversion. Type: {type(v)}"
                        )
                        checked_mapping[k] = str(v)
                    else:
                        checked_mapping[k] = v  # Keep original primitive type
                return await _await_command(redis.hset(key, mapping=checked_mapping))
            else:
                # Handle single field/value
                if not isinstance(value, str | bytes | int | float):
                    logger.warning(
                        f"RedisCoreMethods.hset received non-primitive type for field '{field}' for key '{key}'. Attempting str conversion. Type: {type(value)}"
                    )
                    value_to_set = str(value)
                else:
                    value_to_set = value
                # Use the non-mapping version of hset call
                # Note: redis-py hset changed signature; mapping is preferred, but single key/value works
                # Forcing mapping approach for consistency:
                return await _await_command(
                    redis.hset(key, mapping={field: value_to_set})
                )
                # Older way (might vary by redis-py version): return await redis.hset(key, field, value_to_set)
        except Exception as e:
            logger.error(f"Redis HSET error for key '{key}': {e}", exc_info=True)
            return -1  # Indicate error


async def hget(key: str, field: str, *, alias: PoolAlias = "users") -> str | None:
    """
    Gets the string value of a hash field.

    Args:
        key: The full Redis key of the hash.
        field: The field name.
        alias: Redis pool alias to use (default: "default").

    Returns:
        The string value of the field, or None if the field or key doesn't exist, or on error.
    """
    async with RedisClient.connection(alias=alias) as redis:
        try:
            # Assumes decode_responses=True
            return cast(str | None, await _await_command(redis.hget(key, field)))
        except Exception as e:
            logger.error(f"Redis HGET error for key '{key}', field '{field}': {e}")
            return None


async def hgetall(key: str, *, alias: PoolAlias = "users") -> dict[str, str]:
    """
    Gets all fields and values stored in a hash.

    Args:
        key: The full Redis key of the hash.
        alias: Redis pool alias to use (default: "default").

    Returns:
        A dictionary mapping field names to string values. Returns an empty dict
        if the key doesn't exist or on error.
    """
    async with RedisClient.connection(alias=alias) as redis:
        try:
            # Assumes decode_responses=True, returns Dict[str, str]
            return cast(dict[str, str], await _await_command(redis.hgetall(key)))
        except Exception as e:
            logger.error(f"Redis HGETALL error for key '{key}': {e}", exc_info=True)
            return {}


async def hdel(key: str, *fields: str, alias: PoolAlias = "users") -> int:
    """
    Deletes one or more hash fields.

    Args:
        key: The full Redis key of the hash.
        *fields: One or more field names to delete.
        alias: Redis pool alias to use (default: "default").

    Returns:
        The number of fields that were removed from the hash (0 if the key doesn't exist or on error).
    """
    if not fields:
        return 0
    async with RedisClient.connection(alias=alias) as redis:
        try:
            return await _await_command(redis.hdel(key, *fields))
        except Exception as e:
            logger.error(f"Redis HDEL error for key '{key}', fields '{fields}': {e}")
            return 0
