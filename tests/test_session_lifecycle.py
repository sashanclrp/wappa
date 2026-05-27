"""Tests for SessionLifecycle — unified session acquisition with drain awareness."""

import asyncio

import httpx
import pytest

from wappa.core.lifecycle import RuntimeDrainingError, SessionLifecycle
from wappa.domain.interfaces.session_provider import HTTPSessionClosedError


@pytest.fixture
def live_session():
    transport = httpx.AsyncHTTPTransport(
        limits=httpx.Limits(max_connections=1, max_keepalive_connections=1),
    )
    client = httpx.AsyncClient(transport=transport, timeout=httpx.Timeout(5.0))
    yield client
    if not client.is_closed:
        asyncio.get_event_loop().run_until_complete(client.aclose())


@pytest.fixture
def closed_session(live_session):
    asyncio.get_event_loop().run_until_complete(live_session.aclose())
    return live_session


class TestSessionLifecycle:
    def test_get_session_returns_live_session(self, live_session):
        lifecycle = SessionLifecycle(live_session)
        assert lifecycle.get_session() is live_session

    def test_get_session_raises_when_draining(self, live_session):
        lifecycle = SessionLifecycle(live_session)
        lifecycle.begin_drain()
        with pytest.raises(RuntimeDrainingError, match="draining"):
            lifecycle.get_session()

    def test_get_session_raises_when_closed(self, closed_session):
        lifecycle = SessionLifecycle(closed_session)
        with pytest.raises(HTTPSessionClosedError):
            lifecycle.get_session()

    def test_is_draining_reflects_state(self, live_session):
        lifecycle = SessionLifecycle(live_session)
        assert not lifecycle.is_draining
        lifecycle.begin_drain()
        assert lifecycle.is_draining

    @pytest.mark.asyncio
    async def test_recreate_produces_new_session(self):
        old = SessionLifecycle._default_client_factory()
        lifecycle = SessionLifecycle(old)

        await old.aclose()
        assert old.is_closed

        new = await lifecycle.recreate()
        assert not new.is_closed
        assert new is not old
        assert lifecycle.get_session() is new
        await new.aclose()

    @pytest.mark.asyncio
    async def test_recreate_raises_when_draining(self, live_session):
        lifecycle = SessionLifecycle(live_session)
        lifecycle.begin_drain()
        with pytest.raises(RuntimeDrainingError):
            await lifecycle.recreate()

    @pytest.mark.asyncio
    async def test_recreate_serializes_concurrent_calls(self):
        old = SessionLifecycle._default_client_factory()
        lifecycle = SessionLifecycle(old)
        await old.aclose()

        results = await asyncio.gather(
            lifecycle.recreate(),
            lifecycle.recreate(),
            lifecycle.recreate(),
        )
        # All callers should get the same session
        assert results[0] is results[1] is results[2]
        assert not results[0].is_closed
        await results[0].aclose()

    @pytest.mark.asyncio
    async def test_close_shuts_down_session(self):
        client = SessionLifecycle._default_client_factory()
        lifecycle = SessionLifecycle(client)
        await lifecycle.close()
        assert client.is_closed
        assert lifecycle.session is None

    def test_session_property_for_backward_compat(self, live_session):
        lifecycle = SessionLifecycle(live_session)
        assert lifecycle.session is live_session
