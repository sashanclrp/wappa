"""HTTP contract of the canonical WhatsApp callback route (PRDs 3 and 5)."""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from pydantic import SecretStr
from starlette.requests import Request

from wappa.api.routes.webhooks import create_webhook_router
from wappa.core.auth.middleware import AuthMiddleware
from wappa.core.auth.strategies.bearer_token import BearerTokenStrategy
from wappa.core.config.meta_application import MetaApplicationConfig
from wappa.core.events.event_dispatcher import WappaEventDispatcher
from wappa.core.events.event_handler import WappaEventHandler
from wappa.core.events.webhook_factory import WebhookURLFactory
from wappa.core.factory.inbox_assembly import InboxRuntimeConfiguration
from wappa.core.inbound import SIGNATURE_HEADER, MetaCallbackAuthenticator
from wappa.core.lifecycle import BackgroundWorkTracker, SessionLifecycle
from wappa.core.plugins.auth_plugin import AuthPlugin
from wappa.domain.inbox import (
    InboxRef,
    InboxRoutingMode,
    PlatformAccountRef,
    SettingsInboxCredentialResolver,
)
from wappa.schemas.core.types import PlatformType
from wappa.webhooks import InboundMessageWebhook

APP_SECRET = SecretStr("app-secret")
VERIFY_TOKEN = "verify-token"


class _NoopHandler(WappaEventHandler):
    async def process_message(self, webhook: InboundMessageWebhook) -> None:
        return None


def _resolver(inbox_id: str = "123") -> SettingsInboxCredentialResolver:
    return SettingsInboxCredentialResolver(
        access_token=SecretStr("test-token"),
        phone_number_id=inbox_id,
        business_account_id="1111111111",
    )


def _build_app(inbox_id: str = "123") -> FastAPI:
    app = FastAPI()
    resolver = _resolver(inbox_id)
    app.state.inbox_runtime = InboxRuntimeConfiguration(
        mode=InboxRoutingMode.LEGACY,
        credential_resolver=resolver,
        default_inbox_ref=resolver.inbox_ref,
    )
    app.state.meta_application_config = MetaApplicationConfig(
        app_secret=APP_SECRET, whatsapp_webhook_verify_token=SecretStr(VERIFY_TOKEN)
    )
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


def _client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    )


def _signed_headers(body: bytes) -> dict[str, str]:
    return {
        SIGNATURE_HEADER: MetaCallbackAuthenticator(APP_SECRET).sign(body),
        "Content-Type": "application/json",
    }


def _message_payload(inbox_id: str = "123") -> dict[str, Any]:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "1111111111",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "15551234567",
                                "phone_number_id": inbox_id,
                            },
                            "contacts": [
                                {
                                    "wa_id": "573001234567",
                                    "profile": {"name": "Webhook User"},
                                }
                            ],
                            "messages": [
                                {
                                    "from": "573001234567",
                                    "id": "wamid.canonical",
                                    "timestamp": "1710000000",
                                    "type": "text",
                                    "text": {"body": "hello"},
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }


@pytest.fixture
def app() -> FastAPI:
    return _build_app()


async def test_auth_excludes_canonical_webhook_route(app: FastAPI) -> None:
    async with _client(app) as client:
        response = await client.get("/webhook/inboxes/whatsapp")
    assert response.status_code != 401


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
            "path": "/webhook/inboxes/whatsapp",
            "headers": [],
            "query_string": b"",
            "app": app,
        }
    )
    assert middleware._requires_auth("/webhook/inboxes/whatsapp", request) is False
    assert middleware._requires_auth("/health", request) is False
    assert middleware._requires_auth("/api/whatsapp/send", request) is True


async def test_get_verification_uses_the_verify_token_and_returns_the_challenge(
    app: FastAPI,
) -> None:
    async with _client(app) as client:
        response = await client.get(
            "/webhook/inboxes/whatsapp",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": VERIFY_TOKEN,
                "hub.challenge": "abc",
            },
        )
    assert response.status_code == 200
    assert response.text == "abc"


async def test_get_verification_rejects_the_app_secret_and_wrong_tokens(
    app: FastAPI,
) -> None:
    async with _client(app) as client:
        wrong = await client.get(
            "/webhook/inboxes/whatsapp",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "wrong-token",
                "hub.challenge": "abc",
            },
        )
        secret_as_token = await client.get(
            "/webhook/inboxes/whatsapp",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": APP_SECRET.get_secret_value(),
                "hub.challenge": "abc",
            },
        )
    assert wrong.status_code == 403
    assert secret_as_token.status_code == 403


async def test_get_verification_does_not_read_the_directory(app: FastAPI) -> None:
    class _Exploding:
        async def resolve_credentials(self, inbox_ref: InboxRef) -> Any:
            raise AssertionError("GET verification must not resolve an Inbox")

        async def list_inbox_refs_for_platform_account(
            self, account_ref: PlatformAccountRef
        ) -> Any:
            raise AssertionError("GET verification must not read the directory")

        def subscribe_evictions(self, listener: Any) -> None:
            return None

    app.state.inbox_runtime = InboxRuntimeConfiguration(
        mode=InboxRoutingMode.EXPLICIT,
        credential_resolver=_Exploding(),  # type: ignore[arg-type]
    )
    async with _client(app) as client:
        response = await client.get(
            "/webhook/inboxes/whatsapp",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": VERIFY_TOKEN,
                "hub.challenge": "ok",
            },
        )
    assert response.status_code == 200


