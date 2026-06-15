from __future__ import annotations

import httpx
import pytest
from fastapi import Depends, FastAPI

from wappa.core.plugins import RateLimitProfile, rate_limit
from wappa.core.plugins.rate_limit_plugin import LocalRateLimiter


@pytest.mark.asyncio
async def test_rate_limit_allows_requests_within_limit() -> None:
    app = await _app_with_route(
        "api", RateLimitProfile("api", limit=2, window_seconds=60)
    )

    async with _client(app) as client:
        first = await client.get("/items/inbox-1")
        second = await client.get("/items/inbox-1")

    assert first.status_code == 200
    assert second.status_code == 200


@pytest.mark.asyncio
async def test_rate_limit_rejects_requests_over_limit_with_retry_after() -> None:
    app = await _app_with_route(
        "api", RateLimitProfile("api", limit=1, window_seconds=60)
    )

    async with _client(app) as client:
        allowed = await client.get("/items/inbox-1")
        rejected = await client.get("/items/inbox-1")

    assert allowed.status_code == 200
    assert rejected.status_code == 429
    assert rejected.headers["retry-after"] == "60"


@pytest.mark.asyncio
async def test_rate_limit_unknown_profile_is_configuration_error() -> None:
    app = await _app_with_route(
        "missing", RateLimitProfile("api", limit=1, window_seconds=60)
    )

    async with _client(app) as client:
        with pytest.raises(RuntimeError, match="Unknown rate limit profile"):
            await client.get("/items/inbox-1")


@pytest.mark.asyncio
async def test_rate_limit_missing_plugin_is_configuration_error() -> None:
    app = FastAPI()

    @app.get("/items/{inbox_id}", dependencies=[Depends(rate_limit("api"))])
    async def endpoint(inbox_id: str) -> dict[str, str]:
        return {"inbox_id": inbox_id}

    async with _client(app) as client:
        with pytest.raises(RuntimeError, match="RateLimitPlugin is not configured"):
            await client.get("/items/inbox-1")


@pytest.mark.asyncio
async def test_rate_limit_can_key_by_inbox_id() -> None:
    app = await _app_with_route(
        "api",
        RateLimitProfile(
            "api",
            limit=1,
            window_seconds=60,
            key_by="inbox_id",
        ),
    )

    async with _client(app) as client:
        inbox_one = await client.get("/items/inbox-1")
        inbox_two = await client.get("/items/inbox-2")
        rejected = await client.get("/items/inbox-1")

    assert inbox_one.status_code == 200
    assert inbox_two.status_code == 200
    assert rejected.status_code == 429


@pytest.mark.asyncio
async def test_rate_limit_profiles_have_independent_windows() -> None:
    app = FastAPI()
    app.state.wappa_rate_limiter = LocalRateLimiter(
        [
            RateLimitProfile("one", limit=1, window_seconds=60),
            RateLimitProfile("two", limit=1, window_seconds=60),
        ]
    )

    @app.get("/one/{inbox_id}", dependencies=[Depends(rate_limit("one"))])
    async def one(inbox_id: str) -> dict[str, str]:
        return {"inbox_id": inbox_id}

    @app.get("/two/{inbox_id}", dependencies=[Depends(rate_limit("two"))])
    async def two(inbox_id: str) -> dict[str, str]:
        return {"inbox_id": inbox_id}

    async with _client(app) as client:
        one_allowed = await client.get("/one/inbox-1")
        two_allowed = await client.get("/two/inbox-1")
        one_rejected = await client.get("/one/inbox-1")
        two_rejected = await client.get("/two/inbox-1")

    assert one_allowed.status_code == 200
    assert two_allowed.status_code == 200
    assert one_rejected.status_code == 429
    assert two_rejected.status_code == 429


async def _app_with_route(profile_name: str, *profiles: RateLimitProfile) -> FastAPI:
    app = FastAPI()
    app.state.wappa_rate_limiter = LocalRateLimiter(list(profiles))

    @app.get("/items/{inbox_id}", dependencies=[Depends(rate_limit(profile_name))])
    async def endpoint(inbox_id: str) -> dict[str, str]:
        return {"inbox_id": inbox_id}

    return app


def _client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    )
