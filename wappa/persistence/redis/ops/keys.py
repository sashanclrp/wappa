"""Redis key operations: scan, TTL, expire and conditional rename."""

from __future__ import annotations

from redis.exceptions import ResponseError

from ..redis_client import PoolAlias, RedisClient
from ._shared import _await_command, logger


async def scan_keys(
    match_pattern: str,
    cursor: str | bytes | int = 0,
    count: int | None = None,
    *,
    alias: PoolAlias = "users",
) -> tuple[int, list[str]]:
    """
    Iterates the key space using the SCAN command.

    Args:
        match_pattern: Glob-style pattern to match keys.
        cursor: The cursor to start iteration from (0 for the first call).
                Can be int or string representation of int. Bytes cursor is also possible if decode_responses=False.
        count: Hint for the number of keys to return per iteration.
        alias: Redis pool alias to use (default: "default").

    Returns:
        A tuple containing:
        - The cursor for the next iteration (string or int, depending on redis-py version and connection settings). 0 indicates iteration is complete.
        - A list of matching key strings found in this iteration.
        Returns (0, []) on error.
    """
    # Ensure cursor is suitable for redis-py call
    # redis-py >= 4.2 prefers int cursor, older versions might use bytes/str
    # Let's try to stick to int/str representation for broader compatibility
    current_cursor = int(cursor)

    async with RedisClient.connection(alias=alias) as redis:
        try:
            # redis-py's scan returns (new_cursor, keys_list)
            # new_cursor type might be int or bytes depending on version/config
            # keys_list should be List[str] if decode_responses=True
            next_cursor, keys_batch = await redis.scan(
                cursor=current_cursor, match=match_pattern, count=count
            )

            # Normalize redis-py's version-dependent cursor representation.
            normalized_cursor = int(next_cursor)

            # Ensure keys are strings (should be if decode_responses=True)
            keys_batch_str = [
                k if isinstance(k, str) else k.decode("utf-8") for k in keys_batch
            ]

            return normalized_cursor, keys_batch_str
        except Exception as e:
            logger.error(
                f"Redis SCAN error for pattern '{match_pattern}' with cursor '{current_cursor}': {e}",
                exc_info=True,
            )
            return 0, []


# =========================================================================
# SECTION: TTL Management
# =========================================================================
async def rename_if_absent(
    key: str, new_key: str, *, alias: PoolAlias = "users"
) -> bool | None:
    """
    Rename a key only when the destination does not exist (RENAMENX).

    The rename is atomic and keeps the key's remaining TTL.

    Args:
        key: The full Redis key to rename.
        new_key: The full destination key.
        alias: Redis pool alias to use (default: "default").

    Returns:
        True when renamed, False when the destination exists (nothing changed),
        None when ``key`` does not exist.
    """
    async with RedisClient.connection(alias=alias) as redis:
        try:
            return bool(await _await_command(redis.renamenx(key, new_key)))
        except ResponseError as e:
            if "no such key" in str(e).lower():
                return None
            logger.error(f"Redis RENAMENX error for key '{key}': {e}", exc_info=True)
            raise


async def get_ttl(key: str, *, alias: PoolAlias = "users") -> int:
    """
    Get remaining Time To Live (TTL) for a key in seconds.

    Args:
        key: The full Redis key.
        alias: Redis pool alias to use (default: "default").

    Returns:
            - TTL in seconds
            - -1 if the key exists but has no associated expire time
            - -2 if the key does not exist or an error occurred.
    """
    async with RedisClient.connection(alias=alias) as redis:
        try:
            return await _await_command(redis.ttl(key))
        except Exception as e:
            logger.error(f"Error getting TTL for key '{key}': {e}")
            return -2  # Consistent with redis-py for errors/non-existent key


async def expire(key: str, ttl: int, *, alias: PoolAlias = "users") -> bool:
    """
    Set a timeout on key in seconds.

    Args:
        key: The full Redis key.
        ttl: Time To Live in seconds.
        alias: Redis pool alias to use (default: "default").

    Returns:
        True if the timeout was set, False if key does not exist or timeout could not be set (or on error).
    """
    async with RedisClient.connection(alias=alias) as redis:
        try:
            # EXPIRE returns 1 if timeout was set, 0 if key doesn't exist or timeout wasn't set
            result = await redis.expire(key, ttl)
            return bool(result)  # Convert 1/0 to True/False
        except Exception as e:
            logger.error(f"Error setting EXPIRE for key '{key}': {e}")
            return False
