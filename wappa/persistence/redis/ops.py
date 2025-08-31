# mimeiapify/symphony_ai/redis/ops.py

import builtins
import logging
from collections.abc import Mapping, Sequence

from .redis_client import PoolAlias, RedisClient

logger = logging.getLogger(
    "RedisCoreMethods"
)  # Use __name__ for standard logging practice


# =========================================================================
# SECTION: Basic Key-Value Operations
# =========================================================================
async def set(
    key: str, value: str, ex: int | None = None, *, alias: PoolAlias = "default"
) -> bool:
    """
    Sets the string value of a key, with optional expiration.

    Args:
        key: The full Redis key.
        value: The string value to store.
        ex: Optional expiration time in seconds.
        alias: Redis pool alias to use (default: "default").

    Returns:
        True if the operation was successful, False otherwise.
    """
    async with RedisClient.connection(alias=alias) as redis:
        try:
            # Ensure value is a type redis-py can handle directly (str, bytes, int, float)
            # Assuming decode_responses=True, strings are preferred.
            if not isinstance(value, str | bytes | int | float):
                # Log a warning if a complex type is passed unexpectedly
                logger.warning(
                    f"RedisCoreMethods.set received non-primitive type for key '{key}'. Attempting str conversion. Type: {type(value)}"
                )
                value = str(value)
            return await redis.set(key, value, ex=ex)
        except Exception as e:
            logger.error(f"Redis SET error for key '{key}': {e}", exc_info=True)
            return False


