"""A SCAN pattern must match the segment it was built from, character for character.

Bulk operations (delete-a-table, list-pkids, find-by-field, delete-all-for-user)
are all SCAN globs. A literal segment containing `*`, `?`, `[`, or `]` changes
what the glob means, so a delete built from it silently matches nothing and
reports success. The memory and JSON backends compare prefixes instead of
globbing, so this is a Redis-only hazard — these tests keep the three backends
answering the same way.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest

from wappa.persistence.redis.redis_client import RedisClient
from wappa.persistence.redis.redis_handler.expiry import RedisExpiry
from wappa.persistence.redis.redis_handler.state_handler import RedisStateHandler
from wappa.persistence.redis.redis_handler.table import RedisTable
from wappa.persistence.redis.redis_handler.utils.key_factory import (
    KeyFactory,
    default_key_factory,
)

REDIS_URL = os.getenv("WAPPA_TEST_REDIS_URL", "redis://localhost:6379")

# Values a real deployment can produce: Meta ids are digits, but a Host
# Application may scope a cache space or a table name however it likes.
HOSTILE = "inbox[1]*?x"


@pytest.mark.parametrize(
    ("raw", "escaped"),
    [
        pytest.param("plain", "plain", id="untouched"),
        pytest.param("a[1]", r"a\[1\]", id="brackets"),
        pytest.param("a*b", r"a\*b", id="star"),
        pytest.param("a?b", r"a\?b", id="question-mark"),
        pytest.param("a\\b", "a\\\\b", id="backslash"),
    ],
)
def test_glob_escape_neutralizes_pattern_syntax(raw: str, escaped: str) -> None:
    assert KeyFactory.glob_escape(raw) == escaped


def test_pattern_builders_escape_literals_and_keep_wildcards() -> None:
    keys = default_key_factory

    # None means "range over this dimension"; a value means "match it exactly".
    assert keys.table_pattern("a[1]", "rows") == r"a\[1\]:df:rows:pkid:*"
    assert keys.table_pattern("inbox", pkid="p*1") == r"inbox:df:*:pkid:p\*1"
    assert keys.table_pattern("inbox") == "inbox:df:*:pkid:*"
    assert keys.user_pattern("a[1]") == r"a\[1\]:user:*"
    assert (
        keys.trigger_pattern("inbox", ident="TXN[9]") == r"inbox:EXPTRIGGER:*:TXN\[9\]"
    )
    assert keys.handler_pattern("inbox", user_id="u[2]") == r"inbox:state:*:u\[2\]"
    # A deliberate prefix wildcard survives, while the prefix itself is escaped.
    assert (
        keys.handler_pattern("inbox", user_id="u", name_prefix="flow[a]")
        == r"inbox:state:flow\[a\]*:u"
    )
    assert (
        keys.aistate_pattern("inbox", user_id="u", name_prefix="agent*")
        == r"inbox:aistate:agent\**:u"
    )


def test_the_pattern_and_the_key_agree_on_the_same_literal() -> None:
    """The key stores the raw value; the pattern stores its escaped form."""
    keys = default_key_factory

    key = keys.table(HOSTILE, "rows", "pk-7")
    pattern = keys.table_pattern(HOSTILE, "rows")

    assert key.startswith(f"{HOSTILE}:df:rows:pkid:")
    assert pattern.startswith(f"{KeyFactory.glob_escape(HOSTILE)}:df:rows:pkid:")
    # Whether the two actually match is Redis' call, not fnmatch's — the live
    # tests below settle it against a real server.


@pytest.fixture
async def redis_ready() -> AsyncIterator[None]:
    """Fresh pools bound to this test's loop; skip when no server answers."""
    await RedisClient.close()
    RedisClient.setup_single_url(REDIS_URL)
    try:
        async with RedisClient.connection(alias="table") as redis:
            await redis.ping()
    except Exception:
        await RedisClient.close()
        pytest.skip(f"No Redis reachable at {REDIS_URL}")
    try:
        yield
    finally:
        await RedisClient.close()


async def test_delete_table_removes_rows_under_a_hostile_inbox(
    redis_ready: None,
) -> None:
    table = RedisTable(HOSTILE)
    try:
        await table.upsert("rows", "a", {"v": 1}, ttl=60)
        await table.upsert("rows", "b", {"v": 2}, ttl=60)

        assert sorted(await table.list_pkids("rows")) == ["a", "b"]
        assert len(await table.get_all("rows")) == 2
        assert await table.find_by_field("rows", "v", 2) == {"v": 2}

        assert await table.delete_table("rows") == 2
        assert await table.list_pkids("rows") == []
    finally:
        await table.delete("rows", "a")
        await table.delete("rows", "b")


async def test_delete_all_by_pkid_spans_tables_under_a_hostile_inbox(
    redis_ready: None,
) -> None:
    table = RedisTable(HOSTILE)
    try:
        await table.upsert("t1", "shared[1]", {"v": 1}, ttl=60)
        await table.upsert("t2", "shared[1]", {"v": 2}, ttl=60)

        assert await table.delete_all_by_pkid("shared[1]") == 2
        assert await table.get("t1", "shared[1]") is None
        assert await table.get("t2", "shared[1]") is None
    finally:
        await table.delete_table("t1")
        await table.delete_table("t2")


async def test_state_enumeration_survives_a_hostile_user_id(
    redis_ready: None,
) -> None:
    handler = RedisStateHandler(inbox=HOSTILE, user_id="user[9]")
    try:
        await handler.upsert("flow_a", {"step": 1}, ttl=60)
        await handler.upsert("flow_b", {"step": 2}, ttl=60)

        assert sorted(await handler.list_handlers()) == ["flow_a", "flow_b"]
        assert await RedisStateHandler.list_users_with_handler(
            inbox_id=HOSTILE, handler_name="flow_a"
        ) == ["user[9]"]
        assert await handler.delete_by_handler_prefix("flow_") == 2
        assert await handler.list_handlers() == []
    finally:
        await handler.delete_all_for_user()


async def test_expiry_identifier_cleanup_survives_hostile_values(
    redis_ready: None,
) -> None:
    expiry = RedisExpiry(inbox=HOSTILE, user_id="user[9]")
    try:
        await expiry.set("reminder", "TXN[1]", ttl_seconds=60)
        await expiry.set("timeout", "TXN[1]", ttl_seconds=60)
        await expiry.set("reminder", "OTHER", ttl_seconds=60)

        assert await expiry.delete_all_by_identifier("TXN[1]") == 2
        assert not await expiry.exists("reminder", "TXN[1]")
        assert await expiry.exists("reminder", "OTHER")
    finally:
        await expiry.delete_all_by_identifier("OTHER")


def test_expiry_has_no_delete_all_for_user() -> None:
    """It used to mean "triggers whose identifier is the user id" — a different
    meaning from the identically named method on IStateCache/IAIStateCache.
    Callers say `delete_all_by_identifier(user_id)` instead."""
    from wappa.domain.interfaces.cache_interfaces import (
        IAIStateCache,
        IExpiryCache,
        IStateCache,
    )

    assert not hasattr(IExpiryCache, "delete_all_for_user")
    assert not hasattr(RedisExpiry, "delete_all_for_user")
    # Still present where a key really is user-scoped.
    assert hasattr(IStateCache, "delete_all_for_user")
    assert hasattr(IAIStateCache, "delete_all_for_user")
