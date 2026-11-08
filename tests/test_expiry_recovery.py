"""Recovery admissions use the normal scheduled lane and acknowledge successes only."""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from wappa.core.expiry.dispatcher import ExpiryDispatcher
from wappa.core.expiry.recovery import ExpiryRecovery
from wappa.core.lifecycle import BackgroundWorkTracker
from wappa.domain.inbox import InboxRef
from wappa.persistence.redis.expiry_index import DueTrigger

REF = InboxRef.instagram("account")
KEY = f"{REF.cache_namespace}:EXPTRIGGER:reminder:opaque-message"
DUE = datetime.now(UTC) - timedelta(seconds=10)


class Index:
    """Controlled storage seam: tests exercise runtime admission, not Lua emulation."""

    def __init__(self, count=1):
        self.keys = [KEY + str(i) for i in range(count)]
        self.claims = {
            key: DueTrigger(key, "original-record", "generation", DUE)
            for key in self.keys
        }
        self.leased = set()
        self.acknowledged = []
        self.limits = []

    async def due(self, limit):
        self.limits.append(limit)
        return [
            key for key in self.keys if key in self.claims and key not in self.leased
        ][:limit]

    async def claim(self, key):
        if key in self.leased:
            return None
        self.leased.add(key)
        return self.claims.get(key)

    async def acknowledge(self, trigger):
        self.acknowledged.append(trigger)
        if self.claims.get(trigger.key) == trigger:
            del self.claims[trigger.key]
            return True
        return False


def recovery(index, handler, *, subjects=None, batch_size=100):
    tracker = BackgroundWorkTracker()
    dispatcher = ExpiryDispatcher(run_event=handler, tracker=tracker, subjects=subjects)
    return ExpiryRecovery(
        index, dispatcher, batch_size=batch_size, interval=0.001
    ), tracker


async def settle(runtime):
    await asyncio.gather(*tuple(runtime._inflight.values()), return_exceptions=True)


async def test_startup_recovers_due_work_with_its_original_scope_time_and_generation():
    index = Index()
    handler = AsyncMock()
    subjects = AsyncMock(return_value="known-user")
    runtime, _ = recovery(index, handler, subjects=subjects)
    await runtime.tick()
    await settle(runtime)
    event = handler.call_args.args[0]
    assert event.inbox_ref == REF and event.user_id == "known-user"
    assert event.source == "redis_expiry" and event.action == "reminder"
    assert event.identifier == "opaque-message0"
    assert event.metadata == {"expired_key": index.keys[0], "recovered": True}
    assert event.scheduled_for == DUE and event.execution_id == "generation"
    assert len(index.acknowledged) == 1
    assert index.claims == {}


async def test_pubsub_and_recovery_share_admission_and_success_acknowledgment():
    index = Index()
    handler = AsyncMock()
    live, _ = recovery(index, handler)
    other_process, _ = recovery(index, handler)
    await live.deliver(index.keys[0], recovered=False)
    await other_process.tick()
    await settle(live)
    assert handler.await_count == 1
    assert handler.call_args.args[0].metadata["recovered"] is False
    assert len(index.acknowledged) == 1


@pytest.mark.parametrize("failure", ["handler", "subject", "cancellation"])
async def test_failed_or_cancelled_delivery_remains_recoverable_after_a_restart(
    failure,
):
    index = Index()
    handler = AsyncMock(
        side_effect=RuntimeError("handler failed") if failure == "handler" else None
    )
    subjects = (
        AsyncMock(side_effect=ValueError("unrecognized action"))
        if failure == "subject"
        else None
    )
    if failure == "cancellation":
        handler.side_effect = asyncio.CancelledError()
    runtime, _ = recovery(index, handler, subjects=subjects)
    await runtime.tick()
    await settle(runtime)
    assert index.acknowledged == [] and index.claims
    # A crashed process cannot release its claim; it becomes eligible after lease expiry.
    index.leased.clear()
    recovered_handler = AsyncMock()
    restarted, _ = recovery(index, recovered_handler)
    await restarted.tick()
    await settle(restarted)
    assert recovered_handler.call_args.args[0].execution_id == "generation"
    assert recovered_handler.call_args.args[0].metadata["recovered"] is True
    assert index.claims == {}


