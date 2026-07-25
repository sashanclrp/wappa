"""Tests for cache space composition and versioned table cache invalidation."""

from __future__ import annotations

import pytest
from pydantic import BaseModel, ValidationError

from wappa.persistence import TypedTableCache, VersionedTableCache, build_table_name
from wappa.persistence.memory import MemoryCacheFactory


class AgentRow(BaseModel):
    agent_id: str
    name: str


def _table(inbox_id: str):
    return MemoryCacheFactory(inbox_id=inbox_id, user_id="user").create_table_cache()


# ---------------------------------------------------------------------------
# Cache space
# ---------------------------------------------------------------------------


def test_cache_space_prefixes_the_table_name() -> None:
    assert build_table_name("invoices") == "invoices"
    assert build_table_name("invoices", "billing") == "billing:invoices"


@pytest.mark.parametrize(
    ("table_name", "cache_space"),
    [
        ("", None),
        ("  ", None),
        ("invoices", ""),
        ("a:b", None),
        ("invoices", "bill:ing"),
    ],
)
def test_blank_or_reserved_segments_are_rejected(
    table_name: str, cache_space: str | None
) -> None:
    with pytest.raises(ValueError):
        build_table_name(table_name, cache_space)


@pytest.mark.asyncio
async def test_cache_spaces_isolate_rows_sharing_a_table_name() -> None:
    table = _table("space-isolation")
    billing = TypedTableCache(table, "records", AgentRow, cache_space="billing")
    crm = TypedTableCache(table, "records", AgentRow, cache_space="crm")

    await billing.upsert("a-1", AgentRow(agent_id="a-1", name="billing"))
    await crm.upsert("a-1", AgentRow(agent_id="a-1", name="crm"))

    assert (await billing.get("a-1")).name == "billing"
    assert (await crm.get("a-1")).name == "crm"


@pytest.mark.asyncio
async def test_omitting_the_cache_space_keeps_the_plain_table_name() -> None:
    table = _table("space-default")
    scores = TypedTableCache(table, "records", AgentRow)

    await scores.upsert("a-1", AgentRow(agent_id="a-1", name="plain"))

    assert await table.exists("records", "a-1")


@pytest.mark.asyncio
async def test_typed_table_cache_renew_ttl_extends_an_existing_row() -> None:
    table = _table("renew-ttl")
    scores = TypedTableCache(table, "records", AgentRow, default_ttl=60)

    await scores.upsert("a-1", AgentRow(agent_id="a-1", name="x"), ttl=5)
    assert await scores.renew_ttl("a-1")

    assert await table.get_ttl("records", "a-1") > 5


@pytest.mark.asyncio
async def test_renew_ttl_requires_a_ttl() -> None:
    scores = TypedTableCache(_table("renew-ttl-missing"), "records", AgentRow)
    with pytest.raises(ValueError, match="ttl"):
        await scores.renew_ttl("a-1")


# ---------------------------------------------------------------------------
# Versioned table cache
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rows_round_trip_within_a_generation() -> None:
    cache = VersionedTableCache(_table("v-basic"), "agents", AgentRow, default_ttl=60)

    assert await cache.current_version() == 1
    assert await cache.get("a-1") is None

    assert await cache.upsert("a-1", AgentRow(agent_id="a-1", name="Ada"))
    assert await cache.exists("a-1")
    assert await cache.get("a-1") == AgentRow(agent_id="a-1", name="Ada")

    assert await cache.delete("a-1") == 1
    assert not await cache.exists("a-1")


@pytest.mark.asyncio
async def test_bump_version_invalidates_every_row_without_enumerating_keys() -> None:
    cache = VersionedTableCache(_table("v-bump"), "agents", AgentRow, default_ttl=60)

    await cache.upsert("a-1", AgentRow(agent_id="a-1", name="Ada"))
    await cache.upsert("a-2", AgentRow(agent_id="a-2", name="Grace"))

    assert await cache.bump_version() == 2

    assert await cache.get("a-1") is None
    assert await cache.get("a-2") is None
    assert not await cache.exists("a-1")


@pytest.mark.asyncio
async def test_writes_after_a_bump_land_in_the_new_generation() -> None:
    cache = VersionedTableCache(_table("v-rewrite"), "agents", AgentRow, default_ttl=60)

    await cache.upsert("a-1", AgentRow(agent_id="a-1", name="stale"))
    await cache.bump_version()
    await cache.upsert("a-1", AgentRow(agent_id="a-1", name="fresh"))

    assert (await cache.get("a-1")).name == "fresh"
    assert await cache.current_table_name() == "agents@v2"


