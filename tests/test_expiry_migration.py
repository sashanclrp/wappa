"""Live legacy timer migration and retention on an explicitly supplied test Redis."""

import asyncio
import json
import os
import uuid

import pytest
import pytest_asyncio
from redis.asyncio import Redis
from typer.testing import CliRunner

from wappa.cli.main import app
from wappa.persistence.redis.expiry_index import RedisExpiryIndex
from wappa.persistence.redis.expiry_migration import _expiry_url, migrate_expiry_index
from wappa.persistence.redis.ops import delete, exists, expire, rename_if_absent
from wappa.persistence.redis.redis_client import POOL_DB_MAPPING, RedisClient
from wappa.persistence.redis.redis_handler.utils.inbox_cache import InboxCache

DATABASE = 13


@pytest_asyncio.fixture
async def store():
    url = os.getenv("WAPPA_TEST_REDIS_URL")
    if not url:
        pytest.skip("Explicit throwaway WAPPA_TEST_REDIS_URL required")
    client = Redis.from_url(_expiry_url(url, DATABASE))
    await client.ping()
    namespace = f"instagram__migration-{uuid.uuid4().hex}"
    # This isolated database is reserved for this test module's index.
    assert not await client.exists("__system__:expiry:due", "__system__:expiry:records")
    try:
        yield url, client, namespace
    finally:
        owned = [key async for key in client.scan_iter(match=f"*{namespace}*")]
        await client.delete(
            *owned, "__system__:expiry:due", "__system__:expiry:records"
        )
        await client.aclose()


async def test_dry_run_changes_no_values_ttls_or_index_keys(store):
    url, client, ns = store
    key = f"{ns}:EXPTRIGGER:reminder:opaque-id"
    await client.psetex(key, 2_000, b'"legacy-value"')
    before = await client.pttl(key)
    report = await migrate_expiry_index(url, database=DATABASE)
    assert report.eligible == 1 and report.indexed == 0
    assert await client.get(key) == b'"legacy-value"'
    assert 0 < await client.pttl(key) <= before
    assert not await client.exists("__system__:expiry:due", "__system__:expiry:records")


async def test_apply_preserves_the_timer_and_repeat_runs_preserve_the_occurrence(store):
    url, client, ns = store
    key = f"{ns}:EXPTRIGGER:reminder:opaque-id"
    await client.psetex(key, 2_000, b'"legacy-value"')
    before = await client.pttl(key)
    first = await migrate_expiry_index(url, apply=True, database=DATABASE)
    assert first.indexed == 1
    index = RedisExpiryIndex(client)
    record = await client.hget(index.records_key, key)
    score = await client.zscore(index.due_key, key)
    occurrence = json.loads(record)
    seconds, micros = await client.time()
    expected_due = seconds * 1000 + micros // 1000 + await client.pttl(key)
    assert abs(occurrence["due_at_ms"] - expected_due) < 50
    assert 0 < await client.pttl(key) <= before
    assert await client.get(key) == b'"legacy-value"'
    again = await migrate_expiry_index(url, apply=True, database=DATABASE)
    assert again.already_indexed == 1 and again.indexed == 0
    assert await client.hget(index.records_key, key) == record
    assert await client.zscore(index.due_key, key) == score
    assert (
        await client.pttl(index.due_key) == await client.pttl(index.records_key) == -1
    )
    # Let the original deadline elapse: no renewal or artificial index change.
    async with asyncio.timeout(4):
        while await client.exists(key):
            await asyncio.sleep(0.001)
    assert key.encode() in [entry.encode() for entry in await index.due(100)]
    claim = await index.claim(key)
    assert claim.generation == occurrence["generation"]
    assert await index.acknowledge(claim)


async def test_foreign_persistent_wrong_type_and_partial_index_keys_are_not_modified(
    store,
):
    url, client, ns = store
    invalid = f"foreign-{ns}:EXPTRIGGER:action:id"
    persistent = f"{ns}:EXPTRIGGER:persistent:id"
    wrong_type = f"{ns}:EXPTRIGGER:hash:id"
    conflict = f"{ns}:EXPTRIGGER:partial:id"
    malformed = f"{ns}:EXPTRIGGER:malformed:id"
    await client.set(invalid, "foreign", ex=60)
    await client.set(persistent, "keep")
    await client.hset(wrong_type, mapping={"keep": "yes"})
    await client.set(conflict, "legacy", ex=60)
    index = RedisExpiryIndex(client)
    await client.hset(index.records_key, conflict, "existing-record")
    await client.set(malformed, "legacy", ex=60)
    await client.hset(index.records_key, malformed, "not-json")
    await client.zadd(index.due_key, {malformed: 100})
    report = await migrate_expiry_index(url, apply=True, database=DATABASE)
    assert report.invalid == 2 and report.persistent == 1 and report.conflict == 2
    assert report.indexed == 0
    assert await client.get(invalid) == b"foreign"
    assert await client.get(persistent) == b"keep"
    assert await client.hget(wrong_type, "keep") == b"yes"
    assert await client.hget(index.records_key, conflict) == b"existing-record"
    assert await client.zscore(index.due_key, conflict) is None
    assert await client.hget(index.records_key, malformed) == b"not-json"
    assert await client.zscore(index.due_key, malformed) == 100
    result = await asyncio.to_thread(
        CliRunner().invoke,
        app,
        [
            "migrate",
            "expiry-index",
            "--redis-url",
            url,
            "--database",
            str(DATABASE),
            "--json",
        ],
    )
    assert result.exit_code == 1
    assert json.loads(result.output)["conflict"] == 2


