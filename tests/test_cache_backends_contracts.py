from pathlib import Path

import pytest

from wappa.persistence.cache_factory import create_cache_factory
from wappa.persistence.json.handlers.ai_state import JSONAIState
from wappa.persistence.json.handlers.state_handler import JSONStateHandler
from wappa.persistence.json.handlers.utils.file_manager import file_manager
from wappa.persistence.memory.handlers.ai_state import MemoryAIState
from wappa.persistence.memory.handlers.state_handler import MemoryStateHandler


def test_create_cache_factory_normalizes_cache_type() -> None:
    factory_class = create_cache_factory("  MEMORY  ")
    assert factory_class.__name__ == "MemoryCacheFactory"


@pytest.mark.asyncio
async def test_memory_ai_state_namespace_is_supported() -> None:
    handler = MemoryAIState(inbox="inbox-memory", user_id="user-1")

    assert await handler.upsert("assistant", {"count": 1}, ttl=60) is True
    assert await handler.get("assistant") == {"count": 1}


@pytest.mark.asyncio
async def test_json_state_and_ai_state_ttl_calls_accept_key_argument(
    tmp_path: Path,
) -> None:
    file_manager._cache_root = tmp_path / "cache"
    file_manager.ensure_cache_directories()

    state_handler = JSONStateHandler(inbox="inbox-json", user_id="user-1")
    ai_handler = JSONAIState(inbox="inbox-json", user_id="user-1")

    assert await state_handler.upsert("flow", {"step": 1}, ttl=60) is True
    assert await ai_handler.upsert("assistant", {"count": 2}, ttl=60) is True

    state_ttl = await state_handler.get_ttl("flow")
    ai_ttl = await ai_handler.get_ttl("assistant")

    assert 0 <= state_ttl <= 60
    assert 0 <= ai_ttl <= 60


@pytest.mark.asyncio
async def test_memory_delete_all_for_user_removes_all_agents() -> None:
    handler = MemoryAIState(inbox="t", user_id="user-target")
    other = MemoryAIState(inbox="t", user_id="user-other")

    await handler.upsert("agent-a", {"x": 1})
    await handler.upsert("agent-b", {"x": 2})
    await handler.upsert("agent-c", {"x": 3})
    await other.upsert("agent-a", {"x": 99})

    deleted = await handler.delete_all_for_user()

    assert deleted == 3
    assert await handler.get("agent-a") is None
    assert await handler.get("agent-b") is None
    assert await handler.get("agent-c") is None
    assert await other.get("agent-a") == {"x": 99}


@pytest.mark.asyncio
async def test_memory_delete_all_for_user_returns_zero_when_empty() -> None:
    handler = MemoryAIState(inbox="t", user_id="user-empty")
    assert await handler.delete_all_for_user() == 0


@pytest.mark.asyncio
async def test_json_delete_all_for_user_removes_all_agents(tmp_path: Path) -> None:
    file_manager._cache_root = tmp_path / "cache"
    file_manager.ensure_cache_directories()

    handler = JSONAIState(inbox="t", user_id="user-target")
    other = JSONAIState(inbox="t", user_id="user-other")

    await handler.upsert("agent-a", {"x": 1})
    await handler.upsert("agent-b", {"x": 2})
    await other.upsert("agent-a", {"x": 99})

    deleted = await handler.delete_all_for_user()

    assert deleted == 2
    assert await handler.get("agent-a") is None
    assert await handler.get("agent-b") is None
    assert await other.get("agent-a") == {"x": 99}


@pytest.mark.asyncio
async def test_json_delete_all_for_user_returns_zero_when_empty(
    tmp_path: Path,
) -> None:
    file_manager._cache_root = tmp_path / "cache"
    file_manager.ensure_cache_directories()

    handler = JSONAIState(inbox="t", user_id="user-empty")
    assert await handler.delete_all_for_user() == 0


# ── IStateCache.delete_all_for_user ──────────────────────────────────


@pytest.mark.asyncio
async def test_memory_state_delete_all_for_user_removes_all_handlers() -> None:
    handler = MemoryStateHandler(inbox="t", user_id="user-target")
    other = MemoryStateHandler(inbox="t", user_id="user-other")

    await handler.upsert("flow-a", {"step": 1})
    await handler.upsert("flow-b", {"step": 2})
    await handler.upsert("flow-c", {"step": 3})
    await other.upsert("flow-a", {"step": 99})

    deleted = await handler.delete_all_for_user()

    assert deleted == 3
    assert await handler.get("flow-a") is None
    assert await handler.get("flow-b") is None
    assert await handler.get("flow-c") is None
    assert await other.get("flow-a") == {"step": 99}


@pytest.mark.asyncio
async def test_memory_state_delete_all_for_user_returns_zero_when_empty() -> None:
    handler = MemoryStateHandler(inbox="t", user_id="user-empty-state")
    assert await handler.delete_all_for_user() == 0


@pytest.mark.asyncio
async def test_json_state_delete_all_for_user_removes_all_handlers(
    tmp_path: Path,
) -> None:
    file_manager._cache_root = tmp_path / "cache"
    file_manager.ensure_cache_directories()

    handler = JSONStateHandler(inbox="t", user_id="user-target")
    other = JSONStateHandler(inbox="t", user_id="user-other")

    await handler.upsert("flow-a", {"step": 1})
    await handler.upsert("flow-b", {"step": 2})
    await other.upsert("flow-a", {"step": 99})

    deleted = await handler.delete_all_for_user()

    assert deleted == 2
    assert await handler.get("flow-a") is None
    assert await handler.get("flow-b") is None
    assert await other.get("flow-a") == {"step": 99}


@pytest.mark.asyncio
async def test_json_state_delete_all_for_user_returns_zero_when_empty(
    tmp_path: Path,
) -> None:
    file_manager._cache_root = tmp_path / "cache"
    file_manager.ensure_cache_directories()

    handler = JSONStateHandler(inbox="t", user_id="user-empty-state")
    assert await handler.delete_all_for_user() == 0
