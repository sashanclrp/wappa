from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from fastapi import FastAPI, HTTPException, Request
from pydantic import ValidationError

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
from wappa.domain.inbox import InboxRef
from wappa.domain.interfaces.external_webhook_context import (
    ResolvedExternalWebhookContext,
)
from wappa.schemas.core.types import PlatformType
from wappa.webhooks import InboundMessageWebhook


class _RecordingHandler(WappaEventHandler):
    def __init__(self) -> None:
        super().__init__()
        self.events: list[ExternalEvent] = []
        self.bound_contexts: list[tuple[str | None, str | None]] = []

    async def process_message(self, webhook: InboundMessageWebhook) -> None:
        return None

    async def process_external_event(self, event: ExternalEvent) -> None:
        self.events.append(event)
        self.bound_contexts.append((self.inbox_id, self.user_id))


class _Processor:
    def __init__(self, *, source: str = "stripe") -> None:
        self.source = source
        self.parsed_payload: dict[str, Any] | None = None
        self.webhook_ids: list[str | None] = []
        self.raise_on_parse: Exception | None = None

    def get_source_name(self) -> str:
        return self.source

    async def parse_event(
        self, request: Request, webhook_id: str | None
    ) -> ExternalEvent:
        if self.raise_on_parse is not None:
            raise self.raise_on_parse
        self.webhook_ids.append(webhook_id)
        self.parsed_payload = await request.json()
        return ExternalEvent(
            source=self.source,
            event_type=self.parsed_payload["type"],
            webhook_id="processor-cannot-authorize-this",
            payload=self.parsed_payload,
        )


class _Resolver:
    def __init__(
        self,
        resolution: ResolvedExternalWebhookContext | None,
    ) -> None:
        self.resolution = resolution
        self.calls: list[dict[str, Any]] = []

    async def resolve(
        self,
        request: Request,
        event: ExternalEvent,
        db: Any,
        db_read: Any,
    ) -> ResolvedExternalWebhookContext | None:
        self.calls.append(
            {
                "webhook_id": event.webhook_id,
                "header": request.headers.get("x-inbox-hint"),
                "state_hint": getattr(request.state, "inbox_hint", None),
                "payload": event.payload,
                "db": db,
                "db_read": db_read,
            }
        )
        return self.resolution


class _ContextFactory:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.db = object()
        self.db_read = object()
        self.messenger = object()
        self.cache_factory = object()

    async def create_context(
        self,
        inbox_id: str | None,
        user_id: str | None = None,
        *,
        include_messenger: bool = False,
        platform: PlatformType = PlatformType.WHATSAPP,
    ) -> WappaContext:
        self.calls.append(
            {
                "inbox_id": inbox_id,
                "user_id": user_id,
                "include_messenger": include_messenger,
                "platform": platform,
            }
        )
        return WappaContext(
            inbox_id=inbox_id,
            user_id=user_id,
            db=self.db,  # type: ignore[arg-type]
            db_read=self.db_read,  # type: ignore[arg-type]
            messenger=self.messenger if include_messenger else None,  # type: ignore[arg-type]
            cache_factory=self.cache_factory if user_id else None,  # type: ignore[arg-type]
        )


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
    context_resolver: _Resolver | None = None,
    dispatcher: ExternalEventDispatcher | None = None,
) -> ExternalWebhookRuntime:
    return ExternalWebhookRuntime(
        external_source="stripe",
        processor=processor,
        event_handler=handler,
        context_factory=context_factory or _ContextFactory(),
        context_resolver=context_resolver,
        dispatcher=dispatcher or ExternalEventDispatcher(),
    )


@pytest.mark.asyncio
async def test_unscoped_external_webhook_gets_database_only_context() -> None:
    processor = _Processor()
    handler = _RecordingHandler()
    context_factory = _ContextFactory()
    runtime = _runtime(processor, handler, context_factory=context_factory)

    admitted = await runtime.admit(
        _request_with_json({"type": "payment.approved"}), None
    )
    result = await runtime.dispatch(admitted)

    assert result.status == ExternalWebhookProcessStatus.ACCEPTED_DISPATCH
    assert result.webhook_id is None
    assert result.inbox_ref is None
    assert admitted.event.model_dump()["webhook_id"] is None
    assert handler.events == [admitted.event]
    assert handler.bound_contexts == [(None, None)]
    assert admitted.request_handler.inbox_id is None
    assert admitted.request_handler.user_id is None
    assert admitted.request_handler.db is context_factory.db
    assert admitted.request_handler.messenger is None
    assert context_factory.calls == [
        {
            "inbox_id": None,
            "user_id": None,
            "include_messenger": False,
            "platform": PlatformType.WHATSAPP,
        }
    ]


