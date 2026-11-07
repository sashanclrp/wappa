"""End-to-end coverage for the SSE context propagation contract.

These tests exercise:
- ``sse_event_scope`` sets and resets the contextvar cleanly.
- ``update_metadata`` / ``update_identity`` mutate the active context.
- ``publish_sse_event`` reads identity + metadata from the active scope,
  so envelopes always carry ``bsuid`` / ``phone_number`` / ``metadata``.
- ``SSEMessageHandler`` defers emission until enrichment or the
  ``post_process_message`` fallback, preserving the app's metadata.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock

import pytest

from wappa.core.lifecycle import BackgroundWorkTracker
from wappa.core.sse import (
    SUPPORTED_SSE_EVENT_TYPES,
    SSEEventHub,
    SSEMessageHandler,
    publish_sse_event,
    register_sse_event_type,
)
from wappa.core.sse.context import (
    get_sse_context,
    sse_event_scope,
    update_identity,
    update_metadata,
)


def _drain(subscription) -> list[dict]:
    """Read events after the awaited publisher has completed queue insertion."""
    events: list[dict] = []
    while not subscription.queue.empty():
        events.append(subscription.queue.get_nowait())
    return events


@pytest.fixture
def custom_sse_event_type() -> Iterator[str]:
    """Provide a custom event type without leaking registry state between tests."""
    event_type = "host_custom_test_event"
    SUPPORTED_SSE_EVENT_TYPES.discard(event_type)
    yield event_type
    SUPPORTED_SSE_EVENT_TYPES.discard(event_type)


@pytest.mark.asyncio
async def test_sse_event_scope_sets_and_resets_contextvar():
    assert get_sse_context() is None

    async with sse_event_scope(
        inbox_id="t-1",
        user_id="US.canonical",
        bsuid="US.canonical",
        phone_number="15551234567",
        platform="whatsapp",
    ) as ctx:
        assert get_sse_context() is ctx
        assert ctx.bsuid == "US.canonical"
        assert ctx.phone_number == "15551234567"

    assert get_sse_context() is None


@pytest.mark.asyncio
async def test_update_metadata_and_identity_apply_to_active_scope():
    async with sse_event_scope(
        platform="whatsapp", inbox_id="t-1", user_id="15551234567"
    ):
        update_metadata(conversation_id="conv-42", run_id="run-1")
        update_identity(bsuid="US.new", phone_number="15551234567")

        ctx = get_sse_context()
        assert ctx is not None
        assert ctx.metadata == {"conversation_id": "conv-42", "run_id": "run-1"}
        assert ctx.bsuid == "US.new"
        assert ctx.phone_number == "15551234567"


@pytest.mark.asyncio
async def test_update_metadata_outside_scope_is_noop():
    # Should not raise — tests that app code can call these helpers
    # defensively without first checking for an active scope.
    update_metadata(conversation_id="conv-42")
    update_identity(bsuid="US.x", phone_number="15551234567")
    assert get_sse_context() is None


@pytest.mark.asyncio
async def test_publish_sse_event_reads_identity_from_context():
    hub = SSEEventHub()
    sub = await hub.subscribe()

    async with sse_event_scope(
        inbox_id="t-1",
        user_id="US.canonical",
        bsuid="US.canonical",
        phone_number="15551234567",
        platform="whatsapp",
    ):
        update_metadata(conversation_id="conv-42")
        await publish_sse_event(
            hub,
            event_type="incoming_message",
            source="webhook",
            payload={"foo": "bar"},
        )

    events = _drain(sub)
    assert len(events) == 1
    env = events[0]
    assert env["inbox_id"] == "t-1"
    assert env["user_id"] == "US.canonical"
    assert env["bsuid"] == "US.canonical"
    assert env["phone_number"] == "15551234567"
    assert env["platform"] == "whatsapp"
    assert env["event_type"] == "incoming_message"
    assert env["source"] == "webhook"
    assert env["payload"] == {"foo": "bar"}
    assert env["metadata"] == {"conversation_id": "conv-42"}


@pytest.mark.asyncio
async def test_publish_sse_event_without_scope_yields_defaults():
    """Outside any scope the envelope falls back to unknown identity and no metadata."""
    hub = SSEEventHub()
    sub = await hub.subscribe()

    await publish_sse_event(
        hub,
        event_type="outgoing_bot_message",
        source="bot_messenger",
        payload={"ok": True},
    )

    events = _drain(sub)
    assert len(events) == 1
    env = events[0]
    assert env["inbox_id"] == "unknown"
    assert env["user_id"] == "unknown"
    assert env["bsuid"] is None
    assert env["phone_number"] is None
    assert env["metadata"] is None


@pytest.mark.asyncio
async def test_publish_sse_event_rejects_unknown_event_type() -> None:
    hub = SSEEventHub()
    sub = await hub.subscribe()

    delivered = await publish_sse_event(
        hub,
        event_type="not_registered",
        source="test",
        payload={"ok": True},
    )

    assert delivered == 0
    assert _drain(sub) == []


@pytest.mark.asyncio
async def test_publish_sse_event_delivers_registered_custom_event_type(
    custom_sse_event_type: str,
) -> None:
    register_sse_event_type(custom_sse_event_type)
    hub = SSEEventHub()
    sub = await hub.subscribe(event_types={custom_sse_event_type})

    async with sse_event_scope(
        platform="whatsapp", inbox_id="inbox-1", user_id="user-1"
    ):
        delivered = await publish_sse_event(
            hub,
            event_type=custom_sse_event_type,
            source="host",
            payload={"value": 42},
        )

    events = _drain(sub)
    assert delivered == 1
    assert len(events) == 1
    assert events[0]["event_type"] == custom_sse_event_type
    assert events[0]["inbox_id"] == "inbox-1"
    assert events[0]["user_id"] == "user-1"
    assert events[0]["payload"] == {"value": 42}


@pytest.mark.asyncio
async def test_publish_sse_event_hub_failure_returns_zero() -> None:
    class FailingHub(SSEEventHub):
        async def publish(
            self,
            *,
            event_type: str,
            source: str,
            payload: dict[str, Any],
        ) -> int:
            raise RuntimeError("hub unavailable")

    delivered = await publish_sse_event(
        FailingHub(),
        event_type="incoming_message",
        source="test",
        payload={"ok": True},
    )

    assert delivered == 0


@dataclass
class _FakeUser:
    user_id: str
    bsuid: str | None
    phone_number: str | None


class _FakeWebhook:
    """Minimal stand-in for InboundMessageWebhook for the deferred-flush path."""

    def __init__(self):
        self.user = _FakeUser(
            user_id="US.canonical", bsuid="US.canonical", phone_number="15551234567"
        )
        self.inbox = MagicMock()
        self.inbox.get_tenant_key = MagicMock(return_value="t-1")
        self.platform = MagicMock()
        self.platform.value = "whatsapp"
        self.message = MagicMock()
        self.message.to_universal_dict = MagicMock(return_value={"text": "hi"})
        self.message.model_dump = MagicMock(return_value={"text": "hi"})

    def model_dump(self, **_kwargs):
        return {"user": {"user_id": self.user.user_id}, "message": {"text": "hi"}}

    def get_message_type_name(self) -> str:
        return "text"

    def get_message_text(self) -> str:
        return "hi"


@pytest.mark.asyncio
async def test_incoming_message_defers_until_enrichment_and_keeps_metadata():
    hub = SSEEventHub()
    sub = await hub.subscribe()
    handler = SSEMessageHandler(event_hub=hub)
    webhook = _FakeWebhook()
    tracker = BackgroundWorkTracker()

    async with sse_event_scope(
        platform="whatsapp",
        inbox_id="t-1",
        user_id="US.canonical",
        bsuid="US.canonical",
        phone_number="15551234567",
        tracker=tracker,
    ):
        await handler.log_incoming_message(webhook)

        # No event should have been published yet — emission is deferred.
        assert tracker.active_count == 0
        immediate = _drain(sub)
        assert immediate == []

        # Simulate the app pipeline enriching the envelope mid-request.
        update_metadata(conversation_id="conv-42", chat_id="chat-7")

        await handler.post_process_message(webhook)

    drained = await tracker.drain(timeout=1)
    assert drained.completed == 1
    assert not drained.timed_out
    events = _drain(sub)
    assert len(events) == 1
    env = events[0]
    assert env["event_type"] == "incoming_message"
    assert env["bsuid"] == "US.canonical"
    assert env["phone_number"] == "15551234567"
    assert env["metadata"] == {"conversation_id": "conv-42", "chat_id": "chat-7"}


@pytest.mark.asyncio
async def test_post_process_without_staged_payload_is_noop():
    """Ensures apps that never hit ``log_incoming_message`` don't emit a stray event."""
    hub = SSEEventHub()
    sub = await hub.subscribe()
    handler = SSEMessageHandler(event_hub=hub)
    webhook = _FakeWebhook()
    tracker = BackgroundWorkTracker()

    async with sse_event_scope(
        platform="whatsapp", inbox_id="t-1", user_id="US.canonical", tracker=tracker
    ):
        await handler.post_process_message(webhook)

    drained = await tracker.drain(timeout=1)
    assert drained.completed == 0
    assert not drained.timed_out
    events = _drain(sub)
    assert events == []
