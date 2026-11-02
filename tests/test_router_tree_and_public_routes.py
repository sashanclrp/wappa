"""Tests for FastAPI 0.137+ router-tree integration and public route prefixes."""

from __future__ import annotations

import httpx
import pytest
from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.routing import iter_route_contexts

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


def test_public_prefix_combines_include_and_router_prefixes() -> None:
    builder = WappaBuilder()
    router = APIRouter(prefix="/internal")
    builder.add_router(router, prefix="/external", public=True)

    assert builder._public_prefixes == ["/external/internal"]
    assert "/internal" not in builder._public_prefixes


@pytest.mark.asyncio
async def test_public_mount_does_not_exempt_protected_siblings() -> None:
    builder = WappaBuilder()
    router = APIRouter(prefix="/hooks")

    @router.get("/ping")
    async def ping() -> dict[str, bool]:
        return {"ok": True}

    builder.add_router(router, prefix="/public", public=True)
    builder.add_router(router, prefix="/private")
    builder.add_middleware(AuthMiddleware, strategy=BearerTokenStrategy(token="secret"))
    app = builder.build()

    @app.get("/public/admin")
    @app.get("/public/hooks-admin")
    async def admin() -> dict[str, bool]:
        return {"ok": True}

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        assert (await client.get("/public/hooks/ping")).status_code == 200
        for path in ("/private/hooks/ping", "/public/admin", "/public/hooks-admin"):
            assert (await client.get(path)).status_code == 401
            assert (
                await client.get(path, headers={"Authorization": "Bearer secret"})
            ).status_code == 200


def test_route_contexts_preserve_nested_mount_metadata_and_dependencies() -> None:
    """The public iterator describes each inclusion of a shared router."""
    app = FastAPI()
    calls: list[str] = []

    async def authorize(request: Request) -> None:
        calls.append(request.url.path)

    leaf = APIRouter(prefix="/items")

    @leaf.get("/{item_id}")
    async def item(item_id: str) -> dict[str, str]:
        return {"id": item_id}

    parent = APIRouter(prefix="/v1")
    parent.include_router(leaf, tags=["Items"])
    app.include_router(parent, prefix="/public", include_in_schema=False)
    app.include_router(
        parent, prefix="/private", dependencies=[Depends(authorize)], tags=["Private"]
    )

    contexts = {
        context.path: context
        for context in iter_route_contexts(app.routes)
        if context.endpoint is item
    }
    assert set(contexts) == {
        "/public/v1/items/{item_id}",
        "/private/v1/items/{item_id}",
    }
    assert contexts["/public/v1/items/{item_id}"].include_in_schema is False
    assert contexts["/private/v1/items/{item_id}"].tags == ["Private", "Items"]
    paths = app.openapi()["paths"]
    assert "/public/v1/items/{item_id}" not in paths
    assert paths["/private/v1/items/{item_id}"]["get"]["tags"] == ["Private", "Items"]

    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        assert client.get("/public/v1/items/1").json() == {"id": "1"}
        assert client.get("/private/v1/items/2").json() == {"id": "2"}
    assert calls == ["/private/v1/items/2"]


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