@pytest.mark.asyncio
async def test_a_bump_is_visible_to_another_instance_on_the_same_backend() -> None:
    table = _table("v-shared")
    writer = VersionedTableCache(table, "agents", AgentRow, default_ttl=60)
    reader = VersionedTableCache(table, "agents", AgentRow, default_ttl=60)

    await writer.upsert("a-1", AgentRow(agent_id="a-1", name="Ada"))
    assert await reader.get("a-1") == AgentRow(agent_id="a-1", name="Ada")

    await writer.bump_version()

    assert await reader.current_version() == 2
    assert await reader.get("a-1") is None


@pytest.mark.asyncio
async def test_bumping_one_table_leaves_its_neighbours_alone() -> None:
    table = _table("v-neighbours")
    agents = VersionedTableCache(table, "agents", AgentRow, default_ttl=60)
    contacts = VersionedTableCache(table, "contacts", AgentRow, default_ttl=60)

    await agents.upsert("a-1", AgentRow(agent_id="a-1", name="Ada"))
    await contacts.upsert("c-1", AgentRow(agent_id="c-1", name="Grace"))

    await agents.bump_version()

    assert await agents.get("a-1") is None
    assert await contacts.get("c-1") == AgentRow(agent_id="c-1", name="Grace")
    assert await contacts.current_version() == 1


@pytest.mark.asyncio
async def test_cache_space_scopes_versions_and_rows() -> None:
    table = _table("v-space")
    billing = VersionedTableCache(
        table, "agents", AgentRow, default_ttl=60, cache_space="billing"
    )
    crm = VersionedTableCache(
        table, "agents", AgentRow, default_ttl=60, cache_space="crm"
    )

    await billing.upsert("a-1", AgentRow(agent_id="a-1", name="billing"))
    await crm.upsert("a-1", AgentRow(agent_id="a-1", name="crm"))

    await billing.bump_version()

    assert await billing.get("a-1") is None
    assert (await crm.get("a-1")).name == "crm"
    assert await crm.current_version() == 1
    assert await crm.current_table_name() == "crm:agents@v1"


@pytest.mark.asyncio
async def test_default_ttl_is_applied_to_writes() -> None:
    table = _table("v-ttl")
    cache = VersionedTableCache(table, "agents", AgentRow, default_ttl=45)

    await cache.upsert("a-1", AgentRow(agent_id="a-1", name="Ada"))

    assert 0 < await table.get_ttl("agents@v1", "a-1") <= 45


@pytest.mark.asyncio
async def test_renew_ttl_extends_a_row_in_the_current_generation() -> None:
    table = _table("v-renew")
    cache = VersionedTableCache(table, "agents", AgentRow, default_ttl=120)

    await cache.upsert("a-1", AgentRow(agent_id="a-1", name="Ada"), ttl=5)
    assert await cache.renew_ttl("a-1")

    assert await table.get_ttl("agents@v1", "a-1") > 5


@pytest.mark.asyncio
async def test_update_field_writes_through_the_model_table() -> None:
    cache = VersionedTableCache(_table("v-field"), "agents", AgentRow, default_ttl=60)

    await cache.upsert("a-1", AgentRow(agent_id="a-1", name="Ada"))
    assert await cache.update_field("a-1", "name", "Ada L.")

    assert (await cache.get("a-1")).name == "Ada L."


@pytest.mark.asyncio
async def test_invalid_rows_are_rejected_by_the_row_model() -> None:
    cache = VersionedTableCache(_table("v-model"), "agents", AgentRow, default_ttl=60)

    with pytest.raises(ValidationError):
        await cache.upsert("a-1", {"agent_id": "a-1"})


@pytest.mark.parametrize("default_ttl", [0, -5])
def test_versioned_cache_requires_a_positive_ttl(default_ttl: int) -> None:
    with pytest.raises(ValueError, match="default_ttl"):
        VersionedTableCache(
            _table("v-ttl-invalid"), "agents", AgentRow, default_ttl=default_ttl
        )


@pytest.mark.asyncio
async def test_blank_pkid_is_rejected() -> None:
    cache = VersionedTableCache(_table("v-pkid"), "agents", AgentRow, default_ttl=60)
    with pytest.raises(ValueError, match="pkid"):
        await cache.get("")


@pytest.mark.asyncio
async def test_version_counter_outlives_the_rows_it_invalidates() -> None:
    # If the counter expired while orphaned rows were still live, the table
    # would fall back to v1 and resurrect them.
    table = _table("v-counter-ttl")
    cache = VersionedTableCache(table, "agents", AgentRow, default_ttl=60)

    await cache.upsert("a-1", AgentRow(agent_id="a-1", name="Ada"))
    await cache.bump_version()

    counter_ttl = await table.get_ttl("_wappa_table_versions", "agents")
    assert counter_ttl > 60
