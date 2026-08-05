"""One contract suite for atomic table-row transitions, run on every backend.

The point of these operations is that a race has exactly one winner, so the
suite is parameterized over Redis, memory, and JSON rather than trusting each
adapter's own tests. Redis is the only backend where the race is genuinely
between processes; it is skipped when no server is reachable.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Callable
from enum import StrEnum
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from wappa.domain.interfaces.cache_interfaces import ITableCache, TableRowTransition
from wappa.persistence import TypedTableCache
from wappa.persistence.json.handlers.table_handler import JSONTable
from wappa.persistence.json.handlers.utils.file_manager import file_manager
from wappa.persistence.memory.handlers.table_handler import MemoryTable
from wappa.persistence.redis.redis_client import RedisClient
from wappa.persistence.redis.redis_handler.table import RedisTable

REDIS_URL = os.getenv("WAPPA_TEST_REDIS_URL", "redis://localhost:6379")


class Status(StrEnum):
    PENDING = "pending"
    SETTLED = "settled"


class Handoff(BaseModel):
    owner: str
    status: Status
    attempts: int = 0


async def _open_redis_pools() -> bool:
    """Bind fresh pools to this test's event loop; False when no server answers."""
    await RedisClient.close()
    RedisClient.setup_single_url(REDIS_URL)
    try:
        async with RedisClient.connection(alias="table") as redis:
            await redis.ping()
        return True
    except Exception:
        await RedisClient.close()
        return False


@pytest.fixture(params=["memory", "json", "redis"])
async def table(
    request: pytest.FixtureRequest, tmp_path: Path
) -> AsyncIterator[ITableCache]:
    """An empty ``ITableCache`` for one backend, isolated per test."""
    # Redis cleanup globs on the inbox, so keep the name free of glob syntax.
    node = request.node.name.replace("[", "-").replace("]", "")
    inbox = f"transitions-{node}"[:96]

    match request.param:
        case "memory":
            yield MemoryTable(inbox=inbox)
        case "json":
            file_manager._cache_root = tmp_path / "cache"
            file_manager.ensure_cache_directories()
            yield JSONTable(inbox=inbox)
        case _:
            if not await _open_redis_pools():
                pytest.skip(f"No Redis reachable at {REDIS_URL}")
            cache = RedisTable(inbox=inbox)
            try:
                yield cache
            finally:
                await cache.delete_table("handoffs")
                await RedisClient.close()


@pytest.fixture
def handoffs(table: ITableCache) -> TypedTableCache[Handoff]:
    return TypedTableCache(table, "handoffs", Handoff, default_ttl=60)


async def test_create_if_absent_creates_a_missing_row(
    handoffs: TypedTableCache[Handoff],
) -> None:
    result = await handoffs.create_if_absent(
        "h-1", Handoff(owner="a", status=Status.PENDING)
    )

    assert result.transition is TableRowTransition.CREATED
    assert result.written
    assert result.row is None
    assert await handoffs.get("h-1") == Handoff(owner="a", status=Status.PENDING)


async def test_create_if_absent_reports_the_row_that_won(
    handoffs: TypedTableCache[Handoff],
) -> None:
    await handoffs.create_if_absent("h-1", Handoff(owner="a", status=Status.PENDING))

    result = await handoffs.create_if_absent(
        "h-1", Handoff(owner="b", status=Status.PENDING)
    )

    assert result.transition is TableRowTransition.ALREADY_EXISTS
    assert not result.written
    assert result.row == Handoff(owner="a", status=Status.PENDING)
    assert await handoffs.get("h-1") == Handoff(owner="a", status=Status.PENDING)


async def test_concurrent_create_has_exactly_one_winner(
    handoffs: TypedTableCache[Handoff],
) -> None:
    results = await asyncio.gather(
        *(
            handoffs.create_if_absent(
                "h-1", Handoff(owner=f"owner-{index}", status=Status.PENDING)
            )
            for index in range(20)
        )
    )

    created = [r for r in results if r.transition is TableRowTransition.CREATED]
    assert len(created) == 1

    stored = await handoffs.get("h-1")
    assert stored is not None
    # Every loser sees the same settled row — the one actually stored.
    for result in results:
        if result.transition is TableRowTransition.ALREADY_EXISTS:
            assert result.row == stored


async def test_replace_if_replaces_when_the_condition_holds(
    handoffs: TypedTableCache[Handoff],
) -> None:
    await handoffs.create_if_absent("h-1", Handoff(owner="a", status=Status.PENDING))

    result = await handoffs.replace_if(
        "h-1",
        Handoff(owner="a", status=Status.SETTLED, attempts=1),
        expected={"status": Status.PENDING},
    )

    assert result.transition is TableRowTransition.REPLACED
    assert result.written
    assert await handoffs.get("h-1") == Handoff(
        owner="a", status=Status.SETTLED, attempts=1
    )


async def test_replace_if_refuses_and_reports_the_current_row(
    handoffs: TypedTableCache[Handoff],
) -> None:
    await handoffs.create_if_absent("h-1", Handoff(owner="a", status=Status.SETTLED))

    result = await handoffs.replace_if(
        "h-1",
        Handoff(owner="b", status=Status.SETTLED),
        expected={"status": Status.PENDING},
    )

    assert result.transition is TableRowTransition.CONDITION_NOT_MET
    assert not result.written
    assert result.row == Handoff(owner="a", status=Status.SETTLED)
    assert await handoffs.get("h-1") == Handoff(owner="a", status=Status.SETTLED)


