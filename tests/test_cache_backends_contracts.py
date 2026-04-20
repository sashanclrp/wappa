from pathlib import Path

import pytest

from wappa.persistence.cache_factory import create_cache_factory
from wappa.persistence.json.handlers.ai_state import JSONAIState
from wappa.persistence.json.handlers.state_handler import JSONStateHandler
from wappa.persistence.json.handlers.utils.file_manager import file_manager
from wappa.persistence.memory.handlers.ai_state import MemoryAIState


def test_create_cache_factory_normalizes_cache_type() -> None:
    factory_class = create_cache_factory("  MEMORY  ")
    assert factory_class.__name__ == "MemoryCacheFactory"


@pytest.mark.asyncio
async def test_memory_ai_state_namespace_is_supported() -> None:
    handler = MemoryAIState(tenant="tenant-memory", user_id="user-1")

    assert await handler.upsert("assistant", {"count": 1}, ttl=60) is True
    assert await handler.get("assistant") == {"count": 1}


@pytest.mark.asyncio
async def test_json_state_and_ai_state_ttl_calls_accept_key_argument(
    tmp_path: Path,
) -> None:
    file_manager._cache_root = tmp_path / "cache"
    file_manager.ensure_cache_directories()

    state_handler = JSONStateHandler(tenant="tenant-json", user_id="user-1")
    ai_handler = JSONAIState(tenant="tenant-json", user_id="user-1")

    assert await state_handler.upsert("flow", {"step": 1}, ttl=60) is True
    assert await ai_handler.upsert("assistant", {"count": 2}, ttl=60) is True

    state_ttl = await state_handler.get_ttl("flow")
    ai_ttl = await ai_handler.get_ttl("assistant")

    assert 0 <= state_ttl <= 60
    assert 0 <= ai_ttl <= 60