@pytest.mark.asyncio
async def test_resolver_uses_authenticated_request_evidence_for_context() -> None:
    processor = _Processor()
    handler = _RecordingHandler()
    context_factory = _ContextFactory()
    resolution = ResolvedExternalWebhookContext(
        inbox_ref=InboxRef.whatsapp("inbox-1"),
        user_id="user-1",
    )
    resolver = _Resolver(resolution)
    runtime = _runtime(
        processor,
        handler,
        context_factory=context_factory,
        context_resolver=resolver,
    )
    request = _request_with_json(
        {"type": "payment.approved"},
        headers={"x-inbox-hint": "header-inbox"},
    )
    request.state.inbox_hint = "middleware-inbox"

    admitted = await runtime.admit(request, "merchant-7")

    assert processor.webhook_ids == ["merchant-7"]
    assert admitted.event.webhook_id == "merchant-7"
    assert admitted.inbox_ref == InboxRef.whatsapp("inbox-1")
    assert admitted.request_handler.inbox_id == "inbox-1"
    assert admitted.request_handler.inbox_ref == InboxRef.whatsapp("inbox-1")
    assert admitted.request_handler.user_id == "user-1"
    assert admitted.request_handler.messenger is context_factory.messenger
    assert admitted.request_handler.cache_factory is context_factory.cache_factory
    assert resolver.calls == [
        {
            "webhook_id": "merchant-7",
            "header": "header-inbox",
            "state_hint": "middleware-inbox",
            "payload": {"type": "payment.approved"},
            "db": context_factory.db,
            "db_read": context_factory.db_read,
        }
    ]
    assert context_factory.calls[1] == {
        "inbox_id": "inbox-1",
        "user_id": "user-1",
        "include_messenger": True,
        "platform": PlatformType.WHATSAPP,
    }


@pytest.mark.asyncio
async def test_inbox_only_resolution_builds_messenger_without_user_cache() -> None:
    context_factory = _ContextFactory()
    resolver = _Resolver(
        ResolvedExternalWebhookContext(inbox_ref=InboxRef.whatsapp("inbox-1"))
    )
    runtime = _runtime(
        _Processor(),
        _RecordingHandler(),
        context_factory=context_factory,
        context_resolver=resolver,
    )

    admitted = await runtime.admit(_request_with_json({"type": "x"}), None)

    assert admitted.request_handler.inbox_id == "inbox-1"
    assert admitted.request_handler.user_id is None
    assert admitted.request_handler.messenger is context_factory.messenger
    assert admitted.request_handler.cache_factory is None


@pytest.mark.asyncio
async def test_route_webhook_id_overrides_processor_output() -> None:
    runtime = _runtime(_Processor(), _RecordingHandler())

    admitted = await runtime.admit(
        _request_with_json({"type": "payment.approved"}), "route-authority"
    )

    assert admitted.event.webhook_id == "route-authority"


def test_external_event_rejects_dispatch_context_fields() -> None:
    with pytest.raises(ValidationError):
        ExternalEvent(  # type: ignore[call-arg]
            source="stripe",
            event_type="payment.approved",
            inbox_id="not-event-data",
            user_id="not-event-data",
        )


def test_removed_include_inbox_id_option_fails_with_migration_message() -> None:
    with pytest.raises(TypeError, match="include_webhook_id"):
        WebhookPlugin(
            "stripe",
            processor=_Processor(),
            event_handler=_RecordingHandler(),
            include_inbox_id=True,
        )


@pytest.mark.asyncio
async def test_source_mismatch_fails_admission_before_resolution() -> None:
    processor = _Processor(source="wrong-source")
    resolver = _Resolver(None)
    runtime = _runtime(processor, _RecordingHandler(), context_resolver=resolver)

    with pytest.raises(ValueError, match="does not match"):
        await runtime.admit(_request_with_json({"type": "x"}), None)

    assert resolver.calls == []


@pytest.mark.asyncio
async def test_dispatch_failure_is_observable_after_admission() -> None:
    runtime = _runtime(
        _Processor(),
        _RecordingHandler(),
        dispatcher=_FailingDispatcher(),
    )
    admitted = await runtime.admit(_request_with_json({"type": "x"}), None)

    result = await runtime.dispatch(admitted)

    assert result.status == ExternalWebhookProcessStatus.DISPATCH_FAILURE
    assert result.error == "handler failed"


