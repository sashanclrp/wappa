"""Cron monitoring routes remain visible when populated during lifespan startup."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import APIRouter, Depends
from fastapi.routing import iter_route_contexts
from fastapi.testclient import TestClient

from wappa.core.auth.middleware import AuthMiddleware
from wappa.core.auth.strategies.bearer_token import BearerTokenStrategy
from wappa.core.factory.wappa_builder import WappaBuilder
from wappa.core.plugins.scheduling_plugin import SchedulingPlugin


@pytest.mark.parametrize("include_router", [True, False])
def test_cron_startup_routes_preserve_auth_dependencies_and_openapi(
    monkeypatch: pytest.MonkeyPatch, include_router: bool
) -> None:
    scheduler = MagicMock(start=AsyncMock(), stop=AsyncMock())
    monkeypatch.setattr("fastapi_crons.Crons", MagicMock(return_value=scheduler))
    calls: list[str] = []

    async def record_request() -> None:
        calls.append("monitor")

    source = APIRouter(dependencies=[Depends(record_request)])
    nested = APIRouter(prefix="/monitor")

    @nested.get("/status", tags=["Monitor"])
    async def status() -> dict[str, bool]:
        return {"running": True}

    source.include_router(nested)
    get_router = MagicMock(return_value=source)
    monkeypatch.setattr("fastapi_crons.get_cron_router", get_router)

    plugin = SchedulingPlugin(
        event_handler=MagicMock(), include_cron_router=include_router
    ).add_cron("report", "0 9 * * *")
    builder = WappaBuilder().add_plugin(plugin)
    builder.add_middleware(AuthMiddleware, strategy=BearerTokenStrategy(token="secret"))
    app = builder.build()
    path = "/crons/monitor/status"
    assert path not in {context.path for context in iter_route_contexts(app.routes)}

    with TestClient(app) as client:
        response = client.get(path, headers={"Authorization": "Bearer secret"})
        if include_router:
            assert response.status_code == 200
            assert response.json() == {"running": True}
            assert client.get(path).status_code == 401
            assert app.openapi()["paths"][path]["get"]["tags"] == [
                "Cron Jobs",
                "Monitor",
            ]
            assert calls == ["monitor"]
            get_router.assert_called_once_with()
        else:
            assert response.status_code == 404
            assert path not in app.openapi()["paths"]
            assert calls == []
            get_router.assert_not_called()

    scheduler.start.assert_awaited_once_with()
    scheduler.stop.assert_awaited_once_with()
