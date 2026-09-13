"""Public-contract tests for pluggable SSE hubs."""

from __future__ import annotations

from collections.abc import Mapping

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from wappa.core.factory.wappa_builder import WappaBuilder
from wappa.core.plugins.sse_events_plugin import SSEEventsPlugin
from wappa.sse import (
    SSEDeliveryResult,
    SSEEventEnvelope,
    SSEEventHub,
    SSEHub,
    SSEHubMetrics,
    SSEPublishResult,
    SSESubscription,
)


class BrokeredHubDecorator:
    """Consumer-style decorator using only Wappa's public SSE contract."""

    def __init__(self, queue_size: int) -> None:
        self.local_hub = SSEEventHub(queue_size=queue_size)
        self.published_envelopes: list[SSEEventEnvelope] = []
        self.locally_delivered_envelopes: list[SSEEventEnvelope] = []
        self.shutdown_calls = 0

    async def subscribe(
        self,
        *,
        platform: str | None = None,
        inbox_id: str | None = None,
        user_id: str | None = None,
        event_types: set[str] | None = None,
    ) -> SSESubscription:
        return await self.local_hub.subscribe(
            platform=platform,
            inbox_id=inbox_id,
            user_id=user_id,
            event_types=event_types,
        )

    async def unsubscribe(self, subscriber_id: str) -> None:
        await self.local_hub.unsubscribe(subscriber_id)

    async def publish(
        self,
        *,
        event_type: str,
        source: str,
        payload: Mapping[str, object],
    ) -> SSEPublishResult:
        result = await self.local_hub.publish(
            event_type=event_type,
            source=source,
            payload=payload,
        )
        self.published_envelopes.append(result.envelope)
        return result

    def deliver_envelope(self, envelope: SSEEventEnvelope) -> SSEDeliveryResult:
        self.locally_delivered_envelopes.append(envelope)
        return self.local_hub.deliver_envelope(envelope)

    async def shutdown(self) -> None:
        self.shutdown_calls += 1
        await self.local_hub.shutdown()

    def snapshot_metrics(self) -> SSEHubMetrics:
        return self.local_hub.snapshot_metrics()


def test_plugin_uses_one_structural_hub_from_its_factory() -> None:
    created: list[BrokeredHubDecorator] = []

    def factory(queue_size: int) -> BrokeredHubDecorator:
        hub = BrokeredHubDecorator(queue_size)
        created.append(hub)
        return hub

    plugin = SSEEventsPlugin(event_hub_factory=factory)
    app = WappaBuilder().add_plugin(plugin).build()

    with TestClient(app) as client:
        hub = created[0]
        assert len(created) == 1
        assert isinstance(hub, SSEHub)
        assert app.state.sse_event_hub is hub
        status = client.get("/api/sse/status")
        assert status.status_code == 200
        assert status.json()["hub"]["active_subscriptions"] == 0

    assert created[0].shutdown_calls == 1


def test_plugin_uses_the_standard_in_memory_hub_by_default() -> None:
    app = WappaBuilder().add_plugin(SSEEventsPlugin()).build()

    with TestClient(app):
        assert isinstance(app.state.sse_event_hub, SSEEventHub)


@pytest.mark.asyncio
async def test_plugin_health_reads_metrics_from_a_structural_hub() -> None:
    app = FastAPI()
    app.state.sse_event_hub = BrokeredHubDecorator(queue_size=2)

    health = await SSEEventsPlugin().get_health_status(app)

    assert health["healthy"] is True
    assert health["hub"]["published_events"] == 0


def test_plugin_rejects_duplicate_hub_configuration() -> None:
    with pytest.raises(ValueError, match="event_hub or event_hub_factory"):
        SSEEventsPlugin(
            event_hub=SSEEventHub(),
            event_hub_factory=lambda queue_size: SSEEventHub(queue_size),
        )


@pytest.mark.asyncio
async def test_brokered_decorator_delivers_remote_envelopes_without_republishing() -> (
    None
):
    hub = BrokeredHubDecorator(queue_size=2)
    subscriber = await hub.subscribe()

    created = await hub.publish(
        event_type="incoming_message",
        source="test",
        payload={"value": "local"},
    )
    subscriber.queue.get_nowait()

    hub.deliver_envelope(created.envelope)

    received = subscriber.queue.get_nowait()
    assert received["event_id"] == created.envelope.event_id
    assert hub.published_envelopes == [created.envelope]
    assert hub.locally_delivered_envelopes == [created.envelope]
