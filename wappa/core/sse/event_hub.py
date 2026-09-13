"""Public SSE hub contract and the default in-memory implementation."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable
from uuid import uuid4

from .context import SSEEventContext, get_sse_context


@dataclass(frozen=True, slots=True)
class SSEEventEnvelope:
    """One transport event, preserving Wappa's established JSON wire shape."""

    event_id: str
    event_type: str
    timestamp: str
    inbox_id: str
    user_id: str
    bsuid: str | None
    phone_number: str | None
    platform: str
    source: str
    payload: Mapping[str, Any]
    metadata: Mapping[str, Any] | None

    def to_dict(self) -> dict[str, Any]:
        """Return the backwards-compatible JSON event envelope."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "inbox_id": self.inbox_id,
            "user_id": self.user_id,
            "bsuid": self.bsuid,
            "phone_number": self.phone_number,
            "platform": self.platform,
            "source": self.source,
            "payload": dict(self.payload),
            "metadata": dict(self.metadata) if self.metadata is not None else None,
        }


@dataclass(frozen=True, slots=True)
class SSEDeliveryResult:
    """Process-local outcome of one local envelope delivery."""

    delivered: int = 0
    dropped: int = 0
    overflow_closed: int = 0


@dataclass(frozen=True, slots=True, eq=False)
class SSEPublishResult:
    """The envelope created by ``publish`` and its local delivery outcome."""

    envelope: SSEEventEnvelope
    delivery: SSEDeliveryResult

    @property
    def delivered(self) -> int:
        """Compatibility convenience for callers interested only in fan-out count."""
        return self.delivery.delivered

    def __int__(self) -> int:
        """Preserve simple count consumption for existing low-level callers."""
        return self.delivered

    def __eq__(self, other: object) -> bool:
        """Compare to a legacy delivery count or another publish result."""
        if isinstance(other, int):
            return self.delivered == other
        if isinstance(other, SSEPublishResult):
            return self.envelope == other.envelope and self.delivery == other.delivery
        return NotImplemented


@dataclass(frozen=True, slots=True)
class SSEHubMetrics:
    """Stable process-local connection and delivery counters for an SSE hub."""

    active_subscriptions: int
    published_events: int
    locally_delivered_events: int
    dropped_events: int
    overflow_closures: int
    shutdown_closures: int
    inbox_filtered_subscriptions: int
    platform_filtered_subscriptions: int
    user_filtered_subscriptions: int
    event_filtered_subscriptions: int
    custom: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-ready metrics representation for status endpoints."""
        return {
            "active_subscriptions": self.active_subscriptions,
            "published_events": self.published_events,
            "locally_delivered_events": self.locally_delivered_events,
            "dropped_events": self.dropped_events,
            "overflow_closures": self.overflow_closures,
            "shutdown_closures": self.shutdown_closures,
            "inbox_filtered_subscriptions": self.inbox_filtered_subscriptions,
            "platform_filtered_subscriptions": self.platform_filtered_subscriptions,
            "user_filtered_subscriptions": self.user_filtered_subscriptions,
            "event_filtered_subscriptions": self.event_filtered_subscriptions,
            "custom": dict(self.custom),
        }


@dataclass(slots=True)
class SSESubscription:
    """One live SSE client connection with optional local delivery filters."""

    subscriber_id: str
    queue: asyncio.Queue[Any]
    platform: str | None
    inbox_id: str | None
    user_id: str | None
    event_types: set[str] | None
    delivery_gap: bool = False
    disconnect_reason: str | None = None


@dataclass(frozen=True, slots=True)
class _SSECloseSignal:
    """Internal queue control item that publishers cannot forge as an event."""

    reason: str


@runtime_checkable
class SSEHub(Protocol):
    """Public structural contract used by Wappa's SSE integration points."""

    async def subscribe(
        self,
        *,
        platform: str | None = None,
        inbox_id: str | None = None,
        user_id: str | None = None,
        event_types: set[str] | None = None,
    ) -> SSESubscription: ...
    async def unsubscribe(self, subscriber_id: str) -> None: ...
    async def publish(
        self, *, event_type: str, source: str, payload: Mapping[str, Any]
    ) -> SSEPublishResult: ...
    def deliver_envelope(self, envelope: SSEEventEnvelope) -> SSEDeliveryResult: ...
    async def shutdown(self) -> None: ...
    def snapshot_metrics(self) -> SSEHubMetrics: ...


