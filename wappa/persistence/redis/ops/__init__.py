"""Thin async helpers over ``redis.asyncio``, one module per Redis family.

Each call takes a connection from ``RedisClient.connection(alias)``, so the pool
is reused. Every function accepts ``alias`` to target one of the Redis pools,
returns a safe fallback (``False``, ``None`` or ``0``) on error, and logs it.

For any other command, use the raw client:

    redis = await RedisClient.get("handlers")
    await redis.zadd("scores", {"bob": 123})
"""

from __future__ import annotations

from ._shared import _await_command, logger
from .composite import eval_script, hincrby_with_expire, hset_with_expire
from .hashes import hdel, hget, hgetall, hset
from .keys import expire, get_ttl, rename_if_absent, scan_keys
from .strings import delete, exists, setex

__all__ = [
    "_await_command",
    "delete",
    "eval_script",
    "exists",
    "expire",
    "get_ttl",
    "hdel",
    "hget",
    "hgetall",
    "hincrby_with_expire",
    "hset",
    "hset_with_expire",
    "logger",
    "rename_if_absent",
    "scan_keys",
    "setex",
]