@pytest.mark.asyncio
async def test_clone_request_preserves_body_headers_and_state() -> None:
    request = _request_with_json({"type": "x"}, headers={"x-hint": "one"})
    request.state.inbox_hint = "two"
    body = await request.body()

    snapshot = clone_request_with_body(request, body)

    assert await snapshot.json() == {"type": "x"}
    assert snapshot.headers["x-hint"] == "one"
    assert snapshot.state.inbox_hint == "two"


class _FakeRuntime:
    def __init__(self, *, admission_error: Exception | None = None) -> None:
        self.admission_error = admission_error
        self.webhook_ids: list[str | None] = []

    async def admit(self, request: Request, webhook_id: str | None) -> object:
        self.webhook_ids.append(webhook_id)
        if self.admission_error is not None:
            raise self.admission_error
        await request.body()
        return object()

    async def dispatch(self, admitted: object) -> None:
        return None


class _Tracker:
    def __init__(self) -> None:
        self.names: list[str] = []

    def track(self, coroutine: Any, *, name: str) -> None:
        self.names.append(name)
        coroutine.close()


@pytest.mark.asyncio
async def test_plugins_choose_idless_or_identified_routes_independently() -> None:
    idless = WebhookPlugin(
        "stripe",
        processor=_Processor(),
        event_handler=_RecordingHandler(),
    )
    identified = WebhookPlugin(
        "github",
        processor=_Processor(source="github"),
        event_handler=_RecordingHandler(),
        include_webhook_id=True,
    )
    app = WappaBuilder().add_plugin(idless).add_plugin(identified).build()
    idless_runtime = _FakeRuntime()
    identified_runtime = _FakeRuntime()
    idless._runtime = idless_runtime  # type: ignore[assignment]
    identified._runtime = identified_runtime  # type: ignore[assignment]
    tracker = _Tracker()
    app.state.background_work_tracker = tracker

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        assert (await client.post("/webhook/stripe", json={"type": "x"})).json() == {
            "status": "accepted"
        }
        assert (
            await client.post("/webhook/github/install-9", json={"type": "x"})
        ).json() == {"status": "accepted"}
        assert (await client.post("/webhook/stripe/unexpected")).status_code == 404
        status = (await client.get("/webhook/github/status")).json()

    assert idless_runtime.webhook_ids == [None]
    assert identified_runtime.webhook_ids == ["install-9"]
    assert tracker.names == ["webhook:stripe:unscoped", "webhook:github:install-9"]
    assert status["webhook_url"].endswith("/webhook/github/{webhook_id}")
    assert status["uses_webhook_id"] is True


@pytest.mark.asyncio
async def test_admission_http_error_is_returned_and_not_scheduled() -> None:
    plugin = WebhookPlugin(
        "stripe",
        processor=_Processor(),
        event_handler=_RecordingHandler(),
    )
    app = WappaBuilder().add_plugin(plugin).build()
    plugin._runtime = _FakeRuntime(  # type: ignore[assignment]
        admission_error=HTTPException(401, "Invalid webhook signature")
    )
    tracker = _Tracker()
    app.state.background_work_tracker = tracker

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.post("/webhook/stripe", json={"type": "x"})

    assert response.status_code == 401
    assert tracker.names == []


@pytest.mark.asyncio
async def test_admission_validation_error_becomes_400_and_is_not_scheduled() -> None:
    plugin = WebhookPlugin(
        "stripe",
        processor=_Processor(),
        event_handler=_RecordingHandler(),
    )
    app = WappaBuilder().add_plugin(plugin).build()
    plugin._runtime = _FakeRuntime(  # type: ignore[assignment]
        admission_error=ValueError("bad payload")
    )
    tracker = _Tracker()
    app.state.background_work_tracker = tracker

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.post("/webhook/stripe", json={"type": "x"})

    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid external webhook"}
    assert tracker.names == []


def _request_with_json(
    payload: dict[str, Any],
    *,
    headers: dict[str, str] | None = None,
) -> Request:
    body = json.dumps(payload).encode()
    consumed = False

    async def receive() -> dict[str, object]:
        nonlocal consumed
        if consumed:
            return {"type": "http.request", "body": b"", "more_body": False}
        consumed = True
        return {"type": "http.request", "body": body, "more_body": False}

    encoded_headers = [(b"content-type", b"application/json")]
    encoded_headers.extend(
        (key.lower().encode(), value.encode()) for key, value in (headers or {}).items()
    )
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/webhook/stripe",
            "headers": encoded_headers,
            "query_string": b"",
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
            "scheme": "http",
            "app": FastAPI(),
            "state": {},
        },
        receive,
    )
