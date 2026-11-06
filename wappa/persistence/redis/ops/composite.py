"""Atomic combined Redis operations (hash+expire, list+set) and Lua script evaluation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from ..redis_client import PoolAlias, RedisClient
from ._shared import _await_command, logger
from .keys import expire


async def hset_with_expire(
    key: str, mapping: Mapping[str, str], ttl: int, *, alias: PoolAlias = "users"
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
    key: str, field: str, increment: int, ttl: int, *, alias: PoolAlias = "users"
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


async def eval_script(
    script: str,
    keys: Sequence[str],
    args: Sequence[str | int | float],
    *,
    alias: PoolAlias = "users",
) -> object:
    """
    Run a Lua script server-side, so a condition and its write cannot interleave.

    Raises instead of swallowing errors: a caller reaching for a script needs a
    conditional write to either happen or visibly fail, and a `None` fallback
    would read as "condition not met".

    Args:
        script: Lua source.
        keys: Redis keys the script touches (KEYS[1..n]).
        args: Script arguments (ARGV[1..n]).
        alias: Redis pool alias to use.

    Returns:
        The script's reply, converted by redis-py.
    """
    async with RedisClient.connection(alias=alias) as redis:
        return await _await_command(redis.eval(script, len(keys), *keys, *args))
