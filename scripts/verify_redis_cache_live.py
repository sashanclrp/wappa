#!/usr/bin/env python
"""Live verification of RedisCacheFactory against a real Redis server.

Run it and watch: every step prints what it is about to do, what it expects,
what it actually observed, the raw Redis keys involved, and how long the call
took. Nothing is mocked — if a key shape or a TTL is wrong, you see it here in
the same form `redis-cli` would show you.

    uv run python scripts/verify_redis_cache_live.py
    uv run python scripts/verify_redis_cache_live.py --url redis://localhost:6379
    uv run python scripts/verify_redis_cache_live.py --keep    # skip cleanup

Every key this script writes lives under an inbox id prefixed
`wappa-verify-<pid>-`, so it cannot collide with real data, and it is deleted
on the way out unless you pass --keep.

Exit code is 0 only when every check passed.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from collections.abc import Awaitable, Callable, Sequence
from contextlib import suppress
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

# Allow `python scripts/verify_redis_cache_live.py` from a source checkout.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pydantic import BaseModel  # noqa: E402

from wappa.domain.interfaces.cache_interfaces import TableRowTransition  # noqa: E402
from wappa.persistence import TypedTableCache, VersionedTableCache  # noqa: E402
from wappa.persistence.redis.redis_cache_factory import RedisCacheFactory  # noqa: E402
from wappa.persistence.redis.redis_client import (  # noqa: E402
    POOL_DB_MAPPING,
    PoolAlias,
    RedisClient,
)
from wappa.persistence.redis.redis_handler.expiry import RedisExpiry  # noqa: E402
from wappa.persistence.redis.redis_handler.table import RedisTable  # noqa: E402
from wappa.persistence.redis.redis_handler.utils.key_factory import (  # noqa: E402
    KeyFactory,
)

# ── terminal helpers ────────────────────────────────────────────────────────

_COLOR = sys.stdout.isatty() and os.getenv("NO_COLOR") is None


def _c(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _COLOR else text


def bold(t: str) -> str:
    return _c(t, "1")


def dim(t: str) -> str:
    return _c(t, "2")


def green(t: str) -> str:
    return _c(t, "32")


def red(t: str) -> str:
    return _c(t, "31")


def yellow(t: str) -> str:
    return _c(t, "33")


def cyan(t: str) -> str:
    return _c(t, "36")


class Report:
    """Counts checks so the script can exit non-zero on the first real problem."""

    def __init__(self) -> None:
        self.passed = 0
        self.failed: list[str] = []
        self.timings: list[tuple[str, float]] = []

    def check(self, label: str, ok: bool, observed: object) -> bool:
        if ok:
            self.passed += 1
            print(f"    {green('✓')} {label}")
        else:
            self.failed.append(label)
            print(f"    {red('✗')} {label}")
            print(f"      {red('observed:')} {observed!r}")
        return ok

    def timed(self, label: str, seconds: float) -> None:
        self.timings.append((label, seconds))


report = Report()


def section(number: str, title: str) -> None:
    print()
    print(bold(f"═══ {number}  {title} " + "═" * max(0, 58 - len(title))))


def step(what: str) -> None:
    print(f"\n  {cyan('▸')} {bold(what)}")


def expect(what: str) -> None:
    print(f"    {dim('expect:')} {what}")


def observe(what: str) -> None:
    print(f"    {dim('observe:')} {what}")


async def timed[T](label: str, coro: Awaitable[T]) -> T:
    """Await a call, print how long the round trip took, and record it."""
    started = time.perf_counter()
    result = await coro
    elapsed = time.perf_counter() - started
    report.timed(label, elapsed)
    print(f"    {dim(f'{label} took {elapsed * 1000:.2f} ms')}")
    return result


# ── raw Redis inspection (what redis-cli would show you) ────────────────────


async def raw_keys(pattern: str, alias: PoolAlias) -> list[str]:
    from wappa.persistence.redis.ops import scan_keys

    found: list[str] = []
    cursor = 0
    while True:
        cursor, batch = await scan_keys(
            match_pattern=pattern, cursor=cursor, count=200, alias=alias
        )
        found.extend(batch)
        if cursor == 0:
            return sorted(found)


async def raw_field(key: str, alias: PoolAlias, field: str) -> str | None:
    """Read one hash field exactly as Redis stores it, with no deserialisation."""
    async with RedisClient.connection(alias=alias) as redis:
        return await redis.hget(key, field)


async def show_keys(
    pattern: str, alias: PoolAlias, *, with_values: bool = True
) -> None:
    """Print the raw keys, their type, TTL, and contents — like redis-cli."""
    keys = await raw_keys(pattern, alias)
    db = POOL_DB_MAPPING[alias]
    print(f"    {dim(f'redis db{db}  SCAN {pattern!r} → {len(keys)} key(s)')}")
    async with RedisClient.connection(alias=alias) as redis:
        for key in keys:
            key_type = await redis.type(key)
            ttl = await redis.ttl(key)
            ttl_text = (
                "no expiry" if ttl == -1 else "gone" if ttl == -2 else f"ttl={ttl}s"
            )
            print(f"      {yellow(key)}  {dim(f'[{key_type}, {ttl_text}]')}")
            if not with_values:
                continue
            if key_type == "hash":
                for field, value in sorted((await redis.hgetall(key)).items()):
                    shown = value if len(value) <= 88 else value[:85] + "…"
                    print(f"        {dim(f'{field} =')} {shown}")
            elif key_type == "string":
                value = await redis.get(key)
                print(f"        {dim('value =')} {value}")


# ── models used by the table checks ─────────────────────────────────────────


class HandoffState(StrEnum):
    PENDING = "pending"
    SETTLED = "settled"


class HandoffRow(BaseModel):
    owner: str
    state: HandoffState
    attempts: int = 0
    opened_at: datetime


class UserRow(BaseModel):
    name: str
    messages: int


class AgentRow(BaseModel):
    agent_id: str
    display_name: str


# ── the checks ──────────────────────────────────────────────────────────────


async def check_connection(url: str) -> None:
    section("00", "Connection and pool layout")

    step(f"Opening Wappa's five pools from one base URL: {url}")
    expect(
        "one pool per data domain, on databases "
        + ", ".join(f"{alias}=db{db}" for alias, db in POOL_DB_MAPPING.items())
    )
    await RedisClient.close()
    RedisClient.setup_single_url(url)

    for alias, db in POOL_DB_MAPPING.items():
        started = time.perf_counter()
        async with RedisClient.connection(alias=alias) as redis:
            pong = await redis.ping()
            info = await redis.client_info()
        elapsed = (time.perf_counter() - started) * 1000
        actual_db = info.get("db", "?")
        report.check(
            f"pool {alias!r} answers PING on db{db}",
            bool(pong) and actual_db == db,
            {"ping": pong, "db": actual_db},
        )
        print(f"      {dim(f'round trip {elapsed:.2f} ms')}")

    async with RedisClient.connection(alias="table") as redis:
        server = await redis.info("server")
    print(
        f"\n    {dim('server:')} Redis {server.get('redis_version')} "
        f"{dim('mode')} {server.get('redis_mode')} "
        f"{dim('uptime')} {server.get('uptime_in_days')}d"
    )


async def check_user_cache(factory: RedisCacheFactory, inbox: str, user: str) -> None:
    section("01", "User cache  (IUserCache, db0)")

    cache = factory.create_user_cache()
    key = f"{inbox}:user:{user}"

    step("Writing a user record with a 120s TTL")
    expect(f"one hash at {key}, ttl ≤ 120")
    written = {"name": "Ada", "messages": 4, "verified": True, "score": 9.5}
    ok = await timed("upsert", cache.upsert(written, ttl=120))
    report.check("upsert reported success", ok is True, ok)
    await show_keys(key, "users")

    ttl = await cache.get_ttl()
    report.check("TTL landed in (0, 120]", 0 < ttl <= 120, ttl)

    step("Reading it back")
    expect(f"{written} — ints, floats, and bools all survive the round trip")
    data = await timed("get", cache.get())
    observe(repr(data))
    report.check("read matches what was written", data == written, data)

    step("How booleans are spelled on the wire (ADR-0008)")
    expect(
        "a top-level bool stores as '1'/'0' — the spelling downstream apps read; "
        "a bool nested inside a JSON value keeps JSON spelling"
    )
    await cache.upsert(
        {
            "name": "Ada",
            "messages": 4,
            "verified": True,
            "muted": False,
            "prefs": {"beta": True},
        },
        ttl=120,
    )
    await show_keys(key, "users")
    raw = await raw_field(key, "users", "verified")
    observe(
        f"verified=True stored as {raw!r}; prefs keeps JSON: "
        f"{await raw_field(key, 'users', 'prefs')!r}"
    )
    report.check("a top-level bool stores as '1'", raw == "1", raw)
    report.check(
        "'0' is the false spelling",
        await raw_field(key, "users", "muted") == "0",
        await raw_field(key, "users", "muted"),
    )

    step("The accepted cost of that spelling, and its mitigation")
    expect(
        "an UNTYPED read cannot tell int 1 from True — both are '1'. Reading "
        "through a Pydantic model settles it. See ADR-0008."
    )
    await cache.update_field("messages", 1)
    untyped = (await cache.get() or {}).get("messages")
    typed = await cache.get(models=UserRow)
    observe(
        f"untyped read → {untyped!r} ({type(untyped).__name__}); "
        f"typed read → {typed.messages!r} ({type(typed.messages).__name__})"
    )
    report.check(
        "untyped read of int 1 returns True (documented, not a defect)",
        untyped is True,
        untyped,
    )
    report.check(
        "a typed int field returns a real int",
        typed.messages == 1 and not isinstance(typed.messages, bool),
        typed.messages,
    )
    await cache.upsert({"name": "Ada", "messages": 1}, ttl=120)

    step("Atomically incrementing a counter field (HINCRBY, not read-modify-write)")
    expect("messages goes 1 → 6")
    new_value = await timed("increment_field", cache.increment_field("messages", 5))
    report.check("increment returned 6", new_value == 6, new_value)

    step("Appending to a list field")
    expect("tags = ['vip']")
    await timed("append_to_list", cache.append_to_list("tags", "vip"))
    tags = await cache.get_field("tags")
    report.check("list field round-trips", tags == ["vip"], tags)
    await show_keys(key, "users")

    step("Deleting the record")
    expect("1 key deleted, then exists() is False")
    deleted = await timed("delete", cache.delete())
    report.check("delete removed exactly one key", deleted == 1, deleted)
    report.check("record is gone", await cache.exists() is False, None)


async def check_state_cache(factory: RedisCacheFactory, inbox: str, user: str) -> None:
    section("02", "State cache  (IStateCache, db1)")

    cache = factory.create_state_cache()

    step("Writing two handler states for this user")
    expect(f"{inbox}:state:onboarding:{user} and {inbox}:state:checkout:{user}")
    await timed("upsert onboarding", cache.upsert("onboarding", {"step": 2}, ttl=120))
    await timed("upsert checkout", cache.upsert("checkout", {"cart": 3}, ttl=120))
    await show_keys(f"{inbox}:state:*", "state_handler")

    step("Listing handlers for this user")
    expect("['checkout', 'onboarding'] in some order")
    handlers = await timed("list_handlers", cache.list_handlers())
    observe(repr(handlers))
    report.check(
        "both handlers listed", sorted(handlers) == ["checkout", "onboarding"], handlers
    )

    step("Finding which users sit in a given handler (inbox-wide, classmethod)")
    expect(f"['{user}']")
    users = await timed(
        "list_users_with_handler",
        type(cache).list_users_with_handler(inbox_id=inbox, handler_name="checkout"),
    )
    report.check("this user is listed", users == [user], users)

    step("Deleting every state for this user")
    expect("2 keys deleted")
    deleted = await timed("delete_all_for_user", cache.delete_all_for_user())
    report.check("both handler states removed", deleted == 2, deleted)
    await show_keys(f"{inbox}:state:*", "state_handler")


async def check_table_cache_basics(factory: RedisCacheFactory, inbox: str) -> None:
    section("03", "Table cache basics  (ITableCache, db2)")

    table = factory.create_table_cache()

    step("Upserting three product rows")
    expect(f"three hashes named {inbox}:df:products:pkid:<sku>")
    for sku, name, price in [
        ("sku-1", "Widget", 99),
        ("sku-2", "Gadget", 149),
        ("sku-3", "Doohickey", 12),
    ]:
        await table.upsert("products", sku, {"name": name, "price": price}, ttl=120)
    await show_keys(f"{inbox}:df:products:*", "table")

    step("Listing primary keys")
    expect("['sku-1', 'sku-2', 'sku-3']")
    pkids = await timed("list_pkids", table.list_pkids("products"))
    report.check(
        "all three pkids listed", sorted(pkids) == ["sku-1", "sku-2", "sku-3"], pkids
    )

    step("Reading every row at once")
    rows = await timed("get_all", table.get_all("products"))
    report.check("get_all returned three rows", len(rows) == 3, len(rows))

    step("Searching by field value (SCAN + HGET, no KEYS)")
    expect("the Gadget row")
    found = await timed(
        "find_by_field", table.find_by_field("products", "name", "Gadget")
    )
    report.check(
        "found the right row", found == {"name": "Gadget", "price": 149}, found
    )

    step("Dropping the whole table")
    expect("3 rows deleted, no keys left")
    deleted = await timed("delete_table", table.delete_table("products"))
    report.check("delete_table removed three rows", deleted == 3, deleted)
    await show_keys(f"{inbox}:df:products:*", "table")


async def check_typed_table_cache(factory: RedisCacheFactory, inbox: str) -> None:
    section("04", "TypedTableCache  (Pydantic SERDE over the same rows)")

    handoffs: TypedTableCache[HandoffRow] = TypedTableCache(
        factory.create_table_cache(),
        "handoffs",
        HandoffRow,
        default_ttl=120,
        cache_space="verify",
    )

    step("Writing a typed row — note the cache_space folded into the table name")
    expect(f"one hash at {inbox}:df:verify_handoffs:pkid:h-1")
    row = HandoffRow(
        owner="agent-a",
        state=HandoffState.PENDING,
        attempts=1,  # the value that is ambiguous when read back untyped
        opened_at=datetime.now(UTC),
    )
    await timed("upsert", handoffs.upsert("h-1", row))
    await show_keys(f"{inbox}:df:verify_handoffs:*", "table")
    print(
        f"    {dim('↑ enums store as their value, datetimes as ISO-8601, ints as digits')}"
    )

    step("Reading it back as a model instance")
    expect("a HandoffRow equal to what we wrote, with real enum and datetime types")
    back = await timed("get", handoffs.get("h-1"))
    observe(repr(back))
    report.check("round trip is loss-free", back == row, back)
    report.check(
        "state came back as the enum member",
        back is not None and back.state is HandoffState.PENDING,
        back.state if back else None,
    )
    report.check(
        "attempts=1 came back as int, not bool (the model settles the ambiguity)",
        back is not None and back.attempts == 1 and not isinstance(back.attempts, bool),
        (back.attempts, type(back.attempts).__name__) if back else None,
    )
    report.check(
        "opened_at came back as a datetime",
        back is not None and isinstance(back.opened_at, datetime),
        type(back.opened_at).__name__ if back else None,
    )

    step("Rejecting a row that does not validate")
    expect("ValidationError, and nothing written")
    try:
        await handoffs.upsert("h-bad", {"owner": "x", "state": "not-a-state"})
        report.check(
            "invalid row was rejected before storage", False, "no error raised"
        )
    except Exception as exc:
        observe(f"{type(exc).__name__}: {str(exc).splitlines()[0]}")
        report.check(
            "invalid row was rejected before storage",
            not await handoffs.exists("h-bad"),
            "a key was written anyway",
        )

    await handoffs.delete("h-1")


async def check_atomic_transitions(factory: RedisCacheFactory, inbox: str) -> None:
    section("05", "Atomic row transitions  (the new create_if_absent / replace_if)")

    handoffs: TypedTableCache[HandoffRow] = TypedTableCache(
        factory.create_table_cache(), "handoffs", HandoffRow, default_ttl=120
    )
    key = f"{inbox}:df:handoffs:pkid:h-1"

    def make(owner: str, state: HandoffState) -> HandoffRow:
        return HandoffRow(owner=owner, state=state, opened_at=datetime.now(UTC))

    step("Claiming a row that does not exist yet")
    expect("transition=created, written=True, no blocking row returned")
    first = await timed(
        "create_if_absent (winner)",
        handoffs.create_if_absent("h-1", make("agent-a", HandoffState.PENDING)),
    )
    observe(
        f"transition={first.transition.value} written={first.written} row={first.row}"
    )
    report.check(
        "first claim created the row",
        first.transition is TableRowTransition.CREATED,
        first,
    )
    await show_keys(key, "table")

    step("A second caller claiming the same row")
    expect(
        "transition=already_exists, and the winning row handed back so we need no re-read"
    )
    second = await timed(
        "create_if_absent (loser)",
        handoffs.create_if_absent("h-1", make("agent-b", HandoffState.PENDING)),
    )
    observe(
        f"transition={second.transition.value} row.owner={second.row.owner if second.row else None}"
    )
    report.check(
        "second claim was refused",
        second.transition is TableRowTransition.ALREADY_EXISTS,
        second,
    )
    report.check(
        "the loser was told who won",
        second.row is not None and second.row.owner == "agent-a",
        second.row,
    )

    step("50 coroutines racing to claim a fresh row")
    expect(
        "exactly 1 'created', 49 'already_exists', and every loser sees the same winner"
    )
    started = time.perf_counter()
    results = await asyncio.gather(
        *(
            handoffs.create_if_absent(
                "race", make(f"agent-{i:02d}", HandoffState.PENDING)
            )
            for i in range(50)
        )
    )
    elapsed = time.perf_counter() - started
    report.timed("50-way create race", elapsed)
    created = [r for r in results if r.transition is TableRowTransition.CREATED]
    losers = [r for r in results if r.transition is TableRowTransition.ALREADY_EXISTS]
    stored = await handoffs.get("race")
    observe(
        f"created={len(created)} already_exists={len(losers)} "
        f"stored owner={stored.owner if stored else None} "
        f"in {elapsed * 1000:.1f} ms total"
    )
    report.check("exactly one winner", len(created) == 1, len(created))
    report.check("every other caller was refused", len(losers) == 49, len(losers))
    report.check(
        "every loser was shown the row that actually won",
        all(r.row == stored for r in losers),
        "at least one loser saw a different row",
    )

    step("Conditional replace while the condition still holds")
    expect("transition=replaced; the row moves pending → settled")
    replaced = await timed(
        "replace_if (match)",
        handoffs.replace_if(
            "h-1",
            make("agent-a", HandoffState.SETTLED),
            expected={"state": HandoffState.PENDING},
        ),
    )
    report.check(
        "transition applied",
        replaced.transition is TableRowTransition.REPLACED,
        replaced,
    )
    await show_keys(key, "table")

    step("The same conditional replace, now that the row has moved on")
    expect("transition=condition_not_met, the stored row unchanged and handed back")
    stale = await timed(
        "replace_if (stale)",
        handoffs.replace_if(
            "h-1",
            make("agent-c", HandoffState.SETTLED),
            expected={"state": HandoffState.PENDING},
        ),
    )
    observe(
        f"transition={stale.transition.value} "
        f"row.owner={stale.row.owner if stale.row else None} "
        f"row.state={stale.row.state.value if stale.row else None}"
    )
    report.check(
        "the second transition was refused",
        stale.transition is TableRowTransition.CONDITION_NOT_MET,
        stale,
    )
    current = await handoffs.get("h-1")
    report.check(
        "the stored row was not touched",
        current is not None and current.owner == "agent-a",
        current,
    )

    step("Stating the condition as a plain string instead of the enum member")
    expect("same answer — one canonical encoding is used on both sides")
    by_value = await handoffs.replace_if(
        "h-1", make("agent-d", HandoffState.PENDING), expected={"state": "settled"}
    )
    report.check(
        "'settled' matched HandoffState.SETTLED",
        by_value.transition is TableRowTransition.REPLACED,
        by_value,
    )

    step("Conditionally replacing a row that does not exist")
    expect("transition=missing (distinct from condition_not_met)")
    missing = await handoffs.replace_if(
        "ghost", make("agent-a", HandoffState.SETTLED), expected={"state": "pending"}
    )
    report.check(
        "missing row reported as missing",
        missing.transition is TableRowTransition.MISSING,
        missing,
    )
    report.check(
        "no key was created for it", not await handoffs.exists("ghost"), "a key exists"
    )

    step("TTL behaviour: refused transitions must not touch the clock")
    table = factory.create_table_cache()
    await handoffs.create_if_absent(
        "ttl-probe", make("agent-a", HandoffState.SETTLED), ttl=30
    )
    before = await table.get_ttl("handoffs", "ttl-probe")
    expect(f"ttl stays at ~{before}s even though the refused calls asked for 3600s")
    await handoffs.create_if_absent(
        "ttl-probe", make("agent-b", HandoffState.PENDING), ttl=3600
    )
    await handoffs.replace_if(
        "ttl-probe",
        make("agent-b", HandoffState.SETTLED),
        expected={"state": HandoffState.PENDING},
        ttl=3600,
    )
    after = await table.get_ttl("handoffs", "ttl-probe")
    observe(f"ttl before={before}s after two refused calls={after}s")
    report.check("TTL survived both refusals", after <= before, after)

    step("A successful transition does apply the requested TTL")
    expect("ttl jumps to ~300s")
    await handoffs.replace_if(
        "ttl-probe",
        make("agent-b", HandoffState.PENDING),
        expected={"state": HandoffState.SETTLED},
        ttl=300,
    )
    renewed = await table.get_ttl("handoffs", "ttl-probe")
    observe(f"ttl={renewed}s")
    report.check("TTL was applied on the write", 240 < renewed <= 300, renewed)

    step("Replacement is a whole-row write, not a field merge")
    raw = factory.create_table_cache()
    await raw.create_if_absent(
        "merge_probe", "p-1", {"state": "pending", "owner": "a", "leftover": "yes"}
    )
    await show_keys(f"{inbox}:df:merge_probe:*", "table")
    expect("after replacing with a row that has no 'leftover', the field is gone")
    await raw.replace_if(
        "merge_probe",
        "p-1",
        {"state": "settled", "owner": "a"},
        expected={"state": "pending"},
    )
    await show_keys(f"{inbox}:df:merge_probe:*", "table")
    final = await raw.get("merge_probe", "p-1")
    report.check(
        "stale field was dropped", final == {"state": "settled", "owner": "a"}, final
    )

    step("50 coroutines racing to settle one pending row")
    expect("exactly 1 'replaced', 49 'condition_not_met' — no transition is lost")
    await handoffs.upsert("settle", make("agent-a", HandoffState.PENDING))
    started = time.perf_counter()
    settle_results = await asyncio.gather(
        *(
            handoffs.replace_if(
                "settle",
                make(f"agent-{i:02d}", HandoffState.SETTLED),
                expected={"state": HandoffState.PENDING},
            )
            for i in range(50)
        )
    )
    elapsed = time.perf_counter() - started
    report.timed("50-way settle race", elapsed)
    winners = [r for r in settle_results if r.transition is TableRowTransition.REPLACED]
    refused = [
        r
        for r in settle_results
        if r.transition is TableRowTransition.CONDITION_NOT_MET
    ]
    observe(
        f"replaced={len(winners)} condition_not_met={len(refused)} in {elapsed * 1000:.1f} ms total"
    )
    report.check("exactly one settlement won", len(winners) == 1, len(winners))
    report.check("every other contender was refused", len(refused) == 49, len(refused))

    step("Rejecting conditions the contract cannot honour")
    for label, expected_condition in [
        ("empty condition", {}),
        ("non-scalar condition", {"owner": ["a", "b"]}),
    ]:
        try:
            await handoffs.replace_if(
                "h-1", make("x", HandoffState.SETTLED), expected=expected_condition
            )
            report.check(f"{label} rejected", False, "no error raised")
        except ValueError as exc:
            observe(f"ValueError: {exc}")
            report.check(f"{label} rejected", True, None)

    for pkid in ("h-1", "race", "settle", "ttl-probe"):
        await handoffs.delete(pkid)
    await factory.create_table_cache().delete_table("merge_probe")


async def check_versioned_table_cache(factory: RedisCacheFactory, inbox: str) -> None:
    section("06", "VersionedTableCache  (bump-to-invalidate)")

    agents: VersionedTableCache[AgentRow] = VersionedTableCache(
        factory.create_table_cache(),
        "agents",
        AgentRow,
        default_ttl=120,
        cache_space="verify",
    )

    step("Writing two rows into generation v1")
    expect(f"keys under {inbox}:df:verify_agents@v1:pkid:*")
    await agents.upsert("a-1", AgentRow(agent_id="a-1", display_name="Ada"))
    await agents.upsert("a-2", AgentRow(agent_id="a-2", display_name="Grace"))
    print(f"    {dim('current table:')} {await agents.current_table_name()}")
    await show_keys(f"{inbox}:df:verify_agents*", "table", with_values=False)

    step("Bumping the generation — one counter increment, no key enumeration")
    expect("version 1 → 2, and every previous row becomes unreachable at once")
    version = await timed("bump_version", agents.bump_version())
    observe(f"version={version}, table={await agents.current_table_name()}")
    report.check("version advanced to 2", version == 2, version)
    report.check(
        "v1 rows are unreachable",
        await agents.get("a-1") is None,
        await agents.get("a-1"),
    )

    step("Looking at Redis directly")
    expect(
        "the v1 hashes still exist as orphans; they are reclaimed by TTL, not by a scan"
    )
    await show_keys(f"{inbox}:df:verify_agents*", "table", with_values=False)
    print(f"    {dim('and the generation counter itself:')}")
    await show_keys(f"{inbox}:df:*_wappa_table_versions*", "table")
    print(
        f"    {dim('↑ one counter row per logical table. `bumps=1` means generation 2 —')}"
    )
    print(f"      {dim('a table that was never bumped needs no row at all.')}")

    step("Atomic transitions work inside the current generation too")
    created = await agents.create_if_absent(
        "a-1", AgentRow(agent_id="a-1", display_name="Ada v2")
    )
    report.check(
        "created in v2", created.transition is TableRowTransition.CREATED, created
    )
    replaced = await agents.replace_if(
        "a-1",
        AgentRow(agent_id="a-1", display_name="Ada v3"),
        expected={"display_name": "Ada v2"},
    )
    report.check(
        "conditionally replaced in v2",
        replaced.transition is TableRowTransition.REPLACED,
        replaced,
    )


async def check_expiry_cache(factory: RedisCacheFactory, inbox: str, user: str) -> None:
    section("07", "Expiry cache  (IExpiryCache, db3)")

    cache = factory.create_expiry_cache()

    step("Arming a trigger that fires in 60s")
    expect(f"a string key at {inbox}:EXPTRIGGER:payment_reminder:TXN-1 with ttl ≤ 60")
    await timed("set", cache.set("payment_reminder", "TXN-1", ttl_seconds=60))
    await show_keys(f"{inbox}:EXPTRIGGER:*", "expiry")
    ttl = await cache.get_ttl("payment_reminder", "TXN-1")
    report.check("trigger TTL is in (0, 60]", 0 < ttl <= 60, ttl)

    step("Watching a short trigger actually expire")
    expect("2s trigger disappears on its own — this is what drives expiry callbacks")
    await cache.set("smoke_test", "SHORT", ttl_seconds=2)
    report.check(
        "trigger exists immediately", await cache.exists("smoke_test", "SHORT"), None
    )
    print(f"    {dim('sleeping 2.5s…')}")
    await asyncio.sleep(2.5)
    gone = not await cache.exists("smoke_test", "SHORT")
    report.check("trigger expired by itself", gone, "still present")

    step("Clearing every trigger for one business identifier")
    expect("the TXN-1 trigger goes, regardless of which action armed it")
    deleted = await timed(
        "delete_all_by_identifier", cache.delete_all_by_identifier("TXN-1")
    )
    report.check("the transaction's trigger was cleared", deleted == 1, deleted)

    step("Clearing the triggers a user is the identifier for")
    expect(
        "a trigger key is {inbox}:EXPTRIGGER:{action}:{identifier} — it carries no "
        "user, so the caller says which identifier it means"
    )
    await cache.set("session_timeout", user, ttl_seconds=60)
    await cache.set("invoice_due", "INV-9", ttl_seconds=60)
    await show_keys(f"{inbox}:EXPTRIGGER:*", "expiry")
    deleted = await timed(
        "delete_all_by_identifier(user_id)", cache.delete_all_by_identifier(user)
    )
    observe(f"deleted={deleted} — the user-keyed one; INV-9 is a different identifier")
    report.check("only the user-keyed trigger was removed", deleted == 1, deleted)
    report.check(
        "the unrelated trigger survived",
        await cache.exists("invoice_due", "INV-9"),
        "it was removed too",
    )
    report.check(
        "there is no delete_all_for_user() here to mean something else",
        not hasattr(cache, "delete_all_for_user"),
        "the misleading method is back",
    )
    await show_keys(f"{inbox}:EXPTRIGGER:*", "expiry")
    await cache.delete("invoice_due", "INV-9")


async def check_ai_state_cache(
    factory: RedisCacheFactory, inbox: str, user: str
) -> None:
    section("08", "AI state cache  (IAIStateCache, db4)")

    cache = factory.create_ai_state_cache()

    step("Storing per-agent state for this user")
    expect(f"{inbox}:aistate:summarizer:{user}")
    await timed(
        "upsert", cache.upsert("summarizer", {"turns": 1, "model": "opus"}, ttl=120)
    )
    await show_keys(f"{inbox}:aistate:*", "ai_state")

    step("Incrementing the turn counter")
    turns = await timed(
        "increment_field", cache.increment_field("summarizer", "turns", 2)
    )
    report.check("turns went 1 → 3", turns == 3, turns)

    step("Deleting the agent state")
    report.check("delete removed one key", await cache.delete("summarizer") == 1, None)


async def check_context_override(
    factory: RedisCacheFactory, inbox: str, user: str
) -> None:
    section("09", "Hybrid context  (per-call overrides on one factory)")

    step("Same factory, one call overriding user_id")
    expect("two distinct keys — the factory default and the override do not collide")
    default_cache = factory.create_user_cache()
    override_cache = factory.create_user_cache(user_id=f"{user}-other")
    await default_cache.upsert({"who": "default"}, ttl=60)
    await override_cache.upsert({"who": "override"}, ttl=60)
    await show_keys(f"{inbox}:user:*", "users")

    a = await default_cache.get()
    b = await override_cache.get()
    observe(f"default={a} override={b}")
    report.check("the two contexts stayed separate", a != b, (a, b))

    await default_cache.delete()
    await override_cache.delete()


async def check_glob_safety(url: str) -> None:
    section("10", "Glob safety  (identifiers that carry SCAN syntax)")

    hostile = f"wappa-verify-{os.getpid()}-glob[1]*"
    print(f"    {dim('using inbox_id:')} {yellow(hostile)}")
    print(
        f"    {dim('every bulk op is a SCAN glob, so an unescaped [ ] * ? in a literal')}"
    )
    print(f"      {dim('segment would build a pattern that matches nothing at all.')}")

    table = RedisTable(inbox=hostile)
    try:
        step("Writing two rows under that inbox, then dropping the table")
        expect("delete_table reports 2, not a silent 0")
        await table.upsert("rows", "a", {"v": 1}, ttl=60)
        await table.upsert("rows", "b", {"v": 2}, ttl=60)
        await show_keys(f"{KeyFactory.glob_escape(hostile)}:df:*", "table")

        listed = await timed("list_pkids", table.list_pkids("rows"))
        report.check("both rows are enumerable", sorted(listed) == ["a", "b"], listed)

        found = await timed("find_by_field", table.find_by_field("rows", "v", 2))
        report.check("find_by_field still matches", found == {"v": 2}, found)

        deleted = await timed("delete_table", table.delete_table("rows"))
        observe(f"deleted={deleted}")
        report.check("delete_table removed both rows", deleted == 2, deleted)
        report.check("nothing is left", await table.list_pkids("rows") == [], None)

        step("The same hazard on an expiry identifier")
        expect("both TXN[1] triggers cleared, the unrelated one kept")
        expiry = RedisExpiry(inbox=hostile, user_id="user[9]")
        await expiry.set("reminder", "TXN[1]", ttl_seconds=60)
        await expiry.set("timeout", "TXN[1]", ttl_seconds=60)
        await expiry.set("reminder", "OTHER", ttl_seconds=60)
        cleared = await timed(
            "delete_all_by_identifier", expiry.delete_all_by_identifier("TXN[1]")
        )
        report.check("both bracketed triggers cleared", cleared == 2, cleared)
        report.check(
            "the unrelated trigger survived",
            await expiry.exists("reminder", "OTHER"),
            "it was removed too",
        )
        await expiry.delete("reminder", "OTHER")
    finally:
        await table.delete("rows", "a")
        await table.delete("rows", "b")


async def cleanup(inbox: str) -> None:
    section("11", "Cleanup")
    total = 0
    for alias in POOL_DB_MAPPING:
        keys = await raw_keys(f"{inbox}:*", alias)
        if not keys:
            continue
        async with RedisClient.connection(alias=alias) as redis:
            total += await redis.delete(*keys)
        print(
            f"    {dim(f'db{POOL_DB_MAPPING[alias]} ({alias}): deleted {len(keys)} key(s)')}"
        )
    print(f"\n    {green('✓')} removed {total} key(s) written by this run")

    leftovers: list[str] = []
    for alias in POOL_DB_MAPPING:
        leftovers.extend(await raw_keys(f"{inbox}:*", alias))
    report.check("no keys left behind", not leftovers, leftovers)


def print_summary(inbox: str, kept: bool) -> int:
    section("△", "Summary")

    slowest: Sequence[tuple[str, float]] = sorted(
        report.timings, key=lambda item: item[1], reverse=True
    )[:8]
    print("\n  Slowest operations:")
    for label, seconds in slowest:
        print(f"    {seconds * 1000:8.2f} ms  {dim(label)}")

    single_calls = [t for label, t in report.timings if "race" not in label]
    if single_calls:
        avg = sum(single_calls) / len(single_calls) * 1000
        print(
            f"\n  {dim(f'mean single round trip: {avg:.2f} ms over {len(single_calls)} calls')}"
        )

    total = report.passed + len(report.failed)
    print()
    if report.failed:
        print(red(bold(f"  ✗ {len(report.failed)} of {total} checks FAILED:")))
        for label in report.failed:
            print(red(f"      · {label}"))
        return 1

    print(green(bold(f"  ✓ all {total} checks passed")))
    if kept:
        print(yellow(f"\n  --keep was set: keys under {inbox}:* were left in Redis."))
        print(yellow("  Inspect them with:"))
        for alias, db in POOL_DB_MAPPING.items():
            print(
                yellow(f"    redis-cli -n {db} --scan --pattern '{inbox}:*'")
                + dim(f"   # {alias}")
            )
        print(
            yellow(
                "  Remove them with the same command piped into `xargs redis-cli -n <db> del`."
            )
        )
    return 0


async def run(url: str, keep: bool) -> int:
    inbox = f"wappa-verify-{os.getpid()}"
    user = "573001112233"

    print(bold("\nWappa · live RedisCacheFactory verification"))
    print(dim(f"  redis     {url}"))
    print(dim(f"  inbox_id  {inbox}   (every key this run writes is namespaced by it)"))
    print(dim(f"  user_id   {user}"))
    print(dim(f"  started   {datetime.now().isoformat(timespec='seconds')}"))

    started = time.perf_counter()
    try:
        await check_connection(url)

        factory = RedisCacheFactory(inbox_id=inbox, user_id=user)
        print(
            f"\n  {dim(f'factory built: RedisCacheFactory(inbox_id={inbox!r}, user_id={user!r})')}"
        )

        checks: list[Callable[[], Awaitable[Any]]] = [
            lambda: check_user_cache(factory, inbox, user),
            lambda: check_state_cache(factory, inbox, user),
            lambda: check_table_cache_basics(factory, inbox),
            lambda: check_typed_table_cache(factory, inbox),
            lambda: check_atomic_transitions(factory, inbox),
            lambda: check_versioned_table_cache(factory, inbox),
            lambda: check_expiry_cache(factory, inbox, user),
            lambda: check_ai_state_cache(factory, inbox, user),
            lambda: check_context_override(factory, inbox, user),
            lambda: check_glob_safety(url),
        ]
        for check in checks:
            await check()

        if not keep:
            await cleanup(inbox)
    finally:
        with suppress(Exception):
            await RedisClient.close()

    elapsed = time.perf_counter() - started
    exit_code = print_summary(inbox, keep)
    print(dim(f"\n  wall clock: {elapsed:.2f}s\n"))
    return exit_code


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--url",
        default=os.getenv("WAPPA_TEST_REDIS_URL", "redis://localhost:6379"),
        help="Base Redis URL; Wappa appends /0../4 for its five pools.",
    )
    parser.add_argument(
        "--keep",
        action="store_true",
        help="Leave this run's keys in Redis so you can inspect them yourself.",
    )
    args = parser.parse_args()
    try:
        return asyncio.run(run(args.url, args.keep))
    except KeyboardInterrupt:
        print(yellow("\n  interrupted"))
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
