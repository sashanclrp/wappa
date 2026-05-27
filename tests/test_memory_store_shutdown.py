"""Regression test: WappaCorePlugin._core_shutdown() stops memory store cleanup."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from wappa.core.plugins.wappa_core_plugin import WappaCorePlugin
from wappa.core.types import CacheType
from wappa.persistence.memory.handlers.utils.memory_store import (
    MemoryStore,
    get_memory_store,
)


class TestMemoryStoreShutdownCleanup:
    def test_stop_cleanup_cancels_task(self):
        store = MemoryStore()
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(self._start_and_stop(store))
        finally:
            loop.close()

    async def _start_and_stop(self, store: MemoryStore):
        store.start_cleanup_task()
        assert store._cleanup_task is not None
        assert not store._cleanup_task.done()

        store.stop_cleanup_task()
        await asyncio.sleep(0.05)
        assert store._cleanup_task.cancelled() or store._cleanup_task.done()

    @pytest.mark.asyncio
    async def test_core_shutdown_stops_memory_store(self):
        plugin = WappaCorePlugin(cache_type=CacheType.MEMORY)

        store = get_memory_store()
        store.start_cleanup_task()
        assert store._cleanup_task is not None
        assert not store._cleanup_task.done()

        app = AsyncMock()
        app.state = type("State", (), {"wappa_cache_type": "memory"})()

        await plugin._core_shutdown(app)

        await asyncio.sleep(0.05)
        assert store._cleanup_task.cancelled() or store._cleanup_task.done()

    @pytest.mark.asyncio
    async def test_core_shutdown_skips_when_not_memory_cache(self):
        plugin = WappaCorePlugin(cache_type=CacheType.REDIS)

        with patch(
            "wappa.persistence.memory.handlers.utils.memory_store.MemoryStore.stop_cleanup_task"
        ) as mock_stop:
            app = AsyncMock()
            app.state = type("State", (), {})()

            await plugin._core_shutdown(app)
            mock_stop.assert_not_called()
