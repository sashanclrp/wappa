"""Tests for Wappa shutdown lifecycle ordering and drain behavior."""

import asyncio
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI

from wappa.core.factory.wappa_builder import WappaBuilder


class TestShutdownPriorityOrdering:
    @pytest.mark.asyncio
    async def test_hooks_execute_highest_priority_first(self):
        """Shutdown hooks execute in descending priority order."""
        builder = WappaBuilder()
        execution_order = []

        async def hook_a(app):
            execution_order.append("a-priority-10")

        async def hook_b(app):
            execution_order.append("b-priority-50")

        async def hook_c(app):
            execution_order.append("c-priority-90")

        builder.add_shutdown_hook(hook_a, priority=10)
        builder.add_shutdown_hook(hook_b, priority=50)
        builder.add_shutdown_hook(hook_c, priority=90)

        app = MagicMock(spec=FastAPI)
        await builder._execute_all_shutdown_hooks(app)

        assert execution_order == [
            "c-priority-90",
            "b-priority-50",
            "a-priority-10",
        ]

    @pytest.mark.asyncio
    async def test_drain_before_close(self):
        """Producer hooks (high priority) complete before resource hooks (low priority)."""
        builder = WappaBuilder()
        events = []

        async def producer_shutdown(app):
            events.append("producer-stop")
            await asyncio.sleep(0.01)
            events.append("producer-drained")

        async def resource_close(app):
            events.append("resource-closed")

        builder.add_shutdown_hook(producer_shutdown, priority=80)
        builder.add_shutdown_hook(resource_close, priority=10)

        app = MagicMock(spec=FastAPI)
        await builder._execute_all_shutdown_hooks(app)

        assert events.index("producer-drained") < events.index("resource-closed")

    @pytest.mark.asyncio
    async def test_http_session_closes_after_expiry_and_cron(self):
        """Core HTTP close (priority 10) runs after expiry (80) and cron (85)."""
        builder = WappaBuilder()
        events = []

        async def cron_stop(app):
            events.append("cron-stopped")

        async def expiry_stop(app):
            events.append("expiry-stopped")

        async def http_close(app):
            events.append("http-closed")

        builder.add_shutdown_hook(cron_stop, priority=85)
        builder.add_shutdown_hook(expiry_stop, priority=80)
        builder.add_shutdown_hook(http_close, priority=10)

        app = MagicMock(spec=FastAPI)
        await builder._execute_all_shutdown_hooks(app)

        assert events == ["cron-stopped", "expiry-stopped", "http-closed"]


class TestExpiryListenerShutdown:
    @pytest.mark.asyncio
    async def test_listener_is_cancelled_and_removed_from_app_state(self):
        """SchedulingPlugin shutdown stops the listener and cleans app.state."""
        from wappa.core.plugins.scheduling_plugin import SchedulingPlugin

        plugin = SchedulingPlugin(redis_expiry=True)
        task = asyncio.create_task(asyncio.sleep(60))
        plugin._listener_task = task

        mock_app = MagicMock(spec=FastAPI)
        mock_app.state = MagicMock()
        mock_app.state.expiry_listener_task = task

        await plugin._stop_expiry_listener(mock_app)

        assert task.cancelled()
        assert not hasattr(mock_app.state, "expiry_listener_task")


class TestDrainCompletesBeforeSessionClose:
    @pytest.mark.asyncio
    async def test_tracked_work_finishes_before_close(self):
        """Background work completes during drain before HTTP session closes."""
        from wappa.core.lifecycle import BackgroundWorkTracker, SessionLifecycle

        tracker = BackgroundWorkTracker()
        client = SessionLifecycle._default_client_factory()
        lifecycle = SessionLifecycle(client)
        work_completed = False

        async def background_send():
            nonlocal work_completed
            await asyncio.sleep(0.05)
            # Session should still be open at this point
            assert not client.is_closed
            work_completed = True

        tracker.track(background_send(), name="test-send")

        # Phase 1: mark draining
        lifecycle.begin_drain()
        tracker.begin_drain()

        # Phase 2: drain
        result = await tracker.drain(timeout=5.0)
        assert result.completed == 1
        assert work_completed

        # Phase 3: close session
        await lifecycle.close()
        assert client.is_closed
