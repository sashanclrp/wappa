"""Tests for the messenger middleware pipeline.

Covers the architectural guarantees callers rely on:

- Empty pipeline is a transparent pass-through over raw ``IMessenger``.
- Middleware runs outer → inner on dispatch, inner → outer on return,
  strictly ordered by priority (highest first).
- ``SendInvocation`` captures named arguments so middleware can emit
  stable payloads without per-method knowledge.
- Exceptions bubble from inner to outer; outer middleware post-hooks do
  not run when an inner middleware raises.
- The headline ordering guarantee the pipeline was built for: a
  lower-priority middleware completes its post-hook before a
  higher-priority middleware publishes. This is what lets downstream
  apps cache to Redis before SSE publishes ``outgoing_bot_message``.
- ``SSELifecycleMiddleware`` preserves the legacy wire envelope and the
  ``flush → await → publish`` order.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from wappa.core.messaging.middleware.sse_lifecycle import SSELifecycleMiddleware
from wappa.core.messaging.pipeline import (
    MessengerMiddleware,
    MessengerPipeline,
    SendInvocation,
    SendNext,
)
from wappa.core.sse import SSEEventHub
from wappa.core.sse.context import sse_event_scope
from wappa.messaging.whatsapp.models.basic_models import MessageResult
from wappa.schemas.core.types import PlatformType


def _make_raw() -> MagicMock:
    raw = MagicMock()
    raw.platform = PlatformType.WHATSAPP
    raw.tenant_id = "test-tenant"

    async def _ok(*args, **kwargs) -> MessageResult:
        return MessageResult(success=True, message_id="wamid.test", recipient="5599")

    for method in (
        "send_text",
        "send_image",
        "send_button_message",
        "send_list_message",
        "send_cta_message",
        "send_text_template",
        "send_contact",
        "send_location",
        "mark_as_read",
    ):
        setattr(raw, method, AsyncMock(side_effect=_ok))
    return raw


class _Recorder(MessengerMiddleware):
    """Records pre/post order into a shared list for assertions."""

    def __init__(self, name: str, log: list[str]) -> None:
        self.name = name
        self._log = log

    async def handle(self, invocation: SendInvocation, call_next: SendNext):
        self._log.append(f"pre:{self.name}")
        result = await call_next(invocation)
        self._log.append(f"post:{self.name}")
        return result


@pytest.mark.asyncio
async def test_pipeline_without_middleware_is_passthrough():
    raw = _make_raw()
    pipeline = MessengerPipeline(raw=raw)

    result = await pipeline.send_text("hi", "5599")

    assert result.success
    raw.send_text.assert_awaited_once_with("hi", "5599", None, False)


@pytest.mark.asyncio
async def test_priority_order_is_outer_to_inner():
    raw = _make_raw()
    log: list[str] = []
    pipeline = MessengerPipeline(
        raw=raw,
        middleware=[
            (_Recorder("low", log), 10),
            (_Recorder("mid", log), 50),
            (_Recorder("high", log), 90),
        ],
    )

    await pipeline.send_text("hi", "5599")

    assert log == [
        "pre:high",
        "pre:mid",
        "pre:low",
        "post:low",
        "post:mid",
        "post:high",
    ]


@pytest.mark.asyncio
async def test_send_invocation_captures_named_arguments():
    raw = _make_raw()
    captured: list[SendInvocation] = []

    class _Capture(MessengerMiddleware):
        name = "capture"

        async def handle(self, invocation, call_next):
            captured.append(invocation)
            return await call_next(invocation)

    pipeline = MessengerPipeline(raw=raw, middleware=[(_Capture(), 50)])
    await pipeline.send_button_message(
        buttons=[{"id": "a", "title": "A"}],
        recipient="5599",
        body="Pick one",
    )

    assert len(captured) == 1
    inv = captured[0]
    assert inv.method_name == "send_button_message"
    assert inv.message_type == "button"
    assert inv.recipient == "5599"
    assert inv.arguments["body"] == "Pick one"
    assert inv.arguments["buttons"] == [{"id": "a", "title": "A"}]


@pytest.mark.asyncio
async def test_exception_skips_outer_post_hook():
    raw = _make_raw()
    log: list[str] = []

    class _Boom(MessengerMiddleware):
        name = "boom"

        async def handle(self, invocation, call_next):
            raise RuntimeError("inner failure")

    pipeline = MessengerPipeline(
        raw=raw,
        middleware=[
            (_Recorder("outer", log), 90),
            (_Boom(), 50),
        ],
    )

    with pytest.raises(RuntimeError, match="inner failure"):
        await pipeline.send_text("hi", "5599")

    # Outer saw pre but not post; no raw call happened.
    assert log == ["pre:outer"]
    raw.send_text.assert_not_called()


@pytest.mark.asyncio
async def test_cache_completes_before_sse_publishes():
    """The headline architectural guarantee.

    A lower-priority ("inner") middleware that simulates a cache write
    must complete before a higher-priority ("outer") middleware that
    simulates an SSE publish runs its post-hook. This is the ordering
    that lets apps keep Redis in sync with SSE subscribers without any
    explicit coordination between the two concerns.
    """
    raw = _make_raw()
    order: list[str] = []

    class _Cache(MessengerMiddleware):
        name = "cache"

        async def handle(self, invocation, call_next):
            result = await call_next(invocation)
            order.append("cache_wrote")
            return result

    class _SSE(MessengerMiddleware):
        name = "sse"

        async def handle(self, invocation, call_next):
            result = await call_next(invocation)
            order.append("sse_published")
            return result

    pipeline = MessengerPipeline(
        raw=raw,
        middleware=[
            (_Cache(), 50),  # inner
            (_SSE(), 70),  # outer
        ],
    )
    await pipeline.send_text("hi", "5599")

    assert order == ["cache_wrote", "sse_published"]


@pytest.mark.asyncio
async def test_mark_as_read_bypasses_pipeline():
    """``mark_as_read`` is not a user-visible message; middleware must not fire."""
    raw = _make_raw()
    log: list[str] = []
    pipeline = MessengerPipeline(
        raw=raw,
        middleware=[(_Recorder("any", log), 50)],
    )

    await pipeline.mark_as_read("wamid.123", typing=True)

    raw.mark_as_read.assert_awaited_once_with("wamid.123", True)
    assert log == []


@pytest.mark.asyncio
async def test_sse_lifecycle_middleware_publishes_after_raw_send():
    """``SSELifecycleMiddleware`` mirrors the legacy envelope shape."""
    raw = _make_raw()
    hub = SSEEventHub(queue_size=8)
    pipeline = MessengerPipeline(
        raw=raw,
        middleware=[(SSELifecycleMiddleware(hub), 70)],
    )

    async with sse_event_scope(
        tenant_id="test-tenant",
        user_id="5599",
        phone_number="5599",
        platform="whatsapp",
    ):
        subscription = await hub.subscribe(
            tenant_id="test-tenant",
            event_types={"outgoing_bot_message"},
        )
        await pipeline.send_text("hola", "5599")
        # Event is published in-line (no asyncio.create_task) so it's
        # immediately available on the queue.
        event = await subscription.queue.get()

    assert event["event_type"] == "outgoing_bot_message"
    assert event["source"] == "bot_messenger"
    assert event["payload"]["message_type"] == "text"
    assert event["payload"]["request"]["text"] == "hola"
    assert event["payload"]["request"]["recipient"] == "5599"
    assert event["payload"]["result"]["success"] is True