class SSEEventHub:
    """Loss-aware in-memory implementation of :class:`SSEHub`.

    Overflow closes only the slow subscription. Its stream reconnects rather
    than continuing after a delivery gap; unaffected subscribers keep receiving
    events. The hub is intentionally process-local and non-durable.
    """

    def __init__(self, queue_size: int = 200):
        if queue_size < 1:
            raise ValueError("queue_size must be >= 1")
        self._queue_size = queue_size
        self._subscribers: dict[str, SSESubscription] = {}
        self._lock = asyncio.Lock()
        self._published_events = 0
        self._locally_delivered_events = 0
        self._dropped_events = 0
        self._overflow_closures = 0
        self._shutdown_closures = 0

    async def subscribe(
        self,
        *,
        platform: str | None = None,
        inbox_id: str | None = None,
        user_id: str | None = None,
        event_types: set[str] | None = None,
    ) -> SSESubscription:
        """Register a new subscriber with optional Platform-qualified filters."""
        if inbox_id is not None and platform is None:
            raise ValueError("platform is required when filtering SSE by inbox_id")
        normalized_events = (
            {event.strip() for event in event_types if event.strip()}
            if event_types
            else None
        )
        subscriber = SSESubscription(
            str(uuid4()),
            asyncio.Queue(maxsize=self._queue_size),
            platform,
            inbox_id,
            user_id,
            normalized_events,
        )
        async with self._lock:
            self._subscribers[subscriber.subscriber_id] = subscriber
        return subscriber

    async def unsubscribe(self, subscriber_id: str) -> None:
        """Remove a subscriber; repeated cleanup is harmless."""
        async with self._lock:
            self._subscribers.pop(subscriber_id, None)

    async def publish(
        self, *, event_type: str, source: str, payload: Mapping[str, Any]
    ) -> SSEPublishResult:
        """Create one envelope from the active scope and deliver it locally."""
        context = get_sse_context() or SSEEventContext()
        envelope = self._build_envelope(
            event_type=event_type, source=source, payload=payload, context=context
        )
        self._published_events += 1
        return SSEPublishResult(
            envelope=envelope, delivery=self.deliver_envelope(envelope)
        )

    def deliver_envelope(self, envelope: SSEEventEnvelope) -> SSEDeliveryResult:
        """Fan out an existing envelope locally without rebuilding or rebroadcasting it."""
        delivered = dropped = overflow_closed = 0
        for subscriber in tuple(self._subscribers.values()):
            if subscriber.disconnect_reason is not None or not self._matches(
                subscriber, envelope
            ):
                continue
            if self._enqueue_event(subscriber, envelope):
                delivered += 1
            else:
                dropped += self._close_for_backpressure(subscriber)
                overflow_closed += 1
        self._locally_delivered_events += delivered
        self._dropped_events += dropped
        self._overflow_closures += overflow_closed
        return SSEDeliveryResult(
            delivered=delivered, dropped=dropped, overflow_closed=overflow_closed
        )

    async def shutdown(self) -> None:
        """Close every active stream with a distinct shutdown control signal."""
        async with self._lock:
            subscribers = tuple(self._subscribers.values())
            self._subscribers.clear()
        for subscriber in subscribers:
            if subscriber.disconnect_reason is None:
                self._close_subscription(subscriber, reason="shutdown")
                self._shutdown_closures += 1

    def snapshot_metrics(self) -> SSEHubMetrics:
        """Return the stable, typed process-local metrics snapshot."""
        subscribers = tuple(self._subscribers.values())
        return SSEHubMetrics(
            active_subscriptions=len(subscribers),
            published_events=self._published_events,
            locally_delivered_events=self._locally_delivered_events,
            dropped_events=self._dropped_events,
            overflow_closures=self._overflow_closures,
            shutdown_closures=self._shutdown_closures,
            inbox_filtered_subscriptions=sum(
                item.inbox_id is not None for item in subscribers
            ),
            platform_filtered_subscriptions=sum(
                item.platform is not None for item in subscribers
            ),
            user_filtered_subscriptions=sum(
                item.user_id is not None for item in subscribers
            ),
            event_filtered_subscriptions=sum(
                item.event_types is not None for item in subscribers
            ),
        )

    def get_stats(self) -> dict[str, Any]:
        """Compatibility alias returning the legacy filter-only stats shape."""
        metrics = self.snapshot_metrics()
        return {
            "active_subscribers": metrics.active_subscriptions,
            "inbox_filtered_subscribers": metrics.inbox_filtered_subscriptions,
            "platform_filtered_subscribers": metrics.platform_filtered_subscriptions,
            "user_filtered_subscribers": metrics.user_filtered_subscriptions,
            "event_filtered_subscribers": metrics.event_filtered_subscriptions,
        }

    @staticmethod
    def is_close_signal(item: object) -> bool:
        """Return whether a queue item is Wappa's private stream-close signal."""
        return isinstance(item, _SSECloseSignal)

    @staticmethod
    def close_reason(item: object) -> str | None:
        """Read a close reason from a queue control item, if present."""
        return item.reason if isinstance(item, _SSECloseSignal) else None

    @staticmethod
    def _build_envelope(
        *,
        event_type: str,
        source: str,
        payload: Mapping[str, Any],
        context: SSEEventContext,
    ) -> SSEEventEnvelope:
        return SSEEventEnvelope(
            event_id=str(uuid4()),
            event_type=event_type,
            timestamp=datetime.now(UTC).isoformat(),
            inbox_id=context.inbox_id,
            user_id=context.user_id,
            bsuid=context.bsuid,
            phone_number=context.phone_number,
            platform=context.platform,
            source=source,
            payload=dict(payload),
            metadata=dict(context.metadata) if context.metadata else None,
        )

    @staticmethod
    def _matches(subscriber: SSESubscription, envelope: SSEEventEnvelope) -> bool:
        return (
            (subscriber.platform is None or subscriber.platform == envelope.platform)
            and (
                subscriber.inbox_id is None or subscriber.inbox_id == envelope.inbox_id
            )
            and (subscriber.user_id is None or subscriber.user_id == envelope.user_id)
            and (
                subscriber.event_types is None
                or envelope.event_type in subscriber.event_types
            )
        )

    @staticmethod
    def _enqueue_event(subscriber: SSESubscription, envelope: SSEEventEnvelope) -> bool:
        try:
            subscriber.queue.put_nowait(envelope.to_dict())
            return True
        except asyncio.QueueFull:
            return False

    def _close_for_backpressure(self, subscriber: SSESubscription) -> int:
        """Drop queued work and force reconnect after the first delivery gap."""
        return self._close_subscription(subscriber, reason="backpressure_gap") + 1

    @staticmethod
    def _close_subscription(subscriber: SSESubscription, *, reason: str) -> int:
        subscriber.delivery_gap = reason == "backpressure_gap"
        subscriber.disconnect_reason = reason
        discarded = 0
        while True:
            try:
                subscriber.queue.get_nowait()
                discarded += 1
            except asyncio.QueueEmpty:
                break
        subscriber.queue.put_nowait(_SSECloseSignal(reason=reason))
        return discarded
