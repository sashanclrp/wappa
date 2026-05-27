"""Tests for BackgroundWorkTracker lifecycle and drain behavior."""

import asyncio

import pytest

from wappa.core.lifecycle import BackgroundWorkTracker


class TestBackgroundWorkTracker:
    def test_initial_state(self):
        tracker = BackgroundWorkTracker()
        assert tracker.active_count == 0
        assert not tracker.is_draining

    @pytest.mark.asyncio
    async def test_track_and_completion(self):
        tracker = BackgroundWorkTracker()
        completed = False

        async def work():
            nonlocal completed
            completed = True

        task = tracker.track(work(), name="test-task")
        assert tracker.active_count == 1
        await task
        await asyncio.sleep(0)  # let done callback fire
        assert completed
        assert tracker.active_count == 0

    @pytest.mark.asyncio
    async def test_track_after_drain_raises(self):
        tracker = BackgroundWorkTracker()
        tracker.begin_drain()

        coro = asyncio.sleep(0)
        with pytest.raises(RuntimeError, match="draining"):
            tracker.track(coro, name="rejected")
        coro.close()

    @pytest.mark.asyncio
    async def test_drain_waits_for_completion(self):
        tracker = BackgroundWorkTracker()
        results = []

        async def slow_work(label):
            await asyncio.sleep(0.05)
            results.append(label)

        tracker.track(slow_work("a"), name="a")
        tracker.track(slow_work("b"), name="b")

        result = await tracker.drain(timeout=5.0)
        assert result.completed == 2
        assert result.cancelled == 0
        assert not result.timed_out
        assert set(results) == {"a", "b"}

    @pytest.mark.asyncio
    async def test_drain_timeout_cancels_stragglers(self):
        tracker = BackgroundWorkTracker()

        async def fast():
            await asyncio.sleep(0.01)

        async def stuck():
            await asyncio.sleep(100)

        tracker.track(fast(), name="fast")
        tracker.track(stuck(), name="stuck")

        result = await tracker.drain(timeout=0.1)
        assert result.completed >= 1
        assert result.cancelled >= 1
        assert result.timed_out

    @pytest.mark.asyncio
    async def test_drain_empty(self):
        tracker = BackgroundWorkTracker()
        result = await tracker.drain(timeout=1.0)
        assert result.completed == 0
        assert result.cancelled == 0
        assert not result.timed_out
        assert tracker.is_draining

    @pytest.mark.asyncio
    async def test_begin_drain_is_idempotent(self):
        tracker = BackgroundWorkTracker()
        tracker.begin_drain()
        tracker.begin_drain()
        assert tracker.is_draining
