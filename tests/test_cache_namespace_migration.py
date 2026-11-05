"""0.34: WhatsApp cache namespaces are qualified; old keys are migrated once,
and the Inbox Directory cache is cleared at startup."""

from __future__ import annotations

import os

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
