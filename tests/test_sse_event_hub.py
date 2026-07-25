"""Tests for SSEEventHub subscription, fan-out, overflow, and cleanup."""

from __future__ import annotations

import pytest

from wappa.core.sse.context import SSEEventContext, sse_event_scope
from wappa.sse import SSEEventHub


async def _publish(hub: SSEEventHub, event_type: str, **payload) -> int:
    return await hub.publish(event_type=event_type, source="test", payload=payload)


def _drain(subscription) -> list[dict]:
    events = []
    while not subscription.queue.empty():
        events.append(subscription.queue.get_nowait())
    return events


@pytest.mark.asyncio
async def test_subscriber_receives_published_events() -> None:
    hub = SSEEventHub()
    subscriber = await hub.subscribe()

    async with sse_event_scope(inbox_id="inbox-1", user_id="user-1"):
        assert await _publish(hub, "incoming_message", text="hi") == 1

    event = subscriber.queue.get_nowait()
    assert event["event_type"] == "incoming_message"
    assert event["payload"] == {"text": "hi"}
    assert event["inbox_id"] == "inbox-1"
    assert event["user_id"] == "user-1"
    assert event["event_id"]


@pytest.mark.asyncio
async def test_events_fan_out_to_every_matching_subscriber() -> None:
    hub = SSEEventHub()
    subscribers = [await hub.subscribe() for _ in range(3)]

    async with sse_event_scope(inbox_id="inbox-1", user_id="user-1"):
        assert await _publish(hub, "incoming_message") == 3

    assert all(subscriber.queue.qsize() == 1 for subscriber in subscribers)


@pytest.mark.asyncio
async def test_inbox_filter_excludes_other_inboxes() -> None:
    hub = SSEEventHub()
    mine = await hub.subscribe(inbox_id="inbox-1")
    theirs = await hub.subscribe(inbox_id="inbox-2")

    async with sse_event_scope(inbox_id="inbox-1", user_id="user-1"):
        assert await _publish(hub, "incoming_message") == 1

    assert mine.queue.qsize() == 1
    assert theirs.queue.empty()


@pytest.mark.asyncio
async def test_user_filter_excludes_other_users() -> None:
    hub = SSEEventHub()
    mine = await hub.subscribe(user_id="user-1")
    theirs = await hub.subscribe(user_id="user-2")

    async with sse_event_scope(inbox_id="inbox-1", user_id="user-1"):
        await _publish(hub, "incoming_message")

    assert mine.queue.qsize() == 1
    assert theirs.queue.empty()


@pytest.mark.asyncio
async def test_event_type_filter_only_delivers_subscribed_types() -> None:
    hub = SSEEventHub()
    subscriber = await hub.subscribe(event_types={"status_change"})

    async with sse_event_scope(inbox_id="inbox-1", user_id="user-1"):
        await _publish(hub, "incoming_message")
        await _publish(hub, "status_change")

    events = _drain(subscriber)
    assert [event["event_type"] for event in events] == ["status_change"]


@pytest.mark.asyncio
async def test_publish_without_subscribers_delivers_nothing() -> None:
    hub = SSEEventHub()

    async with sse_event_scope(inbox_id="inbox-1", user_id="user-1"):
        assert await _publish(hub, "incoming_message") == 0


@pytest.mark.asyncio
async def test_full_queue_drops_the_oldest_event_and_keeps_the_newest() -> None:
    # A slow client must not stall the publisher or the other subscribers:
    # overflow is resolved by dropping the oldest event, not by blocking.
    hub = SSEEventHub(queue_size=2)
    subscriber = await hub.subscribe()

    async with sse_event_scope(inbox_id="inbox-1", user_id="user-1"):
        for index in range(4):
            assert await _publish(hub, "incoming_message", index=index) == 1

    events = _drain(subscriber)
    assert [event["payload"]["index"] for event in events] == [2, 3]


@pytest.mark.asyncio
async def test_a_full_subscriber_does_not_starve_the_others() -> None:
    hub = SSEEventHub(queue_size=1)
    slow = await hub.subscribe()
    fast = await hub.subscribe()

    async with sse_event_scope(inbox_id="inbox-1", user_id="user-1"):
        await _publish(hub, "incoming_message", index=0)
        fast.queue.get_nowait()
        await _publish(hub, "incoming_message", index=1)

    assert slow.queue.get_nowait()["payload"]["index"] == 1
    assert fast.queue.get_nowait()["payload"]["index"] == 1


@pytest.mark.asyncio
async def test_unsubscribe_stops_delivery_and_updates_stats() -> None:
    hub = SSEEventHub()
    subscriber = await hub.subscribe(inbox_id="inbox-1")
    assert hub.get_stats()["active_subscribers"] == 1

    await hub.unsubscribe(subscriber.subscriber_id)

    async with sse_event_scope(inbox_id="inbox-1", user_id="user-1"):
        assert await _publish(hub, "incoming_message") == 0

    assert hub.get_stats()["active_subscribers"] == 0
    assert subscriber.queue.empty()


@pytest.mark.asyncio
async def test_unsubscribing_an_unknown_subscriber_is_harmless() -> None:
    hub = SSEEventHub()
    await hub.unsubscribe("never-registered")
    assert hub.get_stats()["active_subscribers"] == 0


@pytest.mark.asyncio
async def test_shutdown_notifies_and_clears_subscribers() -> None:
    hub = SSEEventHub()
    subscriber = await hub.subscribe()

    await hub.shutdown()

    closing = subscriber.queue.get_nowait()
    assert closing["event_type"] == "stream_closed"
    assert closing["payload"] == {"reason": "shutdown"}
    assert hub.get_stats()["active_subscribers"] == 0


@pytest.mark.asyncio
async def test_stats_report_filter_usage() -> None:
    hub = SSEEventHub()
    await hub.subscribe()
    await hub.subscribe(inbox_id="inbox-1")
    await hub.subscribe(user_id="user-1", event_types={"status_change"})

    assert hub.get_stats() == {
        "active_subscribers": 3,
        "inbox_filtered_subscribers": 1,
        "user_filtered_subscribers": 1,
        "event_filtered_subscribers": 1,
    }


@pytest.mark.asyncio
async def test_envelope_carries_scope_identity_and_metadata() -> None:
    hub = SSEEventHub()
    subscriber = await hub.subscribe()

    async with sse_event_scope(
        inbox_id="inbox-1",
        user_id="user-1",
        bsuid="CC.abc",
        phone_number="15551234567",
        platform="whatsapp",
        metadata={"campaign": "welcome"},
    ):
        await _publish(hub, "incoming_message")

    event = subscriber.queue.get_nowait()
    assert event["bsuid"] == "CC.abc"
    assert event["phone_number"] == "15551234567"
    assert event["platform"] == "whatsapp"
    assert event["metadata"] == {"campaign": "welcome"}
    assert event["source"] == "test"


@pytest.mark.asyncio
async def test_publish_outside_a_scope_uses_context_defaults() -> None:
    hub = SSEEventHub()
    subscriber = await hub.subscribe()

    assert await _publish(hub, "incoming_message") == 1

    event = subscriber.queue.get_nowait()
    defaults = SSEEventContext()
    assert event["inbox_id"] == defaults.inbox_id
    assert event["user_id"] == defaults.user_id


def test_queue_size_must_be_positive() -> None:
    with pytest.raises(ValueError, match="queue_size"):
        SSEEventHub(queue_size=0)
