"""Shared logger and awaitable helper for the Redis ops modules."""

from __future__ import annotations

import logging
from collections.abc import Awaitable
from typing import cast

logger = logging.getLogger(
    "RedisCoreMethods"
)  # Use __name__ for standard logging practice


async def _await_command[T](result: T | Awaitable[T]) -> T:
    """Await an asyncio Redis command despite redis-py's sync/async stub union."""
    return await cast(Awaitable[T], result)