async def test_platforms_contract_advertises_canonical_receiving_route(
    app: FastAPI,
) -> None:
    async with _client(app) as client:
        response = await client.get(
            "/webhook/platforms", headers={"Authorization": "Bearer api-token"}
        )
    assert response.status_code == 200
    assert response.json()["webhook_pattern"] == "/webhook/inboxes/{platform}"


def test_router_exposes_canonical_processing_and_verify_only_routes() -> None:
    assert _methods_for_path(_build_app().routes, "/webhook/inboxes/{platform}") == {
        "GET",
        "POST",
    }


def test_webhook_url_factory_is_safe_without_environment_inbox(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("wappa.core.events.webhook_factory.settings.wp_phone_id", None)
    factory = WebhookURLFactory(base_url="https://example.test")
    assert (
        factory.generate_webhook_url(PlatformType.WHATSAPP)
        == "https://example.test/webhook/inboxes/whatsapp"
    )
    assert (
        factory.extract_platform_from_url("/webhook/inboxes/whatsapp")
        == PlatformType.WHATSAPP
    )
    assert factory.extract_platform_from_url("/webhook/inboxes/123/whatsapp") is None


async def test_removed_per_inbox_webhook_route_returns_not_found(app: FastAPI) -> None:
    async with _client(app) as client:
        get_response = await client.get("/webhook/inboxes/123/whatsapp")
        post_response = await client.post("/webhook/inboxes/123/whatsapp", json={})
        verify_only = await client.get("/webhook/messenger/whatsapp/verify")
    assert (
        get_response.status_code,
        post_response.status_code,
        verify_only.status_code,
    ) == (404, 404, 404)


async def test_canonical_post_requires_a_valid_meta_signature(app: FastAPI) -> None:
    body = json.dumps(_message_payload()).encode()
    async with _client(app) as client:
        unsigned = await client.post(
            "/webhook/inboxes/whatsapp",
            content=body,
            headers={"Content-Type": "application/json"},
        )
        bad = await client.post(
            "/webhook/inboxes/whatsapp",
            content=body,
            headers={
                "Content-Type": "application/json",
                SIGNATURE_HEADER: "sha256=" + "0" * 64,
            },
        )
        tampered = await client.post(
            "/webhook/inboxes/whatsapp",
            content=body + b" ",
            headers=_signed_headers(body),
        )
    assert unsigned.status_code == 401
    assert bad.status_code == 401
    assert tampered.status_code == 401
    assert (
        unsigned.json() == bad.json() == tampered.json() == {"detail": "Unauthorized"}
    )


async def test_canonical_post_routes_from_payload_and_returns_accepted() -> None:
    app = _build_app()
    provider_client = httpx.AsyncClient()
    app.state.session_lifecycle = SessionLifecycle(provider_client)
    app.state.background_work_tracker = BackgroundWorkTracker()
    body = json.dumps(_message_payload()).encode()

    try:
        async with _client(app) as client:
            response = await client.post(
                "/webhook/inboxes/whatsapp", content=body, headers=_signed_headers(body)
            )
        await app.state.background_work_tracker.drain(timeout=1)
    finally:
        await app.state.session_lifecycle.close()

    assert response.status_code == 200
    assert response.json() == {"status": "accepted"}


async def test_exact_body_bytes_are_authenticated_before_parsing(app: FastAPI) -> None:
    """Whitespace changes the HMAC input; a signature over other bytes fails."""
    body = json.dumps(_message_payload(), indent=2).encode()
    app.state.session_lifecycle = SessionLifecycle(httpx.AsyncClient())
    app.state.background_work_tracker = BackgroundWorkTracker()
    try:
        async with _client(app) as client:
            ok = await client.post(
                "/webhook/inboxes/whatsapp", content=body, headers=_signed_headers(body)
            )
            mismatch = await client.post(
                "/webhook/inboxes/whatsapp",
                content=body,
                headers=_signed_headers(json.dumps(_message_payload()).encode()),
            )
        await app.state.background_work_tracker.drain(timeout=1)
    finally:
        await app.state.session_lifecycle.close()
    assert ok.status_code == 200
    assert mismatch.status_code == 401


@pytest.mark.parametrize("body", [b"[]", b"null", b'"x"', b"7", b"false"])
async def test_authenticated_non_object_roots_are_400(
    app: FastAPI, body: bytes
) -> None:
    async with _client(app) as client:
        response = await client.post(
            "/webhook/inboxes/whatsapp", content=body, headers=_signed_headers(body)
        )
    assert response.status_code == 400


async def test_authenticated_unknown_inbox_is_400(app: FastAPI) -> None:
    app.state.session_lifecycle = SessionLifecycle(httpx.AsyncClient())
    app.state.background_work_tracker = BackgroundWorkTracker()
    body = json.dumps(_message_payload("999")).encode()
    try:
        async with _client(app) as client:
            response = await client.post(
                "/webhook/inboxes/whatsapp", content=body, headers=_signed_headers(body)
            )
    finally:
        await app.state.session_lifecycle.close()
    assert response.status_code == 400


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
