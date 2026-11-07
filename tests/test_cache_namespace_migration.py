"""0.34: WhatsApp cache namespaces are qualified; old keys are migrated once,
and the Inbox Directory cache is cleared at startup."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from wappa.domain.inbox.identity import InboxRef
from wappa.persistence import create_cache_factory, create_system_table_cache
from wappa.persistence.inbox_directory import (
    ACCOUNT_INDEX_TABLE,
    PRIMARY_TABLE,
    InboxDirectoryTable,
)
from wappa.persistence.memory import storage_manager as memory_storage
from wappa.persistence.memory.handlers.utils import memory_store
from wappa.persistence.namespace_migration import (
    migrate_json_namespaces,
    migrate_redis_namespaces,
)

PNID = "999000111222333"  # fictional, never a real Inbox
REDIS_URL = os.getenv("WAPPA_TEST_REDIS_URL", "redis://localhost:6379")
TEST_DB = 15


def test_json_migration_renames_only_named_inboxes(tmp_path):
    (tmp_path / "users").mkdir()
    (tmp_path / "tables").mkdir()
    (tmp_path / "users" / f"{PNID}_CO.ABC.json").write_text("{}")
    (tmp_path / "tables" / f"{PNID}_tables.json").write_text("{}")
    (tmp_path / "tables" / "12345_tables.json").write_text("{}")  # Host scope

    dry = migrate_json_namespaces(tmp_path, [PNID])
    assert (
        len(dry.renamed) == 2 and (tmp_path / "users" / f"{PNID}_CO.ABC.json").exists()
    )

    done = migrate_json_namespaces(tmp_path, [PNID], apply=True)
    assert len(done.renamed) == 2
    assert (tmp_path / "users" / f"whatsapp__{PNID}_CO.ABC.json").exists()
    assert (tmp_path / "tables" / f"whatsapp__{PNID}_tables.json").exists()
    assert (tmp_path / "tables" / "12345_tables.json").exists()  # untouched
    assert migrate_json_namespaces(tmp_path, [PNID], apply=True).renamed == []


def test_migration_requires_explicit_digit_ids(tmp_path):
    with pytest.raises(ValueError):
        migrate_json_namespaces(tmp_path, [])
    with pytest.raises(ValueError):
        migrate_json_namespaces(tmp_path, ["whatsapp__1"])


async def test_redis_migration_keeps_ttl_and_never_overwrites():
    redis = pytest.importorskip("redis.asyncio")
    client = redis.from_url(f"{REDIS_URL}/{TEST_DB}", decode_responses=True)
    try:
        await client.ping()
    except Exception:
        pytest.skip("no local Redis")
    new = InboxRef.whatsapp(PNID).cache_namespace
    try:
        await client.set(f"{PNID}:state:form:CO.A", "s", ex=300)
        await client.set(f"{PNID}:user:CO.A", "u")
        await client.set(f"{PNID}:user:CO.B", "old")
        await client.set(f"{new}:user:CO.B", "already-new")

        dry = await migrate_redis_namespaces(REDIS_URL, [PNID], databases=[TEST_DB])
        assert len(dry.renamed) == 2 and len(dry.conflicts) == 1
        assert await client.exists(f"{PNID}:user:CO.A")

        done = await migrate_redis_namespaces(
            REDIS_URL, [PNID], apply=True, databases=[TEST_DB]
        )
        assert len(done.renamed) == 2
        assert done.conflicts == [f"db{TEST_DB}:{new}:user:CO.B"]
        assert 0 < await client.ttl(f"{new}:state:form:CO.A") <= 300
        assert await client.get(f"{new}:user:CO.A") == "u"
        assert await client.get(f"{new}:user:CO.B") == "already-new"
    finally:
        async for key in client.scan_iter(match=f"*{PNID}*"):
            await client.delete(key)
        await client.aclose()


@pytest.fixture
def fresh_memory_store(monkeypatch):
    """The memory backend is process-global; other tests leave Inbox Directory
    rows in it. Give this test an empty store so counts do not depend on order."""
    store = memory_store.MemoryStore()
    monkeypatch.setattr(memory_store, "_global_memory_store", store)
    monkeypatch.setattr(memory_storage.storage_manager, "memory_store", store)
    yield store
    store.stop_cleanup_task()


async def test_directory_clear_drops_rows_and_account_index(fresh_memory_store):
    cache = create_system_table_cache("memory")
    await cache.upsert(PRIMARY_TABLE, "whatsapp__1", {"x": 1})
    await cache.upsert(ACCOUNT_INDEX_TABLE, "whatsapp__9", {"x": 1})
    await cache.upsert("wappa_inbox_directory_extra", "k", {"x": 1})  # similar name
    await cache.upsert("wappa_sent_messages", "m1", {"x": 1})  # other System table
    host = create_cache_factory("memory")(inbox_id="whatsapp__1", user_id="u")
    host_table = host.create_table_cache()
    await host_table.upsert(
        PRIMARY_TABLE, "k", {"host": True}
    )  # same name, Inbox scope

    assert await InboxDirectoryTable(cache).clear() == 2
    assert await cache.get(PRIMARY_TABLE, "whatsapp__1") is None
    assert await cache.get("wappa_inbox_directory_extra", "k") is not None
    assert await cache.get("wappa_sent_messages", "m1") is not None
    assert await host_table.get(PRIMARY_TABLE, "k") is not None


# ── CLI: conflicts fail the command and the report is complete ──────────────


def _json_cache_with_conflicts(root: Path, count: int) -> None:
    users = root / "users"
    users.mkdir(parents=True)
    for n in range(count):
        (users / f"{PNID}_u{n}.json").write_text("{}")
        (users / f"whatsapp__{PNID}_u{n}.json").write_text("{}")
    (users / f"{PNID}_free.json").write_text("{}")


def _run_cli(root: Path, *extra: str) -> Any:
    from typer.testing import CliRunner

    from wappa.cli.main import app

    return CliRunner().invoke(
        app,
        ["migrate", "cache-namespaces", "-i", PNID, "--json-root", str(root), *extra],
        env={"REDIS_URL": ""},
    )


def test_cli_conflicts_exit_nonzero_on_dry_run_and_apply(tmp_path: Path) -> None:
    _json_cache_with_conflicts(tmp_path, 1)

    assert _run_cli(tmp_path).exit_code == 1
    assert _run_cli(tmp_path, "--apply").exit_code == 1
    # The free key still moved and the conflicting source was not overwritten.
    assert (tmp_path / "users" / f"whatsapp__{PNID}_free.json").exists()
    assert (tmp_path / "users" / f"{PNID}_u0.json").exists()


def test_cli_without_conflicts_exits_zero(tmp_path: Path) -> None:
    (tmp_path / "users").mkdir()
    (tmp_path / "users" / f"{PNID}_u.json").write_text("{}")

    assert _run_cli(tmp_path).exit_code == 0


def test_cli_json_report_is_complete_past_the_display_limit(tmp_path: Path) -> None:
    _json_cache_with_conflicts(tmp_path, 25)

    result = _run_cli(tmp_path, "--json")

    assert result.exit_code == 1
    report = json.loads(result.stdout)
    assert report["applied"] is False
    assert report["has_conflicts"] is True
    assert len(report["backends"]["JSON"]["conflicts"]) == 25
    assert len(report["backends"]["JSON"]["renamed"]) == 1


def test_cli_text_output_says_how_many_conflicts_it_hid(tmp_path: Path) -> None:
    _json_cache_with_conflicts(tmp_path, 25)

    result = _run_cli(tmp_path)

    assert "and 5 more" in result.stdout
