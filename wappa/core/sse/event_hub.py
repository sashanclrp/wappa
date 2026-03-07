"""In-memory event hub for Server-Sent Events subscribers."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4


@dataclass(slots=True)
class SSESubscription:
    """Represents one active SSE subscriber."""

    subscriber_id: str
    queue: asyncio.Queue[dict[str, Any]]
    tenant_id: str | None
    user_id: str | None
    event_types: set[str] | None


class SSEEventHub:
    """Simple async fan-out hub for in-process SSE subscribers."""

    def __init__(self, queue_size: int = 200):
        if queue_size < 1:
            raise ValueError("queue_size must be >= 1")

        self._queue_size = queue_size
        self._subscribers: dict[str, SSESubscription] = {}
        self._lock = asyncio.Lock()

    async def subscribe(
        self,
        *,
        tenant_id: str | None = None,
        user_id: str | None = None,
        event_types: set[str] | None = None,
    ) -> SSESubscription:
        """Register a new subscriber with optional filters."""
        normalized_events: set[str] | None = None
        if event_types:
            normalized_events = {
                event.strip() for event in event_types if event.strip()
            }

        subscriber = SSESubscription(
            subscriber_id=str(uuid4()),
            queue=asyncio.Queue(maxsize=self._queue_size),
            tenant_id=tenant_id,
            user_id=user_id,
            event_types=normalized_events,
        )

        async with self._lock:
            self._subscribers[subscriber.subscriber_id] = subscriber

        return subscriber

    async def unsubscribe(self, subscriber_id: str) -> None:
        """Remove a subscriber."""
        async with self._lock:
            self._subscribers.pop(subscriber_id, None)

    async def publish(
        self,
        *,
        event_type: str,
        tenant_id: str,
        user_id: str,
        platform: str,
        source: str,
        payload: dict[str, Any],
    ) -> int:
        """Fan out one event to all matching subscribers."""
        event = self._build_event(
            event_type=event_type,
            tenant_id=tenant_id,
            user_id=user_id,
            platform=platform,
            source=source,
            payload=payload,
        )

        async with self._lock:
            subscribers = tuple(self._subscribers.values())

        delivered = 0
        for subscriber in subscribers:
            if not self._matches(
                subscriber=subscriber,
                event_type=event_type,
                tenant_id=tenant_id,
                user_id=user_id,
            ):
                continue

            if self._enqueue(subscriber.queue, event):
                delivered += 1

        return delivered

    async def shutdown(self) -> None:
        """Close hub and notify current subscribers."""
        async with self._lock:
            subscribers = tuple(self._subscribers.values())
            self._subscribers.clear()

        close_event = self._build_event(
            event_type="stream_closed",
            tenant_id="system",
            user_id="system",
            platform="system",
            source="wappa",
            payload={"reason": "shutdown"},
        )

        for subscriber in subscribers:
            self._enqueue(subscriber.queue, close_event)

    def get_stats(self) -> dict[str, int]:
        """Expose basic connection stats for health checks."""
        subscribers = tuple(self._subscribers.values())
        tenant_filtered = sum(1 for item in subscribers if item.tenant_id is not None)
        user_filtered = sum(1 for item in subscribers if item.user_id is not None)
        event_filtered = sum(1 for item in subscribers if item.event_types is not None)

        return {
            "active_subscribers": len(subscribers),
            "tenant_filtered_subscribers": tenant_filtered,
            "user_filtered_subscribers": user_filtered,
            "event_filtered_subscribers": event_filtered,
        }

    def _build_event(
        self,
        *,
        event_type: str,
        tenant_id: str,
        user_id: str,
        platform: str,
        source: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Build the SSE envelope sent to clients."""
        return {
            "event_id": str(uuid4()),
            "event_type": event_type,
            "timestamp": datetime.now(UTC).isoformat(),
            "tenant_id": tenant_id,
            "user_id": user_id,
            "platform": platform,
            "source": source,
            "payload": payload,
        }

    def _matches(
        self,
        *,
        subscriber: SSESubscription,
        event_type: str,
        tenant_id: str,
        user_id: str,
    ) -> bool:
        """Check whether an event should be delivered to a subscriber."""
        if subscriber.tenant_id is not None and subscriber.tenant_id != tenant_id:
            return False

        if subscriber.user_id is not None and subscriber.user_id != user_id:
            return False

        return subscriber.event_types is None or event_type in subscriber.event_types

    def _enqueue(
        self, queue: asyncio.Queue[dict[str, Any]], event: dict[str, Any]
    ) -> bool:
        """Push event without blocking. Drops oldest event when queue is full."""
        try:
            queue.put_nowait(event)
            return True
        except asyncio.QueueFull:
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                return False

            try:
                queue.put_nowait(event)
                return True
            except asyncio.QueueFull:
                return False