async def test_completion_of_an_old_occurrence_never_acknowledges_a_replacement():
    index = Index()

    async def handler(event):
        index.claims[index.keys[0]] = DueTrigger(
            index.keys[0], "renewed-record", "new-generation", DUE
        )

    runtime, _ = recovery(index, handler)
    await runtime.tick()
    await settle(runtime)
    assert index.acknowledged[0].record == "original-record"
    assert index.claims[index.keys[0]].generation == "new-generation"


async def test_tick_has_a_bounded_query_and_inflight_budget_and_eventually_drains():
    index = Index(count=5)
    entered = asyncio.Event()
    release = asyncio.Event()

    async def handler(event):
        entered.set()
        await release.wait()

    runtime, _ = recovery(index, handler, batch_size=2)
    await runtime.tick()
    await asyncio.wait_for(entered.wait(), 1)
    await runtime.tick()
    assert index.limits == [2]
    assert len(runtime._inflight) == 2
    release.set()
    await settle(runtime)
    await runtime.tick()
    await settle(runtime)
    await runtime.tick()
    await settle(runtime)
    assert len(index.acknowledged) == 5
    assert all(limit <= 2 for limit in index.limits)


async def test_runtime_draining_does_not_acknowledge_unsubmitted_work():
    index = Index()
    runtime, tracker = recovery(index, AsyncMock())
    tracker.begin_drain()
    with pytest.raises(RuntimeError, match="draining"):
        await runtime.tick()
    assert index.claims and index.acknowledged == []


async def test_storage_failure_is_retried_by_the_periodic_loop():
    index = Index()
    due = index.due
    failed = False
    acknowledged = asyncio.Event()

    async def fail_once(limit):
        nonlocal failed
        if not failed:
            failed = True
            raise ConnectionError("temporarily unavailable")
        return await due(limit)

    index.due = fail_once
    original_ack = index.acknowledge

    async def ack(trigger):
        result = await original_ack(trigger)
        acknowledged.set()
        return result

    index.acknowledge = ack
    runtime, _ = recovery(index, AsyncMock())
    task = asyncio.create_task(runtime.run())
    try:
        await asyncio.wait_for(acknowledged.wait(), 1)
        assert failed and not index.claims
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


async def test_unindexed_pre_upgrade_notifications_keep_the_live_path_only():
    index = Index()
    index.claims[index.keys[0]] = DueTrigger(index.keys[0])
    handler = AsyncMock()
    runtime, _ = recovery(index, handler)
    await runtime.tick()
    assert handler.await_count == 0  # cannot invent recovery history
    index.leased.clear()
    await runtime.deliver(index.keys[0], recovered=False)
    await settle(runtime)
    assert handler.await_count == 1
    event = handler.call_args.args[0]
    assert event.scheduled_for is None and event.execution_id is None


@pytest.mark.parametrize("max_attempts", [None, 0, 1])
async def test_recovery_starts_even_when_the_pubsub_connection_is_unavailable(
    monkeypatch,
    max_attempts,
):
    from wappa.core.expiry import listener

    index = Index()
    fired = asyncio.Event()

    async def handler(event):
        fired.set()

    runtime, _ = recovery(index, handler)
    monkeypatch.setattr(listener.RedisClient, "get", AsyncMock(return_value=object()))
    monkeypatch.setattr(listener, "RedisExpiryIndex", lambda client: index)
    monkeypatch.setattr(
        listener.RedisConnectionManager,
        "connect",
        AsyncMock(side_effect=ConnectionError("no pubsub")),
    )
    monkeypatch.setattr(listener.RedisConnectionManager, "disconnect", AsyncMock())
    task = asyncio.create_task(
        listener.run_expiry_listener(
            dispatcher=runtime.dispatcher,
            reconnect_delay=1,
            max_reconnect_attempts=max_attempts,
        )
    )
    try:
        await asyncio.wait_for(fired.wait(), 1)
        assert index.leased
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def test_live_legacy_notifications_are_not_lost_to_the_new_indexed_capacity_limit():
    index = Index(count=2)
    index.claims = {key: DueTrigger(key) for key in index.keys}
    release = asyncio.Event()

    async def handler(event):
        await release.wait()

    runtime, _ = recovery(index, handler, batch_size=1)
    await runtime.deliver(index.keys[0], recovered=False)
    await runtime.deliver(index.keys[1], recovered=False)
    assert len(runtime._inflight) == 2
    release.set()
    await settle(runtime)
