"""End-to-end coverage for the v0.3.6 SSE context propagation contract.

These tests exercise:
- ``sse_event_scope`` sets and resets the contextvar cleanly.
- ``update_metadata`` / ``update_identity`` mutate the active context.
- ``publish_sse_event`` reads identity + metadata from the active scope,
  so envelopes always carry ``bsuid`` / ``phone_number`` / ``metadata``.
- ``SSEMessageHandler`` defers emission until ``post_process_message``,
  picking up metadata the app set during ``process_message``.
- ``SSEMessengerWrapper`` publishes with zero per-wrapper identity and
  still produces a complete envelope when a scope is active.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest

from wappa.core.sse import (
    SSEEventHub,
    SSEMessageHandler,
    SSEMessengerWrapper,
    publish_sse_event,
)
from wappa.core.sse.context import (
    get_sse_context,
    sse_event_scope,
    update_identity,
    update_metadata,
)


async def _drain(subscription, timeout: float = 0.5) -> list[dict]:
    """Collect every queued event within ``timeout`` seconds."""
    events: list[dict] = []
    while True:
        try:
            events.append(
                await asyncio.wait_for(subscription.queue.get(), timeout=timeout)
            )
        except asyncio.TimeoutError:
            return events


@pytest.mark.asyncio
async def test_sse_event_scope_sets_and_resets_contextvar():
    assert get_sse_context() is None

    async with sse_event_scope(
        tenant_id="t-1",
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
    async with sse_event_scope(tenant_id="t-1", user_id="15551234567"):
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
        tenant_id="t-1",
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

    events = await _drain(sub, timeout=0.1)
    assert len(events) == 1
    env = events[0]
    assert env["tenant_id"] == "t-1"
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

    events = await _drain(sub, timeout=0.1)
    assert len(events) == 1
    env = events[0]
    assert env["tenant_id"] == "unknown"
    assert env["user_id"] == "unknown"
    assert env["bsuid"] is None
    assert env["phone_number"] is None
    assert env["metadata"] is None


@pytest.mark.asyncio
async def test_sse_messenger_wrapper_emits_with_context_identity():
    hub = SSEEventHub()
    sub = await hub.subscribe()

    inner = MagicMock()
    inner.platform.value = "whatsapp"
    inner.tenant_id = "t-1"
    # Mimic IMessenger.send_text return contract.
    fake_result = MagicMock()
    fake_result.model_dump = MagicMock(return_value={"message_id": "wamid.xyz"})
    inner.send_text = AsyncMock(return_value=fake_result)

    wrapper = SSEMessengerWrapper(inner=inner, event_hub=hub)

    async with sse_event_scope(
        tenant_id="t-1",
        user_id="US.canonical",
        bsuid="US.canonical",
        phone_number="15551234567",
    ):
        update_metadata(conversation_id="conv-42")
        await wrapper.send_text("hello", recipient="15551234567")

    events = await _drain(sub, timeout=0.1)
    assert len(events) == 1
    env = events[0]
    assert env["event_type"] == "outgoing_bot_message"
    assert env["source"] == "bot_messenger"
    assert env["bsuid"] == "US.canonical"
    assert env["phone_number"] == "15551234567"
    assert env["metadata"] == {"conversation_id": "conv-42"}
    assert env["payload"]["message_type"] == "text"


@dataclass
class _FakeUser:
    user_id: str
    bsuid: str | None
    phone_number: str | None


class _FakeWebhook:
    """Minimal stand-in for IncomingMessageWebhook for the deferred-flush path."""

    def __init__(self):
        self.user = _FakeUser(
            user_id="US.canonical", bsuid="US.canonical", phone_number="15551234567"
        )
        self.tenant = MagicMock()
        self.tenant.get_tenant_key = MagicMock(return_value="t-1")
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
async def test_incoming_message_defers_until_post_process_and_picks_up_metadata():
    hub = SSEEventHub()
    sub = await hub.subscribe()
    handler = SSEMessageHandler(event_hub=hub)
    webhook = _FakeWebhook()

    async with sse_event_scope(
        tenant_id="t-1",
        user_id="US.canonical",
        bsuid="US.canonical",
        phone_number="15551234567",
    ):
        await handler.log_incoming_message(webhook)

        # No event should have been published yet — emission is deferred.
        immediate = await _drain(sub, timeout=0.05)
        assert immediate == []

        # Simulate the app pipeline enriching the envelope mid-request.
        update_metadata(conversation_id="conv-42", chat_id="chat-7")

        await handler.post_process_message(webhook)

    events = await _drain(sub, timeout=0.1)
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

    async with sse_event_scope(tenant_id="t-1", user_id="US.canonical"):
        await handler.post_process_message(webhook)

    events = await _drain(sub, timeout=0.05)
    assert events == []
