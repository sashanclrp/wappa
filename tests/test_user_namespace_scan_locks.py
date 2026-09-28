"""SCAN readers must skip the host mutation lock inside ``{inbox}:user:*``.

Host Applications serialize User-cache mutations through a short-lived Redis
*string* at ``{user_key}:symphonai:mutation`` (TTL 15s). The lock shares the
user scan namespace, so ``_find_by_field`` used to HGET it on every pass —
logging a WRONGTYPE error per lock per scan. These tests pin the skip, the
per-key tolerance, and that nothing else about the scan changed.

No live Redis is required: the ops layer is faked at the ``inbox_cache``
module boundary, which is where ``_find_by_field`` resolves it.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from typing import Any

import pytest

from wappa.persistence.redis.redis_client import RedisClient
from wappa.persistence.redis.redis_handler.user import RedisUser
from wappa.persistence.redis.redis_handler.utils import inbox_cache
from wappa.persistence.redis.redis_handler.utils.serde import dumps, dumps_hash

REDIS_URL = os.getenv("WAPPA_TEST_REDIS_URL", "redis://localhost:6379")

INBOX = "660404413518908"
LOCK_KEY = f"{INBOX}:user:CO.2186878922080769:symphonai:mutation"


class _FakeOps:
    """In-memory stand-in for the ops functions ``_find_by_field`` calls."""

    def __init__(self, hashes: dict[str, dict[str, Any]], scanned: list[str]):
        self.hashes = hashes
        self.scanned = scanned
        self.hget_calls: list[str] = []
        self.hgetall_calls: list[str] = []

    async def scan_keys(
        self, match_pattern: str, cursor: int = 0, count: int | None = None, **_: Any
    ) -> tuple[int, list[str]]:
        return 0, list(self.scanned)

    async def hget(self, key: str, field: str, **_: Any) -> str | None:
        self.hget_calls.append(key)
        stored = self.hashes.get(key)
        if stored is None or field not in stored:
            return None
        return dumps(stored[field])

    async def hgetall(self, key: str, **_: Any) -> dict[str, str]:
        self.hgetall_calls.append(key)
        stored = self.hashes.get(key)
        return dumps_hash(stored) if stored is not None else {}


def _patch_ops(monkeypatch: pytest.MonkeyPatch, ops: _FakeOps) -> None:
    monkeypatch.setattr(inbox_cache, "scan_keys", ops.scan_keys)
    monkeypatch.setattr(inbox_cache, "hget", ops.hget)
    monkeypatch.setattr(inbox_cache, "hgetall", ops.hgetall)


@pytest.mark.asyncio
async def test_find_by_field_never_hgets_a_mutation_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The lock key is skipped before HGET — no WRONGTYPE, no wasted call."""
    user_key = f"{INBOX}:user:573168227670"
    ops = _FakeOps(
        hashes={user_key: {"phone": "573168227670"}},
        scanned=[LOCK_KEY, user_key],
    )
    _patch_ops(monkeypatch, ops)

    found = await RedisUser(inbox=INBOX, user_id="_").find_by_field(
        "phone", "573168227670"
    )

    # serde.loads round-trips the digit string to an int.
    assert found == {"phone": 573168227670}
    assert ops.hget_calls == [user_key]
    assert LOCK_KEY not in ops.hget_calls


@pytest.mark.asyncio
async def test_find_by_field_scans_past_locks_to_a_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Lock keys interleaved with real hashes don't abort the scan."""
    user_key = f"{INBOX}:user:CO.2186878922080769"
    ops = _FakeOps(
        hashes={user_key: {"phone": "573168227670", "name": "Sasha"}},
        scanned=[
            LOCK_KEY,
            f"{INBOX}:user:573100000000",  # vanished: hget answers None
            user_key,
        ],
    )
    _patch_ops(monkeypatch, ops)

    found = await RedisUser(inbox=INBOX, user_id="_").find_by_field(
        "phone", "573168227670"
    )

    assert found == {"phone": 573168227670, "name": "Sasha"}
    assert ops.hget_calls == [f"{INBOX}:user:573100000000", user_key]


@pytest.mark.asyncio
async def test_find_by_field_returns_none_when_only_locks_exist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ops = _FakeOps(hashes={}, scanned=[LOCK_KEY])
    _patch_ops(monkeypatch, ops)

    found = await RedisUser(inbox=INBOX, user_id="_").find_by_field(
        "phone", "573168227670"
    )

    assert found is None
    assert ops.hget_calls == []


def test_lock_key_shape_predicate() -> None:
    assert inbox_cache.is_user_mutation_lock_key(LOCK_KEY)
    assert not inbox_cache.is_user_mutation_lock_key(f"{INBOX}:user:573168227670")
    # A user id that merely contains the word is not a lock.
    assert not inbox_cache.is_user_mutation_lock_key(
        f"{INBOX}:user:symphonai_mutation_user"
    )


@pytest.fixture
async def redis_ready() -> AsyncIterator[None]:
    """Fresh pools bound to this test's loop; skip when no server answers."""
    await RedisClient.close()
    RedisClient.setup_single_url(REDIS_URL)
    try:
        async with RedisClient.connection(alias="users") as redis:
            await redis.ping()
    except Exception:
        await RedisClient.close()
        pytest.skip(f"No Redis reachable at {REDIS_URL}")
    try:
        yield
    finally:
        await RedisClient.close()


@pytest.mark.asyncio
async def test_live_find_by_field_ignores_a_real_lock_key(
    redis_ready: None,
) -> None:
    """Against a real server, a string lock key must not fail the lookup."""
    user = RedisUser(inbox=INBOX, user_id="573168227670")
    try:
        await user.upsert({"phone": "573168227670"}, ttl=60)
        async with RedisClient.connection(alias="users") as redis:
            await redis.set(LOCK_KEY, "lock-token", ex=15)

        assert await user.find_by_field("phone", "573168227670") == {
            "phone": 573168227670
        }
    finally:
        await user.delete()
        async with RedisClient.connection(alias="users") as redis:
            await redis.delete(LOCK_KEY)
