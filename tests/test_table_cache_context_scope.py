"""Table Cache ``context_id`` rename, compatibility, and the System Scope (PRD 1)."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from wappa.domain.inbox import InboxRef
from wappa.domain.interfaces.cache_interfaces import ITableCache
from wappa.persistence import (
    SYSTEM_SCOPE,
    create_cache_factory,
    create_system_table_cache,
)
from wappa.persistence.json.handlers.table_handler import JSONTable
from wappa.persistence.json.handlers.utils.file_manager import file_manager
from wappa.persistence.memory.handlers.table_handler import MemoryTable
from wappa.persistence.redis.redis_client import RedisClient
from wappa.persistence.redis.redis_handler.table import RedisTable
from wappa.persistence.redis.redis_handler.utils.key_factory import KeyFactory
from wappa.schemas.core.types import PlatformType

REDIS_URL = os.getenv("WAPPA_TEST_REDIS_URL", "redis://localhost:6379")
TABLE_CLASSES = [MemoryTable, JSONTable, RedisTable]


@pytest.mark.parametrize("table_class", TABLE_CLASSES)
def test_positional_construction_keeps_the_same_key(table_class: type) -> None:
    table = table_class("123")

    assert table.context_id == "123"
    assert table._key("products", "sku") == KeyFactory().table("123", "products", "sku")


@pytest.mark.parametrize("table_class", TABLE_CLASSES)
def test_context_id_keyword_produces_the_same_key_as_the_old_inbox_value(
    table_class: type,
) -> None:
    """Migrating ``inbox_id="123"`` to ``context_id="123"`` changes no stored key."""
    table = table_class(context_id="123")

    assert table._key("products", "sku") == "123:df:products:pkid:sku"


@pytest.mark.parametrize("table_class", TABLE_CLASSES)
@pytest.mark.parametrize("stale_keyword", ["inbox_id", "inbox"])
def test_stale_keywords_fail_at_construction(
    table_class: type, stale_keyword: str
) -> None:
    with pytest.raises(TypeError):
        table_class(**{stale_keyword: "123"})


@pytest.mark.parametrize("table_class", TABLE_CLASSES)
def test_blank_context_id_is_rejected(table_class: type) -> None:
    with pytest.raises(ValueError):
        table_class("   ")


@pytest.mark.parametrize("cache_type", ["memory", "json", "redis"])
def test_system_table_builder_uses_the_exact_system_scope(cache_type: str) -> None:
    table = create_system_table_cache(cache_type)

    assert table.context_id == SYSTEM_SCOPE
    assert table.context_id == "__system__"
    assert (
        table._key("wappa_inbox_directory", "x")
        == "__system__:df:wappa_inbox_directory:pkid:x"
    )


def test_system_table_builder_rejects_unknown_backends() -> None:
    with pytest.raises(ValueError):
        create_system_table_cache("cassandra")


@pytest.mark.parametrize("cache_type", ["memory", "json"])
def test_cache_factory_defaults_table_context_to_its_inbox(cache_type: str) -> None:
    factory = create_cache_factory(cache_type)(inbox_id="555", user_id="u")

    assert factory.create_table_cache().context_id == "555"


@pytest.mark.parametrize("cache_type", ["memory", "json"])
def test_cache_factory_accepts_a_host_defined_business_context(
    cache_type: str,
) -> None:
    """A Host-defined Owner context works without Wappa learning Owner semantics."""
    factory = create_cache_factory(cache_type)(inbox_id="555", user_id="u")

    owner_table = factory.create_table_cache(context_id="owner-7")

    assert owner_table.context_id == "owner-7"
    assert owner_table._key("agents", "a1") == "owner-7:df:agents:pkid:a1"


@pytest.mark.parametrize("cache_type", ["memory", "json"])
def test_cache_factory_rejects_the_stale_table_keyword(cache_type: str) -> None:
    factory = create_cache_factory(cache_type)(inbox_id="555", user_id="u")

    with pytest.raises(TypeError):
        factory.create_table_cache(inbox_id="555")  # type: ignore[call-arg]


@pytest.mark.parametrize("cache_type", ["memory", "json"])
def test_other_cache_families_still_require_inbox_identity(cache_type: str) -> None:
    factory_class = create_cache_factory(cache_type)

    with pytest.raises(ValueError):
        factory_class(inbox_id="", user_id="u")
    with pytest.raises(ValueError):
        factory_class(inbox_id="555", user_id="")

    factory = factory_class(inbox_id="555", user_id="u")
    assert factory.create_user_cache().inbox == "555"
    assert factory.create_state_cache().inbox == "555"
    assert factory.create_ai_state_cache().inbox == "555"


def test_inbox_namespaces_keep_platforms_apart_in_one_table_backend() -> None:
    whatsapp = MemoryTable(InboxRef.whatsapp("123").cache_namespace)
    telegram = MemoryTable(
        InboxRef(platform=PlatformType.TELEGRAM, inbox_id="123").cache_namespace
    )

    assert whatsapp._key("t", "p") == "123:df:t:pkid:p"
    assert telegram._key("t", "p") == "telegram__123:df:t:pkid:p"
    assert whatsapp._key("t", "p") != telegram._key("t", "p")


# ── conformance: the same contract on every backend ─────────────────────────


async def _open_redis_pools() -> bool:
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
async def system_table(
    request: pytest.FixtureRequest, tmp_path: Path
) -> AsyncIterator[ITableCache]:
    match request.param:
        case "memory":
            table = create_system_table_cache("memory")
            await table.delete_table("scope-conformance")
            yield table
        case "json":
            file_manager._cache_root = tmp_path / "cache"
            file_manager.ensure_cache_directories()
            yield create_system_table_cache("json")
        case _:
            if not await _open_redis_pools():
                pytest.skip(f"No Redis reachable at {REDIS_URL}")
            table = create_system_table_cache("redis")
            try:
                yield table
            finally:
                await table.delete_table("scope-conformance")
                await RedisClient.close()


async def test_system_scope_table_round_trips_rows_on_every_backend(
    system_table: ITableCache,
) -> None:
    assert await system_table.upsert("scope-conformance", "row-1", {"v": 1}, ttl=60)
    assert await system_table.get("scope-conformance", "row-1") == {"v": 1}
    assert await system_table.exists("scope-conformance", "row-1")
    assert 0 < await system_table.get_ttl("scope-conformance", "row-1") <= 60
    assert await system_table.renew_ttl("scope-conformance", "row-1", 120)
    assert 60 < await system_table.get_ttl("scope-conformance", "row-1") <= 120
    assert await system_table.delete("scope-conformance", "row-1") == 1
    assert await system_table.get("scope-conformance", "row-1") is None


async def test_system_scope_does_not_bleed_into_an_inbox_scope(
    system_table: ITableCache,
) -> None:
    await system_table.upsert("scope-conformance", "shared", {"owner": "system"})

    inbox_table = (
        MemoryTable("123")
        if isinstance(system_table, MemoryTable)
        else JSONTable("123")
        if isinstance(system_table, JSONTable)
        else RedisTable("123")
    )
    assert await inbox_table.get("scope-conformance", "shared") is None


# ── migration guidance for the renamed keyword (PRD 5) ──────────────────────


@pytest.mark.parametrize("table_class", TABLE_CLASSES)
@pytest.mark.parametrize("stale_keyword", ["inbox_id", "inbox"])
def test_stale_keyword_error_carries_migration_guidance(
    table_class: type, stale_keyword: str
) -> None:
    """A stale keyword must say what replaced it, not just 'unexpected'."""
    with pytest.raises(TypeError) as exc_info:
        table_class(**{stale_keyword: "123"})

    message = str(exc_info.value)
    assert f"no longer accepts {stale_keyword}=" in message
    assert "context_id" in message
    assert "no cache migration is needed" in message
    assert "docs/migration/v0.27.0-multi-inbox.md" in message


@pytest.mark.parametrize("cache_type", ["memory", "json"])
def test_factory_stale_keyword_error_carries_migration_guidance(
    cache_type: str,
) -> None:
    factory = create_cache_factory(cache_type)(inbox_id="555", user_id="u")

    with pytest.raises(TypeError) as exc_info:
        factory.create_table_cache(inbox_id="555")  # type: ignore[call-arg]

    assert "context_id" in str(exc_info.value)
    assert "docs/migration/v0.27.0-multi-inbox.md" in str(exc_info.value)


def test_other_cache_families_still_accept_inbox_id_unchanged() -> None:
    """The rename is Table-Cache-only; a global rename would break these."""
    factory = create_cache_factory("memory")(inbox_id="555", user_id="u")

    assert factory.create_user_cache(inbox_id="other").inbox == "other"
    assert factory.create_state_cache(inbox_id="other", user_id="u2").inbox == "other"
    assert (
        factory.create_ai_state_cache(inbox_id="other", user_id="u2").inbox == "other"
    )
