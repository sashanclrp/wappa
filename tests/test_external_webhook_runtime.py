from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from fastapi import FastAPI, Request

from wappa.core.context import WappaContext
from wappa.core.events.event_handler import WappaEventHandler
from wappa.core.events.external_event_dispatcher import ExternalEventDispatcher
from wappa.core.external_webhooks import (
    ExternalWebhookProcessStatus,
    ExternalWebhookRuntime,
    clone_request_with_body,
)
from wappa.core.factory.wappa_builder import WappaBuilder
from wappa.core.plugins import WebhookPlugin
from wappa.domain.events import ExternalEvent
from wappa.webhooks import InboundMessageWebhook


class _RecordingHandler(WappaEventHandler):
    def __init__(self) -> None:
        super().__init__()
        self.events: list[ExternalEvent] = []

    async def process_message(self, webhook: InboundMessageWebhook) -> None:
        return None

    async def process_external_event(self, event: ExternalEvent) -> None:
        self.events.append(event)


class _Processor:
    def __init__(
        self,
        *,
        source: str = "stripe",
        resolved_user_id: str | None = "user-1",
        event_inbox_id: str | None = None,
    ) -> None:
        self.source = source
        self.resolved_user_id = resolved_user_id
        self.event_inbox_id = event_inbox_id
        self.parsed_payload: dict[str, Any] | None = None
        self.raise_on_parse = False

    def get_source_name(self) -> str:
        return self.source

    async def parse_event(self, request: Request, inbox_id: str) -> ExternalEvent:
        if self.raise_on_parse:
            raise ValueError("bad payload")
        self.parsed_payload = await request.json()
        return ExternalEvent(
            source=self.source,
            event_type=self.parsed_payload["type"],
            inbox_id=self.event_inbox_id or inbox_id,
            payload=self.parsed_payload,
        )

    async def resolve_user_id(self, event: ExternalEvent, db: Any) -> str | None:
        return self.resolved_user_id


class _ContextFactory:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def create_context(
        self,
        inbox_id: str,
        user_id: str | None = None,
        *,
        include_messenger: bool = False,
        **_: Any,
    ) -> WappaContext:
        self.calls.append(
            {
                "inbox_id": inbox_id,
                "user_id": user_id,
                "include_messenger": include_messenger,
            }
        )
        return WappaContext(inbox_id=inbox_id, user_id=user_id)


class _FailingDispatcher(ExternalEventDispatcher):
    async def dispatch(
        self,
        event: ExternalEvent,
        request_handler: WappaEventHandler,
    ) -> dict[str, Any]:
        return {"success": False, "error": "handler failed"}


def _runtime(
    processor: _Processor,
    handler: WappaEventHandler,
    *,
    context_factory: _ContextFactory | None = None,
    dispatcher: ExternalEventDispatcher | None = None,
) -> ExternalWebhookRuntime:
    return ExternalWebhookRuntime(
        external_source="stripe",
        processor=processor,
        event_handler=handler,
        context_factory=context_factory or _ContextFactory(),
        dispatcher=dispatcher or ExternalEventDispatcher(),
    )


@pytest.mark.asyncio
async def test_external_webhook_runtime_dispatches_with_resolved_context() -> None:
    processor = _Processor()
    handler = _RecordingHandler()
    context_factory = _ContextFactory()
    runtime = _runtime(processor, handler, context_factory=context_factory)
    request = _request_with_json({"type": "payment.approved", "id": "evt_1"})

    result = await runtime.process(request, "inbox-1")

    assert result.status == ExternalWebhookProcessStatus.ACCEPTED_DISPATCH
    assert result.user_id == "user-1"
    assert processor.parsed_payload == {"type": "payment.approved", "id": "evt_1"}
    assert len(handler.events) == 1
    assert handler.events[0].user_id == "user-1"
    assert context_factory.calls == [
        {"inbox_id": "inbox-1", "user_id": None, "include_messenger": False},
        {"inbox_id": "inbox-1", "user_id": "user-1", "include_messenger": True},
    ]


@pytest.mark.asyncio
async def test_external_webhook_runtime_rejects_event_inbox_mismatch() -> None:
    processor = _Processor(event_inbox_id="wrong-inbox")
    handler = _RecordingHandler()
    runtime = _runtime(processor, handler)

    result = await runtime.process(
        _request_with_json({"type": "payment.approved"}), "inbox-1"
    )

    assert result.status == ExternalWebhookProcessStatus.INBOX_MISMATCH
    assert handler.events == []


@pytest.mark.asyncio
async def test_external_webhook_runtime_reports_parse_failure() -> None:
    processor = _Processor()
    processor.raise_on_parse = True
    handler = _RecordingHandler()
    runtime = _runtime(processor, handler)

    result = await runtime.process(
        _request_with_json({"type": "payment.approved"}), "inbox-1"
    )

    assert result.status == ExternalWebhookProcessStatus.PARSE_FAILURE
    assert "bad payload" in str(result.error)
    assert handler.events == []


@pytest.mark.asyncio
async def test_external_webhook_runtime_reports_unresolved_user_dispatch() -> None:
    processor = _Processor(resolved_user_id=None)
    handler = _RecordingHandler()
    context_factory = _ContextFactory()
    runtime = _runtime(processor, handler, context_factory=context_factory)

    result = await runtime.process(
        _request_with_json({"type": "payment.approved"}), "inbox-1"
    )

    assert result.status == ExternalWebhookProcessStatus.UNRESOLVED_USER
    assert result.user_id is None
    assert len(handler.events) == 1
    assert handler.events[0].user_id is None
    assert context_factory.calls == [
        {"inbox_id": "inbox-1", "user_id": None, "include_messenger": False},
    ]


@pytest.mark.asyncio
async def test_external_webhook_runtime_reports_dispatch_failure() -> None:
    processor = _Processor()
    handler = _RecordingHandler()
    runtime = _runtime(processor, handler, dispatcher=_FailingDispatcher())

    result = await runtime.process(
        _request_with_json({"type": "payment.approved"}), "inbox-1"
    )

    assert result.status == ExternalWebhookProcessStatus.DISPATCH_FAILURE
    assert result.error == "handler failed"


@pytest.mark.asyncio
async def test_clone_request_with_body_preserves_json_for_background_work() -> None:
    request = _request_with_json({"type": "payment.approved"})
    body = await request.body()

    snapshot = clone_request_with_body(request, body)

    assert await snapshot.json() == {"type": "payment.approved"}
    assert await snapshot.body() == body


@pytest.mark.asyncio
async def test_webhook_plugin_requires_inbox_id_for_processor_mode() -> None:
    builder = WappaBuilder().add_plugin(
        WebhookPlugin(
            "stripe",
            processor=_Processor(),
            event_handler=_RecordingHandler(),
            include_inbox_id=False,
        )
    )
    app = builder.build()

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post("/webhook/stripe/", json={"type": "x"})

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "inbox_id is required for External Webhook Source processing"
    )


def _request_with_json(payload: dict[str, Any]) -> Request:
    body = json.dumps(payload).encode()
    consumed = False

    async def receive() -> dict[str, object]:
        nonlocal consumed
        if consumed:
            return {"type": "http.request", "body": b"", "more_body": False}
        consumed = True
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/webhook/stripe/inbox-1",
            "headers": [(b"content-type", b"application/json")],
            "query_string": b"",
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
            "scheme": "http",
            "app": FastAPI(),
        },
        receive,
    )
