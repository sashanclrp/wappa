"""Native Redis TTL on the scheduled lane, against a real server.

Skips when no Redis answers; ``WAPPA_TEST_REDIS_URL`` selects the server.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any

import pytest
import redis as redis_lib
from pydantic import SecretStr

from wappa import InboxRef, ScheduledEvent, Scheduling
from wappa.core.dispatch.context_builder import (
    DispatchContextBuilder,
    RuntimeCapabilities,
)
from wappa.core.events.event_handler import WappaEventHandler
from wappa.core.expiry import ExpiryDispatcher, run_expiry_listener
from wappa.core.expiry.connection import RedisConnectionManager
from wappa.core.lifecycle import BackgroundWorkTracker
from wappa.domain.inbox import (
    IInboxCredentialResolver,
    PlatformAccountRef,
    ResolvedInboxCredentials,
)
from wappa.domain.interfaces.cache_interfaces import ExpiryKeyConflictError
from wappa.persistence.redis.redis_client import RedisClient
from wappa.persistence.redis.redis_handler.expiry import RedisExpiry
from wappa.persistence.redis.redis_manager import RedisManager

REDIS_URL = os.getenv("WAPPA_TEST_REDIS_URL", "redis://localhost:6379")
USER_ACTIONS = {"agent_trigger", "message_sync", "conversation_window"}


class _Credentials(IInboxCredentialResolver):
    async def resolve_credentials(
        self, inbox_ref: InboxRef
    ) -> ResolvedInboxCredentials:
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
        return None


class _Handler(WappaEventHandler):
    def __init__(self) -> None:
        super().__init__()
        self.fired: asyncio.Queue[Any] = asyncio.Queue()

    async def process_message(self, webhook: Any) -> None:
        return None

    async def process_scheduled_event(self, event: ScheduledEvent) -> None:
        cache = self.cache_factory.create_user_cache() if self.cache_factory else None
        await self.fired.put(SimpleNamespace(event=event, handler=self, cache=cache))


async def _subjects(*, inbox_ref: InboxRef, action: str, identifier: str) -> str | None:
    return identifier if action in USER_ACTIONS else None


@pytest.fixture
async def redis_ready() -> AsyncIterator[None]:
    await RedisClient.close()
    RedisClient.setup_single_url(REDIS_URL)
    try:
        async with RedisClient.connection(alias="expiry") as redis:
            await redis.ping()
    except Exception:
        await RedisClient.close()
        pytest.skip(f"No Redis reachable at {REDIS_URL}")
    try:
        yield
    finally:
        await RedisClient.close()


@pytest.fixture
def inbox() -> InboxRef:
    # A unique Inbox keeps runs from colliding on a shared server.
    return InboxRef.whatsapp(f"test{uuid.uuid4().hex}")


@pytest.fixture
async def lane(
    redis_ready: None, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[SimpleNamespace]:
    handler = _Handler()
    tracker = BackgroundWorkTracker()
    builder = DispatchContextBuilder(
        RuntimeCapabilities(
            session_provider=lambda: SimpleNamespace(is_closed=False),  # type: ignore[arg-type,return-value]
            media_download_client_provider=lambda: SimpleNamespace(is_closed=False),  # type: ignore[arg-type,return-value]
            credential_resolver=_Credentials(),
            messenger_middleware=[],
            cache_type="redis",
            background_work_tracker=tracker,
            redis_manager=RedisManager,
        )
    )
    was_initialized = RedisManager._initialized
    RedisManager._initialized = True
    scheduling = Scheduling(context_builder=builder, event_handler=handler)
    ready = asyncio.Event()
    original_connect = RedisConnectionManager.connect

    async def connect(manager):
        connection = await original_connect(manager)
        # A pong confirms Redis processed SUBSCRIBE, not just that the client
        # wrote it to the socket. No expiry is armed before this handshake.
        await connection.pubsub.ping()
        async with asyncio.timeout(5):
            while True:
                message = await connection.pubsub.get_message(timeout=1)
                if message is not None and message["type"] == "pong":
                    break
        ready.set()
        return connection

    monkeypatch.setattr(RedisConnectionManager, "connect", connect)
    listener = asyncio.create_task(
        run_expiry_listener(
            dispatcher=ExpiryDispatcher(
                run_event=scheduling.run, tracker=tracker, subjects=_subjects
            ),
            reconnect_delay=1,
        )
    )
    try:
        await asyncio.wait_for(ready.wait(), timeout=5)
        yield SimpleNamespace(handler=handler, tracker=tracker)
    finally:
        listener.cancel()
        await asyncio.gather(listener, return_exceptions=True)
        await tracker.drain(timeout=2.0)
        RedisManager._initialized = was_initialized


def _expiry(inbox: InboxRef) -> RedisExpiry:
    return RedisExpiry(inbox=inbox.cache_namespace, user_id="arming-user")


async def _fired(lane: SimpleNamespace, inbox: InboxRef) -> SimpleNamespace:
    """The next firing for this test's Inbox, ignoring other Inboxes on the server."""
    while True:
        fired = await asyncio.wait_for(lane.handler.fired.get(), timeout=5.0)
        if fired.event.inbox_ref == inbox:
            return fired