async def setex(
    key: str, seconds: int, value: str, *, alias: PoolAlias = "default"
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
            return await redis.setex(key, seconds, value)
        except Exception as e:
            logger.error(f"Redis SETEX error for key '{key}': {e}", exc_info=True)
            return False


async def exists(*keys: str, alias: PoolAlias = "default") -> int:
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
            return await redis.exists(*keys)
        except Exception as e:
            logger.error(
                f"Redis EXISTS error for keys starting with '{keys[0]}...': {e}",
                exc_info=True,
            )
            return 0  # Return 0 on error


async def get(key: str, *, alias: PoolAlias = "default") -> str | None:
    """
    Retrieve the string value of a key.

    Args:
        key: The full Redis key.
        alias: Redis pool alias to use (default: "default").

    Returns:
        The string value if the key exists, otherwise None.
        Returns None on error.
    """
    async with RedisClient.connection(alias=alias) as redis:
        try:
            # Assumes decode_responses=True in RedisClient config
            return await redis.get(key)
        except Exception as e:
            logger.error(f"Redis GET error for key '{key}': {e}", exc_info=True)
            return None


async def delete(*keys: str, alias: PoolAlias = "default") -> int:
    """
    Delete one or more keys.

    Args:
        *keys: One or more full Redis keys to delete.
        alias: Redis pool alias to use (default: "default").

    Returns:
        The number of keys deleted. Returns 0 on error.
    """
    if not keys:
        return 0
    async with RedisClient.connection(alias=alias) as redis:
        try:
            return await redis.delete(*keys)
        except Exception as e:
            logger.error(
                f"Redis DELETE error for keys starting with '{keys[0]}...': {e}",
                exc_info=True,
            )
            return 0

    # =========================================================================


# SECTION: Atomic Combined Operations (Using Pipelines internally)
# =========================================================================
async def hset_with_expire(
    key: str, mapping: Mapping[str, str], ttl: int, *, alias: PoolAlias = "default"
) -> tuple[int | None, bool]:
    """
    Atomically sets hash fields using HSET and sets key expiration using EXPIRE.

    Args:
        key: The full Redis key of the hash.
        mapping: A dictionary of field-value pairs (str:str).
        ttl: Time To Live in seconds.
        alias: Redis pool alias to use (default: "default").

    Returns:
        A tuple: (result_of_hset, result_of_expire).
        - result_of_hset: Integer reply from HSET (number of fields added), or None on pipeline error.
        - result_of_expire: Boolean indicating if EXPIRE was successful, or False on pipeline error.
        Returns (None, False) on general exception.
    """
    if not mapping:
        logger.warning(
            f"hset_with_expire called with empty mapping for key '{key}'. Skipping HSET, attempting EXPIRE."
        )
        try:
            # Still attempt expire if key might exist
            expire_success = await expire(key, ttl, alias=alias)
            return 0, expire_success  # HSET result is 0 as nothing was set
        except Exception as e:
            logger.error(
                f"Error attempting EXPIRE in hset_with_expire for key '{key}' with empty mapping: {e}",
                exc_info=True,
            )
            return None, False

    async with RedisClient.connection(alias=alias) as redis:
        try:
            async with redis.pipeline(transaction=True) as pipe:
                # Ensure mapping values are suitable primitive types
                checked_mapping = {}
                for k, v in mapping.items():
                    if not isinstance(v, str | bytes | int | float):
                        logger.warning(
                            f"RedisCoreMethods.hset_with_expire received non-primitive type for field '{k}' in mapping for key '{key}'. Attempting str conversion. Type: {type(v)}"
                        )
                        checked_mapping[k] = str(v)
                    else:
                        checked_mapping[k] = v
                pipe.hset(key, mapping=checked_mapping)
                pipe.expire(key, ttl)
                results = await pipe.execute()
            # results is a list [hset_result, expire_result]
            hset_res = results[0] if results and len(results) > 0 else None
            expire_res = bool(results[1]) if results and len(results) > 1 else False
            return hset_res, expire_res
        except Exception as e:
            logger.error(
                f"Redis HSET+EXPIRE pipeline error for key '{key}': {e}", exc_info=True
            )
            return None, False  # Indicate pipeline execution failure


async def hincrby_with_expire(
    key: str, field: str, increment: int, ttl: int, *, alias: PoolAlias = "default"
) -> tuple[int | None, bool]:
    """
    Atomically increments a hash field using HINCRBY and sets key expiration using EXPIRE.

    Args:
        key: The full Redis key of the hash.
        field: The field name.
        increment: The amount to increment by.
        ttl: Time To Live in seconds.
        alias: Redis pool alias to use (default: "default").

    Returns:
        A tuple: (new_value, result_of_expire).
        - new_value: The integer value after increment, or None if HINCRBY failed (e.g., WRONGTYPE) or pipeline error.
        - result_of_expire: Boolean indicating if EXPIRE was successful, or False on pipeline error.
        Returns (None, False) on general exception.
    """
    async with RedisClient.connection(alias=alias) as redis:
        try:
            async with redis.pipeline(transaction=True) as pipe:
                pipe.hincrby(key, field, increment)
                pipe.expire(key, ttl)
                results = await pipe.execute()

            # results is a list [hincrby_result, expire_result]
            # Check for specific redis error within pipeline result for hincrby if needed
            # For now, assume if results[0] is None or exception, it failed.
            incr_res = (
                int(results[0])
                if results and len(results) > 0 and results[0] is not None
                else None
            )
            expire_res = bool(results[1]) if results and len(results) > 1 else False
            return incr_res, expire_res
        except (
            Exception
        ) as e:  # Catches WRONGTYPE from HINCRBY within execute or connection errors
            logger.error(
                f"Redis HINCRBY+EXPIRE pipeline error for key '{key}', field '{field}': {e}",
                exc_info=True,
            )
            return None, False  # Indicate pipeline execution failure


async def rpush_and_sadd(
    list_key: str,
    list_values: Sequence[str],
    set_key: str,
    set_members: Sequence[str],
    *,
    alias: PoolAlias = "default",
) -> tuple[int | None, int | None]:
    """
    Atomically pushes values to a list using RPUSH and adds members to a set using SADD.

    Args:
        list_key: The full Redis key for the list.
        list_values: Sequence of string values to push to the list.
        set_key: The full Redis key for the set.
        set_members: Sequence of string members to add to the set.
        alias: Redis pool alias to use (default: "default").

    Returns:
        A tuple: (result_of_rpush, result_of_sadd).
        - result_of_rpush: New length of the list, or None on pipeline error.
        - result_of_sadd: Number of members added to the set, or None on pipeline error.
        Returns (None, None) on general exception.
    """
    if not list_values or not set_members:
        logger.warning(
            f"rpush_and_sadd called with empty list_values or set_members. ListKey: '{list_key}', SetKey: '{set_key}'. Skipping pipeline."
        )
        # Decide desired behavior: maybe still run the non-empty part? For now, return failure.
        return None, None  # Indicate nothing was done due to empty input

    async with RedisClient.connection(alias=alias) as redis:
        try:
            # Ensure values/members are primitive types
            checked_list_values = []
            for v in list_values:
                if not isinstance(v, str | bytes | int | float):
                    logger.warning(
                        f"RedisCoreMethods.rpush_and_sadd received non-primitive type in list_values for key '{list_key}'. Attempting str conversion. Type: {type(v)}"
                    )
                    checked_list_values.append(str(v))
                else:
                    checked_list_values.append(v)

            checked_set_members = []
            for m in set_members:
                if not isinstance(m, str | bytes | int | float):
                    logger.warning(
                        f"RedisCoreMethods.rpush_and_sadd received non-primitive type in set_members for key '{set_key}'. Attempting str conversion. Type: {type(m)}"
                    )
                    checked_set_members.append(str(m))
                else:
                    checked_set_members.append(m)

            async with redis.pipeline(transaction=True) as pipe:
                pipe.rpush(list_key, *checked_list_values)
                pipe.sadd(set_key, *checked_set_members)
                results = await pipe.execute()

            # results is a list [rpush_result, sadd_result]
            rpush_res = results[0] if results and len(results) > 0 else None
            sadd_res = results[1] if results and len(results) > 1 else None
            return rpush_res, sadd_res
        except Exception as e:
            logger.error(
                f"Redis RPUSH+SADD pipeline error for list '{list_key}', set '{set_key}': {e}",
                exc_info=True,
            )
            return None, None  # Indicate pipeline execution failure


# =========================================================================
# SECTION: Scan Operations
# =========================================================================


async def scan_keys(
    match_pattern: str,
    cursor: str | bytes | int = 0,
    count: int | None = None,
    *,
    alias: PoolAlias = "default",
) -> tuple[str | int, list[str]]:
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
    current_cursor: str | int = (
        cursor if isinstance(cursor, str | int) else str(int(cursor))
    )  # Prefer string '0' if bytes 'b0' is passed. Assume int 0 is start.

    async with RedisClient.connection(alias=alias) as redis:
        try:
            # redis-py's scan returns (new_cursor, keys_list)
            # new_cursor type might be int or bytes depending on version/config
            # keys_list should be List[str] if decode_responses=True
            next_cursor, keys_batch = await redis.scan(
                cursor=current_cursor, match=match_pattern, count=count
            )

            # Normalize cursor for return - prefer string representation if bytes returned
            if isinstance(next_cursor, bytes):
                next_cursor = next_cursor.decode("utf-8")
            elif isinstance(next_cursor, int):  # Common return type
                next_cursor = str(
                    next_cursor
                )  # Return as string for consistency with potential byte cursor

            # Ensure keys are strings (should be if decode_responses=True)
            keys_batch_str = [
                k if isinstance(k, str) else k.decode("utf-8") for k in keys_batch
            ]

            return next_cursor, keys_batch_str
        except Exception as e:
            logger.error(
                f"Redis SCAN error for pattern '{match_pattern}' with cursor '{current_cursor}': {e}",
                exc_info=True,
            )
            return (
                "0",
                [],
            )  # Return '0' cursor and empty list to signal completion/error


# =========================================================================
# SECTION: TTL Management
# =========================================================================
async def get_ttl(key: str, *, alias: PoolAlias = "default") -> int:
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
            return await redis.ttl(key)
        except Exception as e:
            logger.error(f"Error getting TTL for key '{key}': {e}")
            return -2  # Consistent with redis-py for errors/non-existent key


async def expire(key: str, ttl: int, *, alias: PoolAlias = "default") -> bool:
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


# =========================================================================
# SECTION: Hash Operations
# =========================================================================
async def hset(
    key: str,
    field: str | None = None,
    value: str | None = None,
    mapping: Mapping[str, str] | None = None,
    *,
    alias: PoolAlias = "default",
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
                return await redis.hset(key, mapping=checked_mapping)
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
                return await redis.hset(key, mapping={field: value_to_set})
                # Older way (might vary by redis-py version): return await redis.hset(key, field, value_to_set)
        except Exception as e:
            logger.error(f"Redis HSET error for key '{key}': {e}", exc_info=True)
            return -1  # Indicate error


async def hget(key: str, field: str, *, alias: PoolAlias = "default") -> str | None:
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
            return await redis.hget(key, field)
        except Exception as e:
            logger.error(f"Redis HGET error for key '{key}', field '{field}': {e}")
            return None


async def hgetall(key: str, *, alias: PoolAlias = "default") -> dict[str, str]:
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
            return await redis.hgetall(key)
        except Exception as e:
            logger.error(f"Redis HGETALL error for key '{key}': {e}", exc_info=True)
            return {}


async def hexists(key: str, field: str, *, alias: PoolAlias = "default") -> bool:
    """
    Checks if a field exists in a hash.

    Args:
        key: The full Redis key of the hash.
        field: The field name.
        alias: Redis pool alias to use (default: "default").

    Returns:
        True if the field exists, False otherwise (including key not existing or error).
    """
    async with RedisClient.connection(alias=alias) as redis:
        try:
            return await redis.hexists(key, field)
        except Exception as e:
            logger.error(f"Redis HEXISTS error for key '{key}', field '{field}': {e}")
            return False


async def hdel(key: str, *fields: str, alias: PoolAlias = "default") -> int:
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
            return await redis.hdel(key, *fields)
        except Exception as e:
            logger.error(f"Redis HDEL error for key '{key}', fields '{fields}': {e}")
            return 0


async def hincrby(
    key: str, field: str, increment: int = 1, *, alias: PoolAlias = "default"
) -> int | None:
    """
    Atomically increments the integer value of a hash field by the given amount.
    Sets the field to `increment` if the field does not exist.

    Args:
        key: The full Redis key of the hash.
        field: The field name.
        increment: The amount to increment by (default: 1).
        alias: Redis pool alias to use (default: "default").

    Returns:
        The new integer value of the field after the increment.
        Returns None if the key exists but the field contains a value of the wrong type,
        or if an error occurs.
    """
    async with RedisClient.connection(alias=alias) as redis:
        try:
            result = await redis.hincrby(key, field, increment)
            # HINCRBY returns the new value as an integer
            return int(result)
        except Exception as e:  # Catches redis errors like WRONGTYPE
            logger.error(f"Redis HINCRBY error for key '{key}', field '{field}': {e}")
            return None


# =========================================================================
# SECTION: List Operations
# =========================================================================
async def rpush(key: str, *values: str, alias: PoolAlias = "default") -> int:
    """
    Pushes one or more string values onto the right end of a list.

    Args:
        key: The full Redis key for the list.
        *values: One or more string values to push.
        alias: Redis pool alias to use (default: "default").

    Returns:
        The length of the list after the push operation, or 0 on error.
    """
    if not values:
        return await llen(
            key, alias=alias
        )  # RPUSH with no values is a no-op, return current length

    async with RedisClient.connection(alias=alias) as redis:
        try:
            # Ensure values are primitive types suitable for redis-py
            checked_values = []
            for v in values:
                if not isinstance(v, str | bytes | int | float):
                    logger.warning(
                        f"RedisCoreMethods.rpush received non-primitive type in values for key '{key}'. Attempting str conversion. Type: {type(v)}"
                    )
                    checked_values.append(str(v))
                else:
                    checked_values.append(v)
            return await redis.rpush(key, *checked_values)
        except Exception as e:
            logger.error(f"Redis RPUSH error for key '{key}': {e}", exc_info=True)
            return 0


async def lpop(
    key: str, count: int | None = None, *, alias: PoolAlias = "default"
) -> str | list[str] | None:
    """
    Removes and returns elements from the left end of a list.

    Args:
        key: The full Redis key for the list.
        count: The number of elements to pop. If None (default), pops one element.
                If count > 0, pops up to 'count' elements (Redis >= 6.2).
        alias: Redis pool alias to use (default: "default").

    Returns:
        A single string, a list of strings, or None if the list is empty or an error occurs.
        (Assumes decode_responses=True).
    """
    async with RedisClient.connection(alias=alias) as redis:
        try:
            # aioredis-py handles the 'count' argument.
            # Assumes decode_responses=True returns str or List[str].
            result = await redis.lpop(key, count=count)
            return result  # Should be str, List[str], or None
        except Exception as e:
            logger.error(
                f"Redis LPOP error for key '{key}' with count {count}: {e}",
                exc_info=True,
            )
            return None


async def lrange(
    key: str, start: int, end: int, *, alias: PoolAlias = "default"
) -> list[str]:
    """
    Gets a range of elements from a list.

    Args:
        key: The full Redis key for the list.
        start: Start index (0-based).
        end: End index (inclusive, -1 for last element).
        alias: Redis pool alias to use (default: "default").

    Returns:
        A list of string elements (assumes decode_responses=True),
        or an empty list if key doesn't exist or on error.
    """
    async with RedisClient.connection(alias=alias) as redis:
        try:
            # Assumes decode_responses=True returns List[str]
            return await redis.lrange(key, start, end)
        except Exception as e:
            logger.error(f"Redis LRANGE error for key '{key}': {e}", exc_info=True)
            return []


async def ltrim(
    key: str, start: int, end: int, *, alias: PoolAlias = "default"
) -> bool:
    """
    Trims a list so that it will contain only the specified range of elements.

    Args:
        key: The full Redis key for the list.
        start: Start index (0-based).
        end: End index (inclusive, -1 for last element).
        alias: Redis pool alias to use (default: "default").

    Returns:
        True if the operation was successful, False otherwise.
    """
    async with RedisClient.connection(alias=alias) as redis:
        try:
            return await redis.ltrim(key, start, end)
        except Exception as e:
            logger.error(f"Redis LTRIM error for key '{key}': {e}", exc_info=True)
            return False


async def llen(key: str, *, alias: PoolAlias = "default") -> int:
    """
    Gets the length of a list.

    Args:
        key: The full Redis key for the list.
        alias: Redis pool alias to use (default: "default").

    Returns:
        The length of the list, or 0 if the key doesn't exist or on error.
    """
    async with RedisClient.connection(alias=alias) as redis:
        try:
            return await redis.llen(key)
        except Exception as e:
            logger.error(f"Redis LLEN error for key '{key}': {e}", exc_info=True)
            return 0


# =========================================================================
# SECTION: Set Operations
# =========================================================================
async def sadd(key: str, *members: str, alias: PoolAlias = "default") -> int:
    """
    Adds one or more members to a set.

    Args:
        key: The full key name for the set.
        *members: One or more string members to add.
        alias: Redis pool alias to use (default: "default").

    Returns:
        The number of members that were added to the set (not including members already present),
        or 0 on error.
    """
    if not members:
        return 0  # SADD with no members is a no-op

    async with RedisClient.connection(alias=alias) as redis:
        try:
            # Ensure members are primitive types suitable for redis-py
            checked_members = []
            for m in members:
                if not isinstance(m, str | bytes | int | float):
                    logger.warning(
                        f"RedisCoreMethods.sadd received non-primitive type in members for key '{key}'. Attempting str conversion. Type: {type(m)}"
                    )
                    checked_members.append(str(m))
                else:
                    checked_members.append(m)
            return await redis.sadd(key, *checked_members)
        except Exception as e:
            logger.error(f"Redis SADD error for key '{key}': {e}", exc_info=True)
            return 0


async def smembers(key: str, *, alias: PoolAlias = "default") -> builtins.set[str]:
    """
    Gets all members of a set.

    Args:
        key: The full key name for the set.
        alias: Redis pool alias to use (default: "default").

    Returns:
        A set of string members (assumes decode_responses=True),
        or an empty set if the key doesn't exist or on error.
    """
    async with RedisClient.connection(alias=alias) as redis:
        try:
            # Assumes decode_responses=True returns Set[str]
            return await redis.smembers(key)
        except Exception as e:
            logger.error(f"Redis SMEMBERS error for key '{key}': {e}", exc_info=True)
            return set()


async def srem(key: str, *members: str, alias: PoolAlias = "default") -> int:
    """
    Removes one or more members from a set.

    Args:
        key: The full key name for the set.
        *members: One or more string members to remove.
        alias: Redis pool alias to use (default: "default").

    Returns:
        The number of members that were removed from the set, or 0 on error.
    """
    if not members:
        return 0  # SREM with no members is a no-op

    async with RedisClient.connection(alias=alias) as redis:
        try:
            # Ensure members are primitive types suitable for redis-py
            checked_members = []
            for m in members:
                if not isinstance(m, str | bytes | int | float):
                    logger.warning(
                        f"RedisCoreMethods.srem received non-primitive type in members for key '{key}'. Attempting str conversion. Type: {type(m)}"
                    )
                    checked_members.append(str(m))
                else:
                    checked_members.append(m)
            return await redis.srem(key, *checked_members)
        except Exception as e:
            logger.error(f"Redis SREM error for key '{key}': {e}", exc_info=True)
            return 0


"""
Tiny, opinionated helpers on top of `redis.asyncio`.

```python
from symphony_concurrency.redis import ops as r

await r.set("foo", "bar", ex=60)
val = await r.get("foo")
await r.hset_with_expire("profile:42", {"name": "alice"}, ttl=3600)

# Use different Redis pools/databases via alias
await r.set("key", "value", alias="expiry")  # expiry pool
await r.hget("hash", "field", alias="pubsub")  # pubsub pool
```
Each call grabs a connection from RedisClient.connection(alias) – the pool is
reused, so there's no socket churn.

All functions accept an optional `alias` parameter (default: "default") to target
specific Redis pools configured via GlobalSymphonyConfig.

Values are automatically coerced to str for safety.

All functions return a sane fallback (False / None / 0) on error and
emit a Rich-style log entry via logger = logging.getLogger("RedisOps").

If you need more exotic commands, import the raw client:
```python
redis = await RedisClient.get("handlers")  # specific pool
await redis.zadd("scores", {"bob": 123})
```
"""
