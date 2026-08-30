"""Tests for HTTP client lifecycle ownership and stale-session detection."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from wappa.domain.interfaces.session_provider import (
    HTTPSessionClosedError,
    validate_session,
)

# --- validate_session ---


def test_validate_session_open():
    session = MagicMock(spec=httpx.AsyncClient)
    session.is_closed = False
    result = validate_session(session)
    assert result is session


def test_validate_session_closed():
    session = MagicMock(spec=httpx.AsyncClient)
    session.is_closed = True
    with pytest.raises(HTTPSessionClosedError, match="HTTP session is closed"):
        validate_session(session)


# --- MessengerFactory ---


@pytest.fixture
def mock_credential_store():
    """A minimal IInboxCredentialResolver test double."""
    from pydantic import SecretStr

    from wappa.domain.inbox import (
        IInboxCredentialResolver,
        InboxRef,
        PlatformAccountRef,
        ResolvedInboxCredentials,
    )

    class _Resolver(IInboxCredentialResolver):
        async def resolve_credentials(self, inbox_ref: InboxRef):
            return ResolvedInboxCredentials(
                inbox_ref=inbox_ref,
                account_ref=PlatformAccountRef.whatsapp("waba"),
                access_token=SecretStr("test-token"),
                credential_version=1,
            )

        async def list_inbox_refs_for_platform_account(self, account_ref):
            return ()

    return _Resolver()


@pytest.fixture
def open_session():
    session = MagicMock(spec=httpx.AsyncClient)
    session.is_closed = False
    return session


@pytest.fixture
def closed_session():
    session = MagicMock(spec=httpx.AsyncClient)
    session.is_closed = True
    return session


class TestMessengerFactorySessionGuard:
    def test_provider_raises_propagates(self, closed_session):
        from wappa.domain.factories.messenger_factory import MessengerFactory

        def bad_provider():
            raise HTTPSessionClosedError("session closed")

        factory = MessengerFactory(
            session_provider=bad_provider,
            media_download_client_provider=bad_provider,
        )
        with pytest.raises(HTTPSessionClosedError):
            factory._get_session()

    def test_provider_returns_session(self, open_session):
        from wappa.domain.factories.messenger_factory import MessengerFactory

        factory = MessengerFactory(
            session_provider=lambda: open_session,
            media_download_client_provider=lambda: open_session,
        )
        result = factory._get_session()
        assert result is open_session

    @pytest.mark.asyncio
    async def test_create_messenger_closed_session_raises(
        self, closed_session, mock_credential_store
    ):
        from wappa.domain.factories.messenger_factory import MessengerFactory
        from wappa.domain.inbox import InboxRef

        def bad_provider():
            raise HTTPSessionClosedError("session closed")

        factory = MessengerFactory(
            session_provider=bad_provider,
            media_download_client_provider=bad_provider,
            credential_resolver=mock_credential_store,
        )
        with pytest.raises(RuntimeError, match="Messenger creation failed"):
            await factory.create_messenger(InboxRef.whatsapp("12345"))

    @pytest.mark.asyncio
    async def test_cached_messenger_evicted_when_session_closes(
        self, open_session, mock_credential_store
    ):
        from wappa.domain.factories.messenger_factory import MessengerFactory
        from wappa.domain.inbox import InboxRef

        factory = MessengerFactory(
            session_provider=lambda: open_session,
            media_download_client_provider=lambda: open_session,
            credential_resolver=mock_credential_store,
        )

        await factory.create_messenger(InboxRef.whatsapp("12345"))
        assert "whatsapp:12345" in factory._messenger_cache

        # Provider now raises — next access should evict + fail
        factory._session_provider = lambda: (_ for _ in ()).throw(
            HTTPSessionClosedError("closed")
        )
        with pytest.raises(RuntimeError, match="Messenger creation failed"):
            await factory.create_messenger(InboxRef.whatsapp("12345"))

        assert "whatsapp:12345" not in factory._messenger_cache


# --- Expiry context helpers ---


class TestExpiryMessengerSessionGuard:
    @pytest.mark.asyncio
    async def test_no_lifecycle_raises_http_not_available(self):
        from wappa.core.expiry.context_helpers import (
            SessionLifecycleNotAvailableError,
            create_expiry_messenger,
        )

        mock_app = MagicMock()
        mock_app.state.session_lifecycle = None

        mock_context = MagicMock()
        mock_context.get_app.return_value = mock_app

        with (
            patch(
                "wappa.core.expiry.context_helpers.get_app_context",
                return_value=mock_context,
            ),
            pytest.raises(
                SessionLifecycleNotAvailableError,
                match="SessionLifecycle not available",
            ),
        ):
            await create_expiry_messenger("12345")

    @pytest.mark.asyncio
    async def test_draining_lifecycle_raises_messenger_error(self):
        from wappa.core.expiry.context_helpers import (
            MessengerCreationError,
            create_expiry_messenger,
        )
        from wappa.core.lifecycle import SessionLifecycle

        client = SessionLifecycle._default_client_factory()
        lifecycle = SessionLifecycle(client)
        lifecycle.begin_drain()

        mock_app = MagicMock()
        mock_app.state.session_lifecycle = lifecycle

        mock_context = MagicMock()
        mock_context.get_app.return_value = mock_app

        with (
            patch(
                "wappa.core.expiry.context_helpers.get_app_context",
                return_value=mock_context,
            ),
            pytest.raises(MessengerCreationError),
        ):
            await create_expiry_messenger("12345")

        await client.aclose()


# --- WappaContextFactory ---


class TestContextFactorySessionGuard:
    @pytest.mark.asyncio
    async def test_returns_none_when_no_session_lifecycle(self):
        from types import SimpleNamespace

        from wappa.core.context import WappaContextFactory

        mock_app = SimpleNamespace(state=SimpleNamespace(session_lifecycle=None))

        factory = WappaContextFactory(app=mock_app)  # type: ignore[arg-type]
        context = await factory.create_context(
            inbox_id="12345", user_id="user1", include_messenger=True
        )
        assert context.messenger is None
        assert context.cache_factory is None


# --- WappaCorePlugin session recreation ---


class TestSessionRecreation:
    def _make_plugin_with_lifecycle(self, old_session: httpx.AsyncClient):
        """Return a WappaCorePlugin pre-wired with a SessionLifecycle (simulates post-startup)."""
        from wappa.core.lifecycle import SessionLifecycle
        from wappa.core.plugins.wappa_core_plugin import WappaCorePlugin
        from wappa.core.types import CacheType

        plugin = WappaCorePlugin(cache_type=CacheType.MEMORY)
        plugin._session_lifecycle = SessionLifecycle(old_session)
        return plugin

    @pytest.mark.asyncio
    async def test_recreate_replaces_session(self):
        from wappa.core.lifecycle import SessionLifecycle

        old_session = SessionLifecycle._default_client_factory()
        await old_session.aclose()
        assert old_session.is_closed

        plugin = self._make_plugin_with_lifecycle(old_session)
        await plugin.recreate_http_session()

        new_session = plugin._session_lifecycle.get_session()
        assert isinstance(new_session, httpx.AsyncClient)
        assert not new_session.is_closed
        assert new_session is not old_session

        await new_session.aclose()

    @pytest.mark.asyncio
    async def test_recreate_before_startup_raises(self):
        from wappa.core.plugins.wappa_core_plugin import WappaCorePlugin
        from wappa.core.types import CacheType

        plugin = WappaCorePlugin(cache_type=CacheType.MEMORY)
        with pytest.raises(RuntimeError, match="called before startup"):
            await plugin.recreate_http_session()

    @pytest.mark.asyncio
    async def test_recreate_handles_already_closed(self):
        from wappa.core.lifecycle import SessionLifecycle

        old_session = SessionLifecycle._default_client_factory()
        await old_session.aclose()

        plugin = self._make_plugin_with_lifecycle(old_session)
        await plugin.recreate_http_session()

        new_session = plugin._session_lifecycle.get_session()
        assert isinstance(new_session, httpx.AsyncClient)
        assert not new_session.is_closed

        await new_session.aclose()