async def test_real_expired_user_triggers_reach_the_hook_with_user_context(
    lane: SimpleNamespace,
    inbox: InboxRef,
) -> None:
    # Independent keys can expire together; exercise every action without
    # repeating the listener startup and one-second TTL wait for each one.
    expiry = _expiry(inbox)
    pending = {action: f"USER-{action}" for action in sorted(USER_ACTIONS)}
    for action, identifier in pending.items():
        assert await expiry.set(action, identifier, 1)
        assert await expiry.get_ttl(action, identifier) > 0

    handlers = []
    while pending:
        fired = await _fired(lane, inbox)
        handlers.append(fired.handler)
        identifier = pending.pop(fired.event.action)
        assert fired.event.source == "redis_expiry"
        assert fired.event.identifier == identifier
        assert fired.event.user_id == identifier
        assert fired.handler.cache_factory.user_id == identifier
        assert fired.handler.whatsapp is not None
        # The key disappears on expiry: no shadow or retained state.
        assert not await expiry.exists(fired.event.action, identifier)
        assert await expiry.get_ttl(fired.event.action, identifier) < 0
    assert len({id(handler) for handler in handlers}) == len(USER_ACTIONS)


async def test_a_real_message_keyed_trigger_stays_inbox_only(
    lane: SimpleNamespace, inbox: InboxRef
) -> None:
    await _expiry(inbox).set("template_rollback", "wamid.HBgM", 1)

    fired = await _fired(lane, inbox)

    assert fired.event.identifier == "wamid.HBgM"
    assert fired.handler.user_id is None
    assert fired.handler.cache_factory is None
    assert fired.handler.messenger is not None


async def test_the_handler_reads_real_user_state_after_expiry(
    lane: SimpleNamespace, inbox: InboxRef
) -> None:
    builder_cache = RuntimeCacheProbe(inbox, "USER2")
    await builder_cache.seed({"messages": ["hola"]})
    await _expiry(inbox).set("message_sync", "USER2", 1)

    fired = await _fired(lane, inbox)
    try:
        assert (await fired.cache.get())["messages"] == ["hola"]
    finally:
        await fired.cache.delete()


class RuntimeCacheProbe:
    def __init__(self, inbox: InboxRef, user_id: str) -> None:
        from wappa.persistence.cache_factory import create_cache_factory

        self.cache = create_cache_factory("redis")(
            inbox_id=inbox.cache_namespace, user_id=user_id
        ).create_user_cache()

    async def seed(self, data: dict[str, Any]) -> None:
        await self.cache.upsert(data, ttl=30)


async def test_a_renewed_timer_fires_once_after_the_renewal(
    lane: SimpleNamespace, inbox: InboxRef
) -> None:
    expiry = _expiry(inbox)
    await expiry.set("message_sync", "USER3", 1)
    await asyncio.sleep(0.4)
    await expiry.set("message_sync", "USER3", 2)
    await asyncio.sleep(0.8)
    assert await expiry.exists("message_sync", "USER3")

    await _fired(lane, inbox)
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(_fired(lane, inbox), timeout=1.5)


async def test_a_cancelled_trigger_never_reaches_the_hook(
    lane: SimpleNamespace, inbox: InboxRef
) -> None:
    expiry = _expiry(inbox)
    await expiry.set("agent_trigger", "USER4", 1)
    assert await expiry.delete("agent_trigger", "USER4") == 1
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(_fired(lane, inbox), timeout=1.8)