async def test_replace_if_reports_a_missing_row(
    handoffs: TypedTableCache[Handoff],
) -> None:
    result = await handoffs.replace_if(
        "nope",
        Handoff(owner="a", status=Status.SETTLED),
        expected={"status": Status.PENDING},
    )

    assert result.transition is TableRowTransition.MISSING
    assert result.row is None
    assert await handoffs.get("nope") is None


async def test_replace_if_matches_a_scalar_across_its_stored_encodings(
    handoffs: TypedTableCache[Handoff],
) -> None:
    """A caller may state the condition as the enum or as its value."""
    await handoffs.create_if_absent("h-1", Handoff(owner="a", status=Status.PENDING))

    by_value = await handoffs.replace_if(
        "h-1",
        Handoff(owner="a", status=Status.SETTLED),
        expected={"status": "pending", "attempts": 0},
    )

    assert by_value.transition is TableRowTransition.REPLACED


async def test_concurrent_conditional_replacement_settles_once(
    handoffs: TypedTableCache[Handoff],
) -> None:
    """No transition is lost: one contender replaces, the rest see it happened."""
    await handoffs.create_if_absent("h-1", Handoff(owner="a", status=Status.PENDING))

    results = await asyncio.gather(
        *(
            handoffs.replace_if(
                "h-1",
                Handoff(owner=f"owner-{index}", status=Status.SETTLED),
                expected={"status": Status.PENDING},
            )
            for index in range(20)
        )
    )

    replaced = [r for r in results if r.transition is TableRowTransition.REPLACED]
    assert len(replaced) == 1

    stored = await handoffs.get("h-1")
    assert stored is not None
    assert stored.status is Status.SETTLED
    for result in results:
        if result.transition is TableRowTransition.CONDITION_NOT_MET:
            assert result.row == stored


async def test_successful_transitions_apply_the_requested_ttl(
    table: ITableCache,
) -> None:
    handoffs = TypedTableCache(table, "handoffs", Handoff, default_ttl=600)

    await handoffs.create_if_absent(
        "h-1", Handoff(owner="a", status=Status.PENDING), ttl=120
    )
    assert 0 < await table.get_ttl("handoffs", "h-1") <= 120

    await handoffs.replace_if(
        "h-1",
        Handoff(owner="a", status=Status.SETTLED),
        expected={"status": Status.PENDING},
        ttl=300,
    )
    assert 120 < await table.get_ttl("handoffs", "h-1") <= 300


async def test_refused_transitions_leave_the_ttl_alone(table: ITableCache) -> None:
    handoffs = TypedTableCache(table, "handoffs", Handoff)

    await handoffs.create_if_absent(
        "h-1", Handoff(owner="a", status=Status.SETTLED), ttl=120
    )
    before = await table.get_ttl("handoffs", "h-1")

    await handoffs.create_if_absent(
        "h-1", Handoff(owner="b", status=Status.PENDING), ttl=3600
    )
    await handoffs.replace_if(
        "h-1",
        Handoff(owner="b", status=Status.SETTLED),
        expected={"status": Status.PENDING},
        ttl=3600,
    )

    after = await table.get_ttl("handoffs", "h-1")
    assert after <= before


async def test_invalid_rows_never_reach_storage(
    handoffs: TypedTableCache[Handoff],
) -> None:
    with pytest.raises(ValidationError):
        await handoffs.create_if_absent("h-1", {"owner": "a"})
    with pytest.raises(ValidationError):
        await handoffs.replace_if(
            "h-1", {"owner": "a", "status": "bogus"}, expected={"status": "pending"}
        )

    assert await handoffs.get("h-1") is None


async def test_partial_rows_are_rejected_before_storage(table: ITableCache) -> None:
    """The untyped contract still refuses a write that would erase a row."""
    with pytest.raises(ValueError, match="whole row"):
        await table.create_if_absent("handoffs", "h-1", {})


@pytest.mark.parametrize(
    "expected",
    [
        pytest.param({}, id="empty"),
        pytest.param({"owner": ["a"]}, id="non-scalar"),
    ],
)
async def test_unusable_conditions_are_rejected(
    handoffs: TypedTableCache[Handoff], expected: dict[str, Any]
) -> None:
    await handoffs.create_if_absent("h-1", Handoff(owner="a", status=Status.PENDING))

    with pytest.raises(ValueError):
        await handoffs.replace_if(
            "h-1", Handoff(owner="b", status=Status.SETTLED), expected=expected
        )

    assert await handoffs.get("h-1") == Handoff(owner="a", status=Status.PENDING)


async def test_replace_if_drops_fields_the_new_row_omits(
    table: ITableCache,
) -> None:
    """Replacement is a whole-row write, not a field merge, on every backend."""
    await table.create_if_absent(
        "handoffs", "h-1", {"owner": "a", "status": "pending", "stale": "yes"}
    )

    result = await table.replace_if(
        "handoffs",
        "h-1",
        {"owner": "a", "status": "settled"},
        expected={"status": "pending"},
    )

    assert result.transition is TableRowTransition.REPLACED
    assert await table.get("handoffs", "h-1") == {"owner": "a", "status": "settled"}


def test_transition_helpers_agree_on_what_counts_as_written(
    make_result: Callable[[TableRowTransition], Any],
) -> None:
    written = {TableRowTransition.CREATED, TableRowTransition.REPLACED}
    for transition in TableRowTransition:
        assert make_result(transition).written is (transition in written)


@pytest.fixture
def make_result() -> Callable[[TableRowTransition], Any]:
    from wappa.domain.interfaces.cache_interfaces import TableTransitionResult

    return TableTransitionResult
