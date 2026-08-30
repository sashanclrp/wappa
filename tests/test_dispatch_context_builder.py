"""One Dispatch Context builder across webhook, API, cron, and external paths (PRD 5)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import SecretStr

from wappa.core.context import WappaContextFactory
from wappa.core.dispatch import DispatchContextBuilder, RuntimeCapabilities
from wappa.core.events.api_event_dispatcher import APIEventDispatcher
from wappa.core.events.event_handler import WappaEventHandler
from wappa.core.factory.inbox_assembly import InboxRuntimeConfiguration
from wappa.core.lifecycle import BackgroundWorkTracker, SessionLifecycle
from wappa.domain.events.api_message_event import APIMessageEvent
from wappa.domain.inbox import (
    IInboxCredentialResolver,
    InboxDirectoryUnavailableError,
    InboxRef,
    InboxRoutingMode,
    PlatformAccountRef,
    ResolvedInboxCredentials,
)
from wappa.webhooks import InboundMessageWebhook


class _Resolver(IInboxCredentialResolver):
    def __init__(self) -> None:
        self.unavailable = False
        self.listeners: list[Any] = []

    async def resolve_credentials(
        self, inbox_ref: InboxRef
    ) -> ResolvedInboxCredentials:
        if self.unavailable:
            raise InboxDirectoryUnavailableError("down")
        return ResolvedInboxCredentials(
            inbox_ref=inbox_ref,
            account_ref=PlatformAccountRef.whatsapp("waba"),
            access_token=SecretStr("token"),
            credential_version=1,
        )

    async def list_inbox_refs_for_platform_account(
        self, account_ref: PlatformAccountRef
    ) -> tuple[InboxRef, ...]:
        return ()

    def subscribe_evictions(self, listener: Any) -> None:
        self.listeners.append(listener)


class _Handler(WappaEventHandler):
    async def process_message(self, webhook: InboundMessageWebhook) -> None:
        return None

    async def process_api_message(self, event: APIMessageEvent) -> None:
        self.seen_db = self.db  # type: ignore[attr-defined]


class _SessionManager:
    @asynccontextmanager
    async def get_session(self):  # type: ignore[no-untyped-def]
        yield "primary-session"

    @asynccontextmanager
    async def get_read_session(self):  # type: ignore[no-untyped-def]
        yield "read-session"


class _Session:
    is_closed = False


def _capabilities(resolver: _Resolver, *, db: bool = False) -> RuntimeCapabilities:
    return RuntimeCapabilities(
        session_provider=lambda: _Session(),  # type: ignore[arg-type,return-value]
        media_download_client_provider=lambda: _Session(),  # type: ignore[arg-type,return-value]
        credential_resolver=resolver,
        messenger_middleware=[],
        cache_type="memory",
        background_work_tracker=BackgroundWorkTracker(),
        postgres_session_manager=_SessionManager() if db else None,
    )


def _app(resolver: _Resolver, *, db: bool = False) -> Any:
    return SimpleNamespace(
        state=SimpleNamespace(
            session_lifecycle=SessionLifecycle(_Session()),  # type: ignore[arg-type]
            inbox_runtime=InboxRuntimeConfiguration(
                mode=InboxRoutingMode.EXPLICIT, credential_resolver=resolver
            ),
            messenger_middleware=[],
            wappa_cache_type="memory",
            background_work_tracker=BackgroundWorkTracker(),
            postgres_session_manager=_SessionManager() if db else None,
        )
    )


async def test_builder_binds_messenger_cache_and_optional_db() -> None:
    builder = DispatchContextBuilder(_capabilities(_Resolver(), db=True))
    ref = InboxRef.whatsapp("111")

    messenger = await builder.messenger(ref)
    cache_factory = builder.cache_factory(ref, "user-1")
    handler = builder.bind_handler(
        _Handler(),
        inbox_ref=ref,
        user_id="user-1",
        messenger=messenger,
        cache_factory=cache_factory,
    )

    assert handler.inbox_id == "111" and handler.user_id == "user-1"
    assert handler.messenger is messenger
    assert handler.cache_factory is cache_factory
    assert cache_factory.inbox_id == "111"
    assert handler.db is not None and handler.db_read is not None
    async with handler.db() as session:
        assert session == "primary-session"
    async with handler.db_read() as session:
        assert session == "read-session"


def test_db_and_db_read_stay_optional_without_a_fake_session() -> None:
    builder = DispatchContextBuilder(_capabilities(_Resolver()))
    handler = builder.bind_handler(
        _Handler(),
        inbox_ref=InboxRef.whatsapp("1"),
        user_id="u",
        messenger=None,
        cache_factory=None,
    )

    assert handler.db is None and handler.db_read is None
    assert builder.database_factories() == (None, None)
    with pytest.raises(RuntimeError, match="db"):
        handler.require_database()


async def test_messenger_construction_propagates_directory_outages_typed() -> None:
    resolver = _Resolver()
    resolver.unavailable = True
    builder = DispatchContextBuilder(_capabilities(resolver))

    with pytest.raises(InboxDirectoryUnavailableError):
        await builder.messenger(InboxRef.whatsapp("111"))


async def test_messenger_factory_subscribes_to_evictions_and_recreates() -> None:
    resolver = _Resolver()
    builder = DispatchContextBuilder(_capabilities(resolver))
    ref = InboxRef.whatsapp("111")
    first = await builder.messenger_factory.create_messenger(ref)
    assert await builder.messenger_factory.create_messenger(ref) is first
    assert len(resolver.listeners) == 1

    resolver.listeners[0](ref)

    assert await builder.messenger_factory.create_messenger(ref) is not first


async def test_context_factory_uses_the_shared_builder_for_cron_and_external_paths() -> (
    None
):
    resolver = _Resolver()
    app = _app(resolver, db=True)
    factory = WappaContextFactory(app)

    system = await factory.create_context(inbox_id="__system__")
    scoped = await factory.create_context(
        inbox_id="111", user_id="user-1", include_messenger=True
    )

    assert (
        system.db is not None
        and system.messenger is None
        and system.cache_factory is None
    )
    assert scoped.messenger is not None
    assert scoped.cache_factory is not None and scoped.cache_factory.inbox_id == "111"
    assert app.state.dispatch_context_builder is DispatchContextBuilder.from_app(app)


async def test_api_event_dispatcher_binds_db_through_the_shared_builder() -> None:
    handler = _Handler()
    dispatcher = APIEventDispatcher(handler)
    app = _app(_Resolver(), db=True)
    request = SimpleNamespace(app=app)
    event = APIMessageEvent(
        message_type="text",
        recipient="573001234567",
        user_id="573001234567",
        request_payload={},
        response_success=True,
        message_id="wamid.1",
        inbox_id="111",
    )

    bound = dispatcher._create_api_request_handler(event, request)  # type: ignore[arg-type]

    assert bound.inbox_id == "111"
    assert bound.db is not None and bound.db_read is not None


def test_require_database_returns_the_factory_when_present() -> None:
    builder = DispatchContextBuilder(_capabilities(_Resolver(), db=True))
    handler = builder.bind_handler(
        _Handler(), inbox_ref=None, user_id="", messenger=None, cache_factory=None
    )

    assert handler.require_database() is handler.db


# ── typed failures reach background dispatch paths (PRD 5) ─────────────────


async def test_context_factory_propagates_typed_directory_failures() -> None:
    """Cron and External Webhook Source paths must see the typed category.

    Degrading to ``messenger=None`` would surface later as an unclassified
    AttributeError inside Host code instead of the documented failure.
    """
    resolver = _Resolver()
    resolver.unavailable = True
    factory = WappaContextFactory(_app(resolver))

    with pytest.raises(InboxDirectoryUnavailableError):
        await factory.create_context(
            inbox_id="111", user_id="user-1", include_messenger=True
        )


async def test_context_factory_still_returns_a_db_only_context_when_unavailable() -> (
    None
):
    """A system-scoped context needs no Inbox, so a directory outage cannot break it."""
    resolver = _Resolver()
    resolver.unavailable = True
    factory = WappaContextFactory(_app(resolver, db=True))

    context = await factory.create_context(inbox_id="__system__")

    assert context.db is not None
    assert context.messenger is None and context.cache_factory is None


def test_the_db_fallback_uses_the_one_shared_helper() -> None:
    """Two definitions of what db/db_read mean is one too many."""
    from wappa.core.dispatch.context_builder import resolve_database_factories

    manager = _SessionManager()
    assert resolve_database_factories(manager) == (
        manager.get_session,
        manager.get_read_session,
    )
    assert resolve_database_factories(None) == (None, None)


async def test_dispatch_result_names_the_failure_category() -> None:
    """A handler failure must be attributable to a category, not just a string."""
    from wappa.core.events.event_dispatcher import WappaEventDispatcher

    class _Failing(_Handler):
        async def process_message(self, webhook: InboundMessageWebhook) -> None:
            raise InboxDirectoryUnavailableError("directory down mid-handler")

    dispatcher = WappaEventDispatcher(_Failing())
    result = await dispatcher.dispatch_universal_webhook(
        universal_webhook=object(),  # type: ignore[arg-type]
        inbox_id="111",
        request_handler=_Failing(),
    )

    assert result["success"] is False
    assert "error_type" in result
