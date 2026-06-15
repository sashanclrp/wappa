from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from starlette.requests import Request

from wappa.api.routes.webhooks import create_webhook_router
from wappa.core.auth.middleware import AuthMiddleware
from wappa.core.auth.strategies.bearer_token import BearerTokenStrategy
from wappa.core.events.event_dispatcher import WappaEventDispatcher
from wappa.core.events.event_handler import WappaEventHandler
from wappa.core.events.webhook_factory import WebhookURLFactory
from wappa.core.plugins.auth_plugin import AuthPlugin
from wappa.domain.interfaces.inbox_credential_store import (
    IInboxCredentialStore,
    InboxCredentials,
    InboxNotFoundError,
)
from wappa.schemas.core.types import PlatformType
from wappa.webhooks import InboundMessageWebhook


class _NoopHandler(WappaEventHandler):
    async def process_message(self, webhook: InboundMessageWebhook) -> None:
        return None


class _SingleInboxCredentialStore(IInboxCredentialStore):
    def __init__(self, inbox_id: str) -> None:
        self.inbox_id = inbox_id

    async def get_credentials(self, inbox_id: str) -> InboxCredentials:
        if inbox_id != self.inbox_id:
            raise InboxNotFoundError(inbox_id)
        return InboxCredentials(
            inbox_id=inbox_id,
            access_token="test-token",
            platform_account_id="test-waba",
        )

    async def validate_inbox(self, inbox_id: str) -> bool:
        return inbox_id == self.inbox_id


class _NoopHTTPSession:
    async def post(self, *args: Any, **kwargs: Any) -> httpx.Response:
        return httpx.Response(200, json={})


@pytest.fixture
def authenticated_webhook_app() -> FastAPI:
    return _build_authenticated_webhook_app("123")


@pytest.mark.asyncio
async def test_auth_excludes_canonical_webhook_and_verify_only_routes(
    authenticated_webhook_app: FastAPI,
) -> None:
    async with _test_client(authenticated_webhook_app) as client:
        canonical_response = await client.post("/webhook/inboxes/123/whatsapp", json={})
        verify_response = await client.post(
            "/webhook/messenger/whatsapp/verify", json={}
        )

    assert canonical_response.status_code != 401
    assert verify_response.status_code == 405


def test_auth_skips_public_route_prefixes_from_builder() -> None:
    app = FastAPI()
    app.state.public_route_prefixes = ("/webhook", "/health")

    middleware = AuthMiddleware(
        app=lambda scope, receive, send: None,
        strategy=BearerTokenStrategy(token="api-token"),
        exclude=AuthPlugin.DEFAULT_EXCLUDES,
    )

    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/webhook/inboxes/123/whatsapp",
            "headers": [],
            "query_string": b"",
            "app": app,
        }
    )
    assert middleware._requires_auth("/webhook/inboxes/123/whatsapp", request) is False
    assert middleware._requires_auth("/health", request) is False
    assert middleware._requires_auth("/api/whatsapp/send", request) is True


@pytest.mark.asyncio
async def test_inbox_webhook_verification_bypasses_auth_and_returns_challenge(
    monkeypatch: pytest.MonkeyPatch,
    authenticated_webhook_app: FastAPI,
) -> None:
    monkeypatch.setattr(
        "wappa.api.controllers.webhook_controller.settings.wp_webhook_verify_token",
        "verify-token",
    )

    async with _test_client(authenticated_webhook_app) as client:
        response = await client.get(
            "/webhook/inboxes/123/whatsapp",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "verify-token",
                "hub.challenge": "abc",
            },
        )

    assert response.status_code == 200
    assert response.text == "abc"


@pytest.mark.asyncio
async def test_inbox_webhook_bad_verify_token_returns_forbidden_not_auth_failure(
    monkeypatch: pytest.MonkeyPatch,
    authenticated_webhook_app: FastAPI,
) -> None:
    monkeypatch.setattr(
        "wappa.api.controllers.webhook_controller.settings.wp_webhook_verify_token",
        "verify-token",
    )

    async with _test_client(authenticated_webhook_app) as client:
        response = await client.get(
            "/webhook/inboxes/123/whatsapp",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "wrong-token",
                "hub.challenge": "abc",
            },
        )

    assert response.status_code == 403
    assert "token mismatch" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_verify_endpoint_allows_only_get_method(
    authenticated_webhook_app: FastAPI,
) -> None:
    async with _test_client(authenticated_webhook_app) as client:
        post_response = await client.post("/webhook/messenger/whatsapp/verify", json={})
        get_response = await client.get(
            "/webhook/messenger/whatsapp/verify",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "any-token",
                "hub.challenge": "abc",
            },
        )

    assert post_response.status_code == 405
    assert get_response.status_code in {200, 403}


@pytest.mark.asyncio
async def test_platforms_contract_advertises_canonical_receiving_route(
    authenticated_webhook_app: FastAPI,
) -> None:
    async with _test_client(authenticated_webhook_app) as client:
        response = await client.get(
            "/webhook/platforms",
            headers={"Authorization": "Bearer api-token"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["webhook_pattern"] == "/webhook/inboxes/{inbox_id}/{platform}"
    assert data["verify_pattern"] == "/webhook/messenger/{platform}/verify"


def test_router_exposes_canonical_processing_and_verify_only_routes() -> None:
    app = _build_authenticated_webhook_app("123")

    verify_methods = _methods_for_path(
        app.routes, "/webhook/messenger/{platform}/verify"
    )
    canonical_methods = _methods_for_path(
        app.routes,
        "/webhook/inboxes/{inbox_id}/{platform}",
    )

    assert verify_methods == {"GET"}
    assert canonical_methods == {"GET", "POST"}


def test_webhook_url_factory_uses_canonical_inbox_processing_path() -> None:
    factory = WebhookURLFactory(base_url="https://example.test")

    webhook_url = factory.generate_webhook_url(PlatformType.WHATSAPP, "123")

    assert webhook_url == "https://example.test/webhook/inboxes/123/whatsapp"
    assert (
        factory.extract_platform_from_url("/webhook/inboxes/123/whatsapp")
        == PlatformType.WHATSAPP
    )
    assert factory.extract_inbox_from_url("/webhook/inboxes/123/whatsapp") == "123"
    assert factory.extract_platform_from_url("/webhook/messenger/123/whatsapp") is None
    assert factory.extract_inbox_from_url("/webhook/messenger/123/whatsapp") is None


def _build_authenticated_webhook_app(inbox_id: str) -> FastAPI:
    app = FastAPI()
    app.state.inbox_credential_store = _SingleInboxCredentialStore(inbox_id)
    app.state.http_session = _NoopHTTPSession()
    app.state.messenger_middleware = []
    app.state.wappa_cache_type = "memory"
    app.state.public_route_prefixes = ("/webhook",)
    app.add_middleware(
        AuthMiddleware,
        strategy=BearerTokenStrategy(token="api-token"),
        exclude=AuthPlugin.DEFAULT_EXCLUDES,
    )
    app.include_router(create_webhook_router(WappaEventDispatcher(_NoopHandler())))
    return app


def _methods_for_path(routes: Iterable[Any], path: str) -> set[str]:
    methods: set[str] = set()
    for route in routes:
        if getattr(route, "path", None) == path:
            methods.update(getattr(route, "methods", set()))
        router = getattr(route, "original_router", None)
        if router is not None:
            methods.update(_methods_for_path(router.routes, path))
    methods.discard("HEAD")
    methods.discard("OPTIONS")
    return methods


def _test_client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    )
