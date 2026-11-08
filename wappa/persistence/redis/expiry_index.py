"""Atomic durable expiry occurrences in the existing expiry Redis database.

A due sorted set locates work without scanning keys. Its companion hash keeps
an occurrence generation and original due time while the score becomes a short
claim deadline. Successful delivery acknowledges only that exact generation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from redis.asyncio import Redis

from .ops._shared import _await_command
from .redis_handler.utils.key_factory import KeyFactory

# Redis TIME is authoritative for both TTL deadlines and recovery claims.
_CLOCK = "local t = redis.call('TIME'); local now = t[1]*1000 + math.floor(t[2]/1000); "
_CHECK = """
local function check_index(due, records)
    local dt = redis.call('TYPE', due).ok
    local rt = redis.call('TYPE', records).ok
    if (dt ~= 'none' and dt ~= 'zset') or (rt ~= 'none' and rt ~= 'hash') then
        error('Wappa expiry index has an invalid Redis type')
    end
end
"""
_ARM = (
    _CHECK
    + _CLOCK
    + """
check_index(KEYS[2], KEYS[3])
local due = now + tonumber(ARGV[1])*1000
local record = cjson.encode({generation=ARGV[2], due_at_ms=due})
redis.call('SET', KEYS[1], ARGV[2], 'EX', ARGV[1])
redis.call('HSET', KEYS[3], KEYS[1], record)
redis.call('ZADD', KEYS[2], due, KEYS[1])
return 1
"""
)
_CANCEL = (
    _CHECK
    + """
check_index(KEYS[2], KEYS[3])
local removed = redis.call('DEL', KEYS[1])
redis.call('HDEL', KEYS[3], KEYS[1])
redis.call('ZREM', KEYS[2], KEYS[1])
return removed
"""
)
_DUE = (
    _CLOCK
    + "return redis.call('ZRANGEBYSCORE', KEYS[1], '-inf', now, 'LIMIT', 0, ARGV[1])"
)
_CLAIM = (
    _CHECK
    + _CLOCK
    + """
check_index(KEYS[2], KEYS[3])
if redis.call('EXISTS', KEYS[1]) == 1 then return {} end
local record = redis.call('HGET', KEYS[3], KEYS[1])
if not record then return {'legacy', ''} end
local score = redis.call('ZSCORE', KEYS[2], KEYS[1])
if not score or tonumber(score) > now then return {} end
redis.call('ZADD', KEYS[2], now + tonumber(ARGV[1]), KEYS[1])
return {'indexed', record}
"""
)
_ACK = (
    _CHECK
    + """
check_index(KEYS[2], KEYS[3])
if redis.call('HGET', KEYS[3], KEYS[1]) ~= ARGV[1] then return 0 end
if redis.call('EXISTS', KEYS[1]) == 1 then return 0 end
redis.call('HDEL', KEYS[3], KEYS[1])
return redis.call('ZREM', KEYS[2], KEYS[1])
"""
)
_REBIND = (
    _CHECK
    + _CLOCK
    + """
check_index(KEYS[3], KEYS[4])
if redis.call('EXISTS', KEYS[1]) == 0 then return 0 end
if KEYS[1] == KEYS[2] then return 1 end
if redis.call('EXISTS', KEYS[2]) == 1 or redis.call('HEXISTS', KEYS[4], KEYS[2]) == 1 then return -1 end
local ttl = redis.call('PTTL', KEYS[1])
local record = redis.call('HGET', KEYS[4], KEYS[1])
if not record then record = cjson.encode({generation=ARGV[1], due_at_ms=now+ttl}) end
local due = cjson.decode(record).due_at_ms
redis.call('RENAME', KEYS[1], KEYS[2])
redis.call('HDEL', KEYS[4], KEYS[1])
redis.call('HSET', KEYS[4], KEYS[2], record)
redis.call('ZREM', KEYS[3], KEYS[1])
redis.call('ZADD', KEYS[3], due, KEYS[2])
return 1
"""
)


def _text(value: str | bytes) -> str:
    return value.decode() if isinstance(value, bytes) else value


@dataclass(frozen=True)
class DueTrigger:
    key: str
    record: str | None = None
    generation: str | None = None
    due_at: datetime | None = None


class RedisExpiryIndex:
    """Internal persistence seam; all mutations fail rather than arm unindexed work."""

    def __init__(self, redis: Redis) -> None:
        self.redis = redis
        keys = KeyFactory()
        self.due_key = keys.expiry_due()
        self.records_key = keys.expiry_records()

    def _keys(self, key: str) -> tuple[str, str, str]:
        return key, self.due_key, self.records_key

    async def arm(self, key: str, ttl_seconds: int) -> bool:
        if (
            not isinstance(ttl_seconds, int)
            or isinstance(ttl_seconds, bool)
            or ttl_seconds <= 0
        ):
            raise ValueError("Expiry TTL must be positive")
        return bool(
            await _await_command(
                self.redis.eval(_ARM, 3, *self._keys(key), ttl_seconds, uuid4().hex)
            )
        )

    async def cancel(self, key: str) -> int:
        return int(await _await_command(self.redis.eval(_CANCEL, 3, *self._keys(key))))

    async def cancel_matching(self, pattern: str) -> int:
        removed = 0
        # HSCAN includes overdue occurrences whose TTL key has already vanished.
        async for key, _ in self.redis.hscan_iter(
            self.records_key, match=pattern, count=100
        ):
            removed += await self.cancel(_text(key))
        # SCAN retains cancellation for pre-upgrade, unindexed TTL keys.
        async for key in self.redis.scan_iter(match=pattern, count=100):
            removed += await self.cancel(_text(key))
        return removed

    async def rebind(self, old_key: str, new_key: str) -> int:
        return int(
            await _await_command(
                self.redis.eval(
                    _REBIND,
                    4,
                    old_key,
                    new_key,
                    self.due_key,
                    self.records_key,
                    uuid4().hex,
                )
            )
        )

    async def due(self, limit: int) -> list[str]:
        values = await _await_command(self.redis.eval(_DUE, 1, self.due_key, limit))
        return [_text(value) for value in values]

    async def claim(self, key: str, *, lease_ms: int = 30_000) -> DueTrigger | None:
        values = await _await_command(
            self.redis.eval(_CLAIM, 3, *self._keys(key), lease_ms)
        )
        if not values:
            return None
        if _text(values[0]) == "legacy":
            return DueTrigger(key)
        raw = _text(values[1])
        record = json.loads(raw)
        return DueTrigger(
            key,
            raw,
            record["generation"],
            datetime.fromtimestamp(record["due_at_ms"] / 1000, UTC),
        )

    async def acknowledge(self, trigger: DueTrigger) -> bool:
        if trigger.record is None:
            return False
        return bool(
            await _await_command(
                self.redis.eval(_ACK, 3, *self._keys(trigger.key), trigger.record)
            )
        )