async def test_rebind_preserves_the_ttl_and_fires_under_the_new_identity(
    lane: SimpleNamespace, inbox: InboxRef
) -> None:
    expiry = _expiry(inbox)
    await expiry.set("agent_trigger", "5730", 2)

    assert await expiry.rebind("agent_trigger", "5730", "CO.abc") is True

    assert not await expiry.exists("agent_trigger", "5730")
    assert 0 < await expiry.get_ttl("agent_trigger", "CO.abc") <= 2
    fired = await _fired(lane, inbox)
    assert fired.event.identifier == "CO.abc"
    assert fired.handler.user_id == "CO.abc"


async def test_rebind_refuses_to_overwrite_an_existing_destination(
    redis_ready: None, inbox: InboxRef
) -> None:
    expiry = _expiry(inbox)
    await expiry.set("agent_trigger", "old", 30)
    await expiry.set("agent_trigger", "new", 300)
    try:
        with pytest.raises(ExpiryKeyConflictError):
            await expiry.rebind("agent_trigger", "old", "new")
        assert await expiry.get_ttl("agent_trigger", "old") <= 30
        assert await expiry.get_ttl("agent_trigger", "new") > 30
    finally:
        await expiry.delete("agent_trigger", "old")
        await expiry.delete("agent_trigger", "new")


async def test_rebind_reports_when_nothing_was_armed(
    redis_ready: None, inbox: InboxRef
) -> None:
    assert await _expiry(inbox).rebind("agent_trigger", "absent", "new") is False


async def test_rebind_to_the_same_identifier_changes_nothing(
    redis_ready: None, inbox: InboxRef
) -> None:
    expiry = _expiry(inbox)
    assert await expiry.rebind("agent_trigger", "same", "same") is False
    await expiry.set("agent_trigger", "same", 30)
    try:
        assert await expiry.rebind("agent_trigger", "same", "same") is True
    finally:
        await expiry.delete("agent_trigger", "same")


async def test_triggers_live_in_the_existing_expiry_pool(redis_ready: None) -> None:
    async with RedisClient.connection(alias="expiry") as redis:
        database = redis.connection_pool.connection_kwargs["db"]
    assert database == 3


def test_a_real_wappa_app_routes_expiry_and_host_dispatch_to_one_hook(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The whole composition: real lifespan, real listener, real TTL, real hook."""
    import threading

    from fastapi.testclient import TestClient

    from wappa import SchedulingPlugin, Wappa
    from wappa.core.config.settings import settings

    try:
        redis_lib.Redis.from_url(REDIS_URL, socket_connect_timeout=1).ping()
    except redis_lib.RedisError:
        pytest.skip(f"No Redis reachable at {REDIS_URL}")

    monkeypatch.setattr(settings, "redis_url", REDIS_URL)
    inbox_ref = InboxRef.whatsapp(settings.wp_phone_id)
    identifier = f"USER{uuid.uuid4().hex}"
    seen: list[SimpleNamespace] = []
    fired = threading.Event()

    class Handler(WappaEventHandler):
        async def process_message(self, webhook: Any) -> None:
            return None

        async def process_scheduled_event(self, event: ScheduledEvent) -> None:
            if event.source == "test" or event.identifier == identifier:
                seen.append(SimpleNamespace(event=event, handler=self))
            if event.identifier == identifier:
                fired.set()

    application = Wappa(cache="redis")
    application.add_plugin(
        SchedulingPlugin(redis_expiry=True, expiry_subjects=_subjects)
    )
    application.set_event_handler(Handler())
    app = application.asgi

    with TestClient(app) as client:
        portal = client.portal
        assert portal is not None
        expiry = _expiry(inbox_ref)
        portal.call(expiry.set, "agent_trigger", identifier, 1)
        assert fired.wait(timeout=6.0), "the expired key never reached the hook"
        portal.call(
            Scheduling.from_app(app).dispatch,
            ScheduledEvent(
                action="reminder", source="test", inbox_ref=inbox_ref, user_id="u"
            ),
        )

    expired, reminder = seen
    assert expired.event.source == "redis_expiry"
    assert expired.handler.user_id == identifier
    assert expired.handler.cache_factory.user_id == identifier
    assert expired.handler.whatsapp is not None
    assert reminder.handler.user_id == "u"
    assert expired.handler is not reminder.handler
    assert not hasattr(app.state, "expiry_listener_task")