@pytest.mark.parametrize("race", ["expire", "renew"])
async def test_atomic_snapshot_respects_expiry_and_renewal_during_scan(
    store, monkeypatch, race
):
    url, client, ns = store
    key = f"{ns}:EXPTRIGGER:race:id"
    await client.set(key, "legacy", ex=60)
    original = RedisExpiryIndex.index_existing

    async def intervene(index, found, *, apply=False):
        if race == "expire":
            await client.delete(found)
        else:
            await index.arm(found, 120)
        return await original(index, found, apply=apply)

    monkeypatch.setattr(RedisExpiryIndex, "index_existing", intervene)
    report = await migrate_expiry_index(url, apply=True, database=DATABASE)
    assert report.indexed == 0
    if race == "expire":
        assert report.expired == 1
        assert not await client.exists("__system__:expiry:records")
    else:
        assert report.already_indexed == 1
        assert await client.pttl(key) > 110_000


async def test_generic_cleanup_ttl_and_rename_preserve_recovery_indexes_and_shutdown(
    store,
):
    url, client, ns = store
    index = RedisExpiryIndex(client)
    key = f"{ns}:EXPTRIGGER:retained:id"
    await index.arm(key, 60)
    record = await client.hget(index.records_key, key)
    await client.set(f"{ns}:ordinary", "remove")
    # Route the production ops through this test-owned server only.
    await RedisClient.close()
    RedisClient.setup_multiple_urls(
        {
            alias: _expiry_url(url, DATABASE if alias == "expiry" else number)
            for alias, number in POOL_DB_MAPPING.items()
        }
    )
    try:
        cache = InboxCache(inbox=ns, redis_alias="expiry")
        assert await cache._delete_by_pattern(f"{ns}:ordinary") == 1
        assert await exists(index.due_key, index.records_key, alias="expiry") == 2
        assert await cache._delete_by_pattern("__system__:expiry:*") == 0
        assert await delete(index.due_key, index.records_key, alias="expiry") == 0
        assert not await expire(index.due_key, 1, alias="expiry")
        assert not await expire(index.records_key, 1, alias="expiry")
        with pytest.raises(ValueError, match="Reserved"):
            await rename_if_absent(index.records_key, f"{ns}:new", alias="expiry")
        with pytest.raises(ValueError, match="Reserved"):
            await rename_if_absent(key, index.records_key, alias="expiry")
        assert await client.hget(index.records_key, key) == record
        assert (
            await client.pttl(index.due_key)
            == await client.pttl(index.records_key)
            == -1
        )
        await RedisClient.close()
        # A fresh connection sees all timer data after Wappa pool cleanup.
        await client.ping()
        assert await client.hget(index.records_key, key) == record
        assert await client.exists(key)
    finally:
        await RedisClient.close()


async def test_cli_requires_explicit_url_and_reports_counts_without_identifiers(store):
    url, client, ns = store
    await client.set(f"{ns}:EXPTRIGGER:action:private-id", "private-value", ex=60)
    runner = CliRunner()
    missing = runner.invoke(app, ["migrate", "expiry-index"])
    assert missing.exit_code == 2
    dry = await asyncio.to_thread(
        runner.invoke,
        app,
        [
            "migrate",
            "expiry-index",
            "--redis-url",
            url,
            "--database",
            str(DATABASE),
            "--json",
        ],
    )
    assert dry.exit_code == 0, dry.output
    assert json.loads(dry.output)["eligible"] == 1
    assert "private-id" not in dry.output and "private-value" not in dry.output
    applied = await asyncio.to_thread(
        runner.invoke,
        app,
        [
            "migrate",
            "expiry-index",
            "--redis-url",
            url,
            "--database",
            str(DATABASE),
            "--apply",
            "--json",
        ],
    )
    assert applied.exit_code == 0, applied.output
    assert json.loads(applied.output)["indexed"] == 1


def test_cli_connection_errors_never_echo_connection_secrets(monkeypatch):
    from wappa.cli import expiry_migration

    async def fail(*args, **kwargs):
        raise RuntimeError("redis://user:password-secret@bad.example")

    monkeypatch.setattr(expiry_migration, "migrate_expiry_index", fail)
    result = CliRunner().invoke(
        app, ["migrate", "expiry-index", "--redis-url", "redis://bad.example"]
    )
    assert result.exit_code == 2
    assert "password-secret" not in result.output and "bad.example" not in result.output


def test_database_selection_is_explicit_and_retains_other_url_options():
    assert (
        _expiry_url("rediss://user:secret@localhost:6380/0?db=1&socket_timeout=3", 13)
        == "rediss://user:secret@localhost:6380/13?socket_timeout=3"
    )
    with pytest.raises(ValueError):
        _expiry_url("http://localhost", 3)
