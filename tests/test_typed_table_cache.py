from __future__ import annotations

import pytest
from pydantic import BaseModel, ValidationError

from wappa.persistence import TypedTableCache
from wappa.persistence.memory import MemoryCacheFactory


class ScoreRow(BaseModel):
    user_id: str
    score: int


@pytest.mark.asyncio
async def test_typed_table_cache_get_upsert_exists_and_delete() -> None:
    table = MemoryCacheFactory(
        inbox_id="typed-cache-1", user_id="user"
    ).create_table_cache()
    scores = TypedTableCache(table, "scores", ScoreRow)

    assert await scores.get("user-1") is None

    assert await scores.upsert("user-1", ScoreRow(user_id="user-1", score=10))
    assert await scores.exists("user-1")
    assert await scores.get("user-1") == ScoreRow(user_id="user-1", score=10)

    assert await scores.delete("user-1") == 1
    assert not await scores.exists("user-1")


@pytest.mark.asyncio
async def test_typed_table_cache_validates_dict_input_through_pydantic() -> None:
    table = MemoryCacheFactory(
        inbox_id="typed-cache-2", user_id="user"
    ).create_table_cache()
    scores = TypedTableCache(table, "scores", ScoreRow)

    assert await scores.upsert("user-1", {"user_id": "user-1", "score": "7"})
    assert await scores.get("user-1") == ScoreRow(user_id="user-1", score=7)

    with pytest.raises(ValidationError):
        await scores.upsert("bad", {"user_id": "bad", "score": "not-int"})


@pytest.mark.asyncio
async def test_typed_table_cache_forwards_default_ttl_to_writes() -> None:
    table = MemoryCacheFactory(
        inbox_id="typed-cache-3", user_id="user"
    ).create_table_cache()
    scores = TypedTableCache(table, "scores", ScoreRow, default_ttl=60)

    assert await scores.upsert("user-1", {"user_id": "user-1", "score": 1})
    ttl = await table.get_ttl("scores", "user-1")

    assert 0 < ttl <= 60


@pytest.mark.asyncio
async def test_typed_table_cache_update_field_uses_bound_table() -> None:
    table = MemoryCacheFactory(
        inbox_id="typed-cache-4", user_id="user"
    ).create_table_cache()
    scores = TypedTableCache(table, "scores", ScoreRow)

    assert await scores.upsert("user-1", {"user_id": "user-1", "score": 1})
    assert await scores.update_field("user-1", "score", 2)
    assert await scores.get("user-1") == ScoreRow(user_id="user-1", score=2)


@pytest.mark.asyncio
async def test_typed_table_cache_rejects_empty_table_name_and_pkid() -> None:
    table = MemoryCacheFactory(
        inbox_id="typed-cache-5", user_id="user"
    ).create_table_cache()

    with pytest.raises(ValueError, match="table_name"):
        TypedTableCache(table, "", ScoreRow)

    scores = TypedTableCache(table, "scores", ScoreRow)
    with pytest.raises(ValueError, match="pkid"):
        await scores.get("")
