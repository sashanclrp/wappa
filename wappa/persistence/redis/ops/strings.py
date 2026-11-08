"""Redis string (key-value) operations."""

from __future__ import annotations

from ..expiry_keys import is_expiry_index_key
from ..redis_client import PoolAlias, RedisClient
from ._shared import _await_command, logger


async def setex(
    key: str, seconds: int, value: str, *, alias: PoolAlias = "users"
) -> bool:
    """
    Set key to hold string value and set key to timeout after given number of seconds.

    Args:
        key: The full Redis key.
        seconds: Expiration time in seconds.
        value: The string value to store.
        alias: Redis pool alias to use (default: "default").

    Returns:
        True if the operation was successful, False otherwise.
    """
    async with RedisClient.connection(alias=alias) as redis:
        try:
            if not isinstance(value, str | bytes | int | float):
                logger.warning(
                    f"RedisCoreMethods.setex received non-primitive type for key '{key}'. Attempting str conversion. Type: {type(value)}"
                )
                value = str(value)
            return bool(await _await_command(redis.setex(key, seconds, value)))
        except Exception as e:
            logger.error(f"Redis SETEX error for key '{key}': {e}", exc_info=True)
            return False


async def exists(*keys: str, alias: PoolAlias = "users") -> int:
    """
    Returns the number of keys that exist from the list of keys.

    Args:
        *keys: One or more full Redis keys.
        alias: Redis pool alias to use (default: "default").

    Returns:
        Integer reply: The number of keys that exist.
    """
    if not keys:
        return 0
    async with RedisClient.connection(alias=alias) as redis:
        try:
            return await _await_command(redis.exists(*keys))
        except Exception as e:
            logger.error(
                f"Redis EXISTS error for keys starting with '{keys[0]}...': {e}",
                exc_info=True,
            )
            return 0  # Return 0 on error


async def delete(*keys: str, alias: PoolAlias = "users") -> int:
    """
    Delete one or more keys.

    Args:
        *keys: One or more full Redis keys to delete.
        alias: Redis pool alias to use (default: "default").

    Returns:
        The number of keys deleted. Returns 0 on error.
    """
    keys = tuple(key for key in keys if not is_expiry_index_key(key))
    if not keys:
        return 0
    async with RedisClient.connection(alias=alias) as redis:
        try:
            return await _await_command(redis.delete(*keys))
        except Exception as e:
            logger.error(
                f"Redis DELETE error for keys starting with '{keys[0]}...': {e}",
                exc_info=True,
            )
            return 0
