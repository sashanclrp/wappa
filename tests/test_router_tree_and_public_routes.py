"""Tests for FastAPI 0.137+ router-tree integration and public route prefixes."""

from __future__ import annotations

import httpx
import pytest
from fastapi import APIRouter, FastAPI

from wappa.core.auth.middleware import AuthMiddleware
from wappa.core.auth.strategies.bearer_token import BearerTokenStrategy
from wappa.core.factory.wappa_builder import WappaBuilder


def test_builder_tracks_public_prefixes() -> None:
    builder = WappaBuilder()
    r1 = APIRouter(prefix="/health")
    r2 = APIRouter(prefix="/webhook")
    r3 = APIRouter(prefix="/api")

    builder.add_router(r1, public=True)
    builder.add_router(r2, public=True)
    builder.add_router(r3)

    assert "/health" in builder._public_prefixes
    assert "/webhook" in builder._public_prefixes
    assert "/api" not in builder._public_prefixes


def test_build_exposes_public_prefixes_on_app_state() -> None:
    builder = WappaBuilder()
    builder.add_router(APIRouter(prefix="/health"), public=True)
    builder.add_router(APIRouter(prefix="/webhook"), public=True)

    app = builder.build()

    assert "/health" in app.state.public_route_prefixes
    assert "/webhook" in app.state.public_route_prefixes


def test_public_prefix_from_kwargs_overrides_router_attr() -> None:
    builder = WappaBuilder()
    router = APIRouter(prefix="/internal")
    builder.add_router(router, prefix="/external", public=True)

    assert "/external" in builder._public_prefixes
    assert "/internal" not in builder._public_prefixes


@pytest.mark.asyncio
async def test_auth_middleware_skips_public_route_prefixes() -> None:
    app = FastAPI()
    app.state.public_route_prefixes = ("/webhook", "/health")

    public_router = APIRouter(prefix="/webhook")

    @public_router.get("/test")
    async def public_endpoint() -> dict[str, str]:
        return {"auth": "not_required"}

    protected_router = APIRouter(prefix="/api")

    @protected_router.get("/data")
    async def protected_endpoint() -> dict[str, str]:
        return {"auth": "required"}

    app.add_middleware(
        AuthMiddleware,
        strategy=BearerTokenStrategy(token="secret"),
    )
    app.include_router(public_router)
    app.include_router(protected_router)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        public_resp = await client.get("/webhook/test")
        protected_resp = await client.get("/api/data")
        authed_resp = await client.get(
            "/api/data", headers={"Authorization": "Bearer secret"}
        )

    assert public_resp.status_code == 200
    assert protected_resp.status_code == 401
    assert authed_resp.status_code == 200


def test_lazy_route_registration_with_router_tree() -> None:
    """Routes added to a router AFTER include_router are routable in 0.137+."""
    app = FastAPI()
    router = APIRouter(prefix="/lazy")
    app.include_router(router)

    @router.get("/endpoint")
    async def lazy_endpoint() -> dict[str, str]:
        return {"lazy": "true"}

    from fastapi.testclient import TestClient

    client = TestClient(app)
    resp = client.get("/lazy/endpoint")
    assert resp.status_code == 200
    assert resp.json() == {"lazy": "true"}


def test_builder_routes_all_go_through_builder() -> None:
    """All routers registered through the builder are included in the app."""
    builder = WappaBuilder()

    r1 = APIRouter(prefix="/a")

    @r1.get("/ping")
    async def ping_a() -> dict[str, str]:
        return {"router": "a"}

    r2 = APIRouter(prefix="/b")

    @r2.get("/ping")
    async def ping_b() -> dict[str, str]:
        return {"router": "b"}

    builder.add_router(r1, public=True)
    builder.add_router(r2)

    app = builder.build()

    from fastapi.testclient import TestClient

    client = TestClient(app)
    assert client.get("/a/ping").json() == {"router": "a"}
    assert client.get("/b/ping").json() == {"router": "b"}


@pytest.mark.asyncio
async def test_webhook_plugin_router_marked_public() -> None:
    """WebhookPlugin registers its router as public (excluded from auth)."""
    from unittest.mock import MagicMock

    from wappa.core.plugins.webhook_plugin import WebhookPlugin

    builder = WappaBuilder()
    mock_processor = MagicMock()
    mock_processor.get_source_name.return_value = "stripe"
    mock_handler = MagicMock()

    plugin = WebhookPlugin(
        "stripe",
        processor=mock_processor,
        event_handler=mock_handler,
    )
    plugin.configure(builder)

    assert "/webhook/stripe" in builder._public_prefixes
