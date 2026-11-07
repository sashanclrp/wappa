"""One scheduled lane: every source reaches the same prepared handler."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError

import wappa
from wappa import InboxRef, ScheduledEvent, Scheduling, SchedulingPlugin, Wappa
from wappa.cli.examples.scheduled_tasks_example.app import jobs
from wappa.cli.examples.scheduled_tasks_example.app.master_event import (
    MasterEventHandler,
)
from wappa.core.dispatch import DispatchContextBuilder
from wappa.core.events.event_handler import WappaEventHandler
from wappa.core.expiry import (
    ExpiryDispatcher,
    ExpiryNotification,
    parse_expiry_notification,
)
from wappa.core.factory.inbox_assembly import InboxRuntimeConfiguration
from wappa.core.factory.wappa_builder import WappaBuilder
from wappa.core.lifecycle import BackgroundWorkTracker, SessionLifecycle
from wappa.core.logging.context import (
    bind_inbox_context,
    get_current_inbox_context,
    get_current_user_context,
    reset_inbox_context,
)
from wappa.core.messaging.pipeline import MessengerPipeline
from wappa.core.scheduling.static_cron import StaticCron, register_static_cron
from wappa.core.sse.context import get_sse_context, sse_event_scope
from wappa.domain.inbox import (
    IInboxCredentialResolver,
    InboxDirectoryUnavailableError,
    PlatformAccountRef,
    ResolvedInboxCredentials,
)
from wappa.domain.interfaces.identity_resolver import IIdentityResolver
from wappa.messaging.instagram.platform_messenger import InstagramMessenger
from wappa.messaging.whatsapp.platform_messenger import WhatsAppMessenger
from wappa.schemas.core.types import PlatformType
from wappa.webhooks import InboundMessageWebhook

WA = InboxRef.whatsapp("111")
WA_OTHER = InboxRef.whatsapp("222")
IG = InboxRef(platform=PlatformType.INSTAGRAM, inbox_id="333")


class _Credentials(IInboxCredentialResolver):
    def __init__(self) -> None:
        self.unavailable = False
        self.resolved: list[InboxRef] = []

    async def resolve_credentials(
        self, inbox_ref: InboxRef
    ) -> ResolvedInboxCredentials:
        if self.unavailable:
            raise InboxDirectoryUnavailableError("down")
        self.resolved.append(inbox_ref)
        return ResolvedInboxCredentials(
            inbox_ref=inbox_ref,
            account_ref=PlatformAccountRef(
                platform=inbox_ref.platform, platform_account_id="account"
            ),
            access_token=SecretStr("token"),
            credential_version=1,
        )

    async def list_inbox_refs_for_platform_account(
        self, account_ref: PlatformAccountRef
    ) -> tuple[InboxRef, ...]:
        return ()

    def subscribe_evictions(self, listener: Any) -> None:
        return None


class _CanonicalResolver(IIdentityResolver):
    def __init__(self, mapping: dict[str, str] | None = None) -> None:
        self.mapping = mapping or {}
        self.calls: list[tuple[str, InboxRef]] = []

    async def resolve(self, recipient: str, *, inbox_ref: InboxRef) -> str:
        self.calls.append((recipient, inbox_ref))
        return self.mapping.get(recipient, recipient)


class _SessionManager:
    @asynccontextmanager
    async def get_session(self):  # type: ignore[no-untyped-def]
        yield "primary-session"

    @asynccontextmanager
    async def get_read_session(self):  # type: ignore[no-untyped-def]
        yield "read-session"


class _Handler(WappaEventHandler):
    """Records the context every invocation actually received."""

    def __init__(self) -> None:
        super().__init__()
        self.seen: list[SimpleNamespace] = []
        self.fail_with: Exception | None = None
        self.gate: asyncio.Event | None = None
        self.body: Any = None

    async def process_message(self, webhook: InboundMessageWebhook) -> None:
        return None

    async def process_scheduled_event(self, event: ScheduledEvent) -> None:
        sse = get_sse_context()
        self.seen.append(
            SimpleNamespace(
                handler=self,
                event=event,
                sse=None
                if sse is None
                else (sse.inbox_id, sse.user_id, sse.bsuid, sse.phone_number),
                sse_platform=None if sse is None else sse.platform,
                log=(get_current_inbox_context(), get_current_user_context()),
            )
        )
        if self.gate is not None:
            await self.gate.wait()
        if self.body is not None:
            await self.body(self, event)
        if self.fail_with is not None:
            raise self.fail_with


def _app(
    handler: WappaEventHandler | None = None,
    *,
    credentials: _Credentials | None = None,
    resolver: IIdentityResolver | None = None,
    db: bool = False,
    cache_type: str = "memory",
) -> Any:
    session = SimpleNamespace(is_closed=False)
    return SimpleNamespace(
        state=SimpleNamespace(
            session_lifecycle=SessionLifecycle(session),  # type: ignore[arg-type]
            inbox_runtime=InboxRuntimeConfiguration(
                mode=wappa.InboxRoutingMode.EXPLICIT,
                credential_resolver=credentials or _Credentials(),
            ),
            messenger_middleware=[],
            wappa_cache_type=cache_type,
            background_work_tracker=BackgroundWorkTracker(),
            postgres_session_manager=_SessionManager() if db else None,
            identity_resolver=resolver,
            wappa_event_handler=handler if handler is not None else _Handler(),
        )
    )


async def _dispatch(app: Any, **fields: Any) -> None:
    fields.setdefault("action", "task")
    fields.setdefault("source", "test")
    await Scheduling.from_app(app).dispatch(ScheduledEvent(**fields))


# --- The event --------------------------------------------------------------


def test_a_user_scoped_event_requires_an_inbox() -> None:
    with pytest.raises(ValidationError, match="requires inbox_ref"):
        ScheduledEvent(action="a", source="s", user_id="u")


def test_naive_timestamps_are_refused_and_others_become_utc() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        ScheduledEvent(action="a", source="s", scheduled_for=datetime(2026, 11, 6))  # noqa: DTZ001 - the naive value is the case under test

    bogota = timezone(timedelta(hours=-5))
    event = ScheduledEvent(
        action="a", source="s", scheduled_for=datetime(2026, 11, 6, 9, tzinfo=bogota)
    )
    assert event.scheduled_for == datetime(2026, 11, 6, 14, tzinfo=UTC)
    assert event.scheduled_for is not None
    assert event.scheduled_for.utcoffset() == timedelta(0)
    assert event.dispatched_at.utcoffset() == timedelta(0)


def test_engine_facts_are_optional_and_unknown_fields_are_refused() -> None:
    event = ScheduledEvent(action="a", source="custom")
    assert (event.inbox_ref, event.user_id, event.identifier) == (None, None, None)
    assert (event.execution_id, event.scheduled_for) == (None, None)
    with pytest.raises(ValidationError):
        ScheduledEvent(action="a", source="s", cron_expr="* * * * *")  # type: ignore[call-arg]


# --- Scope capabilities -----------------------------------------------------


async def test_user_scope_prepares_every_capability() -> None:
    handler = _Handler()
    await _dispatch(_app(handler, db=True), inbox_ref=WA, user_id="u1")

    bound = handler.seen[0].handler
    assert isinstance(bound.messenger, MessengerPipeline)
    assert isinstance(bound.whatsapp, WhatsAppMessenger)
    assert bound.instagram is None
    assert (bound.inbox_ref, bound.inbox_id, bound.user_id) == (WA, "111", "u1")
    assert bound.cache_factory is not None
    assert bound.cache_factory.user_id == "u1"
    assert bound.cache_factory.inbox_id == WA.cache_namespace
    assert bound.db is not None
    assert bound.db_read is not None


async def test_inbox_scope_has_its_messenger_and_no_invented_user() -> None:
    handler = _Handler()
    await _dispatch(_app(handler), inbox_ref=IG)

    bound = handler.seen[0].handler
    assert isinstance(bound.messenger, MessengerPipeline)
    assert isinstance(bound.instagram, InstagramMessenger)
    assert bound.whatsapp is None
    assert bound.user_id is None
    assert bound.cache_factory is None
    assert handler.seen[0].sse == ("333", "unknown", None, None)
    assert handler.seen[0].sse_platform == "instagram"


async def test_system_scope_invents_neither_identity_nor_messaging() -> None:
    credentials = _Credentials()
    handler = _Handler()
    await _dispatch(_app(handler, credentials=credentials, db=True))

    bound = handler.seen[0].handler
    assert (bound.inbox_ref, bound.inbox_id, bound.user_id) == (None, None, None)
    assert (bound.messenger, bound.whatsapp, bound.instagram) == (None, None, None)
    assert bound.cache_factory is None
    assert bound.db is not None
    assert credentials.resolved == []
    assert handler.seen[0].sse is None


@pytest.mark.parametrize(
    "scope", [{}, {"inbox_ref": WA}, {"inbox_ref": WA, "user_id": "u"}]
)
async def test_database_stays_optional_in_every_scope(scope: dict[str, Any]) -> None:
    handler = _Handler()
    await _dispatch(_app(handler), **scope)
    assert handler.seen[0].handler.db is None
    assert handler.seen[0].handler.db_read is None


# --- Identity ---------------------------------------------------------------


async def test_canonical_user_reaches_event_handler_and_cache_scope() -> None:
    resolver = _CanonicalResolver({"5730": "CO.abc"})
    handler = _Handler()
    await _dispatch(_app(handler, resolver=resolver), inbox_ref=WA, user_id="5730")

    seen = handler.seen[0]
    assert resolver.calls == [("5730", WA)]
    assert seen.event.user_id == "CO.abc"
    assert seen.handler.user_id == "CO.abc"
    assert seen.handler.cache_factory.user_id == "CO.abc"
    assert seen.sse[1] == "CO.abc"
    assert seen.log == ("111", "CO.abc")


async def test_the_resolver_is_asked_within_the_tasks_own_inbox() -> None:
    resolver = _CanonicalResolver()
    app = _app(resolver=resolver)
    await _dispatch(app, inbox_ref=WA, user_id="same")
    await _dispatch(app, inbox_ref=WA_OTHER, user_id="same")
    assert resolver.calls == [("same", WA), ("same", WA_OTHER)]


async def test_inbox_and_system_work_never_consult_the_resolver() -> None:
    resolver = _CanonicalResolver()
    app = _app(resolver=resolver)
    await _dispatch(app, inbox_ref=WA, identifier="wamid.ABC")
    await _dispatch(app)
    assert resolver.calls == []


async def test_identifier_is_never_read_as_a_user_or_shaped_into_sse() -> None:
    handler = _Handler()
    await _dispatch(_app(handler), inbox_ref=WA, identifier="5730000000")

    seen = handler.seen[0]
    assert seen.handler.user_id is None
    assert seen.event.identifier == "5730000000"
    assert seen.sse == ("111", "unknown", None, None)


# --- Failure propagation ----------------------------------------------------


async def test_a_handler_exception_reaches_the_awaiting_caller() -> None:
    handler = _Handler()
    handler.fail_with = LookupError("business failure")
    with pytest.raises(LookupError, match="business failure"):
        await _dispatch(_app(handler), inbox_ref=WA, user_id="u")


async def test_unavailable_inbox_fails_typed_before_the_host_hook() -> None:
    credentials = _Credentials()
    credentials.unavailable = True
    handler = _Handler()
    with pytest.raises(InboxDirectoryUnavailableError):
        await _dispatch(
            _app(handler, credentials=credentials), inbox_ref=WA, user_id="u"
        )
    assert handler.seen == []


async def test_unavailable_user_cache_fails_before_the_host_hook() -> None:
    handler = _Handler()
    with pytest.raises(RuntimeError, match="RedisPlugin not available"):
        await _dispatch(_app(handler, cache_type="redis"), inbox_ref=WA, user_id="u")
    assert handler.seen == []


async def test_a_resolver_failure_never_falls_back_to_the_armed_identifier() -> None:
    class _Broken(IIdentityResolver):
        async def resolve(self, recipient: str, *, inbox_ref: InboxRef) -> str:
            raise ConnectionError("identity store down")

    handler = _Handler()
    with pytest.raises(ConnectionError):
        await _dispatch(_app(handler, resolver=_Broken()), inbox_ref=WA, user_id="u")
    assert handler.seen == []


async def test_a_resolver_returning_nothing_fails_explicitly() -> None:
    handler = _Handler()
    with pytest.raises(ValueError, match="returned no User"):
        await _dispatch(
            _app(handler, resolver=_CanonicalResolver({"u": ""})),
            inbox_ref=WA,
            user_id="u",
        )
    assert handler.seen == []


def test_from_app_without_a_handler_explains_how_to_set_one() -> None:
    app = _app()
    app.state.wappa_event_handler = None
    with pytest.raises(RuntimeError, match="set_event_handler"):
        Scheduling.from_app(app)


# --- Isolation --------------------------------------------------------------


async def test_every_invocation_gets_a_fresh_clone_and_the_prototype_stays_unbound() -> (
    None
):
    prototype = _Handler()

    async def remember(handler: Any, event: ScheduledEvent) -> None:
        assert getattr(handler, "host_state", None) is None
        handler.host_state = event.user_id

    prototype.body = remember
    app = _app(prototype)
    await _dispatch(app, inbox_ref=WA, user_id="a")
    await _dispatch(app, inbox_ref=WA, user_id="b")

    first, second = prototype.seen
    assert first.handler is not second.handler
    assert first.handler is not prototype
    assert prototype.user_id is None
    assert prototype.messenger is None
    assert not hasattr(prototype, "host_state")


async def test_concurrent_dispatches_keep_their_own_identity() -> None:
    handler = _Handler()
    observed: dict[str, tuple[Any, Any]] = {}

    async def record(bound: Any, event: ScheduledEvent) -> None:
        await asyncio.sleep(0)
        sse = get_sse_context()
        assert sse is not None
        observed[event.payload["n"]] = (
            (sse.inbox_id, sse.user_id),
            (bound.inbox_id, bound.user_id, bound.cache_factory.user_id),
        )

    handler.body = record
    app = _app(handler)
    await asyncio.gather(
        *(
            _dispatch(
                app,
                inbox_ref=WA if n % 2 else WA_OTHER,
                user_id=f"u{n}",
                payload={"n": str(n)},
            )
            for n in range(10)
        )
    )
    for n in range(10):
        inbox_id = "111" if n % 2 else "222"
        assert observed[str(n)] == (
            (inbox_id, f"u{n}"),
            (inbox_id, f"u{n}", f"u{n}"),
        )


async def test_sse_and_log_identity_are_restored_after_dispatch() -> None:
    handler = _Handler()
    token = bind_inbox_context("parent")
    try:
        async with sse_event_scope(
            inbox_id="parent", user_id="parent-user", platform="whatsapp"
        ):
            builder_app = _app(handler)
            await _dispatch(builder_app, inbox_ref=WA, user_id="u")
            await Scheduling.from_app(builder_app).run(
                ScheduledEvent(action="in-task", source="t", inbox_ref=WA, user_id="v")
            )
            assert handler.seen[1].sse[:2] == ("111", "v")
            sse = get_sse_context()
            assert sse is not None
            assert (sse.inbox_id, sse.user_id) == ("parent", "parent-user")
            assert get_current_inbox_context() == "parent"
    finally:
        reset_inbox_context(token)
    assert get_sse_context() is None


async def test_system_work_does_not_inherit_its_callers_sse_identity() -> None:
    handler = _Handler()
    async with sse_event_scope(inbox_id="parent", user_id="p", platform="whatsapp"):
        await Scheduling.from_app(_app(handler)).run(
            ScheduledEvent(action="beat", source="t")
        )
        assert handler.seen[0].sse is None
        sse = get_sse_context()
        assert sse is not None
        assert sse.user_id == "p"


# --- self.scope -------------------------------------------------------------


async def test_scope_prepares_another_user_and_restores_the_parent() -> None:
    resolver = _CanonicalResolver({"phone": "CO.owner"})
    handler = _Handler()
    captured: dict[str, Any] = {}

    async def body(bound: Any, event: ScheduledEvent) -> None:
        async with bound.scope(user_id="phone") as owner:
            sse = get_sse_context()
            captured["owner"] = owner
            captured["inner_sse"] = (sse.inbox_id, sse.user_id)
            captured["inner_log"] = get_current_user_context()
        sse = get_sse_context()
        captured["outer_sse"] = (sse.inbox_id, sse.user_id)
        captured["outer_log"] = get_current_user_context()

    handler.body = body
    await _dispatch(_app(handler, resolver=resolver), inbox_ref=WA, user_id="u")

    owner = captured["owner"]
    assert (owner.inbox_ref, owner.user_id) == (WA, "CO.owner")
    assert owner.cache_factory.user_id == "CO.owner"
    assert isinstance(owner.whatsapp, WhatsAppMessenger)
    assert owner is not handler.seen[0].handler
    assert captured["inner_sse"] == ("111", "CO.owner")
    assert captured["inner_log"] == "CO.owner"
    assert captured["outer_sse"] == ("111", "u")
    assert captured["outer_log"] == "u"


async def test_scope_reaches_another_inbox_through_the_same_credentials() -> None:
    credentials = _Credentials()
    handler = _Handler()
    captured: dict[str, Any] = {}

    async def body(bound: Any, event: ScheduledEvent) -> None:
        async with bound.scope(inbox_ref=IG, user_id="ig-user") as other:
            captured["other"] = other

    handler.body = body
    await _dispatch(_app(handler, credentials=credentials), inbox_ref=WA, user_id="u")

    assert isinstance(captured["other"].instagram, InstagramMessenger)
    assert captured["other"].whatsapp is None
    assert credentials.resolved == [WA, IG]


async def test_scope_does_not_carry_host_state_to_another_subject() -> None:
    handler = _Handler()
    captured: dict[str, Any] = {}

    async def body(bound: Any, event: ScheduledEvent) -> None:
        bound.typed_user_cache = "only for u"
        async with bound.scope(user_id="other") as other:
            captured["leaked"] = getattr(other, "typed_user_cache", None)

    handler.body = body
    await _dispatch(_app(handler), inbox_ref=WA, user_id="u")
    assert captured["leaked"] is None


async def test_scope_is_restored_when_its_body_raises() -> None:
    handler = _Handler()

    async def body(bound: Any, event: ScheduledEvent) -> None:
        with pytest.raises(KeyError):
            async with bound.scope(user_id="other"):
                raise KeyError("boom")
        assert get_sse_context().user_id == "u"

    handler.body = body
    await _dispatch(_app(handler), inbox_ref=WA, user_id="u")


async def test_system_scope_needs_an_inbox_to_reach_a_user() -> None:
    handler = _Handler()

    async def body(bound: Any, event: ScheduledEvent) -> None:
        with pytest.raises(ValueError, match="requires inbox_ref"):
            async with bound.scope(user_id="u"):
                pass
        async with bound.scope(inbox_ref=WA, user_id="u") as scoped:
            assert scoped.user_id == "u"

    handler.body = body
    await _dispatch(_app(handler))


def test_scope_on_an_unbound_handler_is_an_explicit_error() -> None:
    with pytest.raises(RuntimeError, match="Dispatch Context"):
        _Handler().scope(user_id="u")


async def test_scope_is_available_to_webhook_handlers_bound_by_the_builder() -> None:
    handler = _Handler()
    app = _app(handler)
    builder = DispatchContextBuilder.from_app(app)
    bound = builder.bind_handler(
        handler,
        inbox_ref=WA,
        user_id="u",
        messenger=await builder.messenger(WA),
        cache_factory=builder.cache_factory(WA, "u"),
    )
    async with bound.scope(user_id="v") as other:
        assert other.user_id == "v"


# --- Lifecycle --------------------------------------------------------------


async def test_dispatch_counts_as_tracked_work_and_drain_waits_for_it() -> None:
    handler = _Handler()
    handler.gate = asyncio.Event()
    app = _app(handler)
    tracker = app.state.background_work_tracker

    task = asyncio.create_task(_dispatch(app, inbox_ref=WA, user_id="u"))
    await asyncio.sleep(0.01)
    assert tracker.active_count == 1

    drain = asyncio.create_task(tracker.drain(timeout=2.0))
    await asyncio.sleep(0.01)
    assert not drain.done()
    handler.gate.set()

    result = await drain
    await task
    assert result.completed == 1
    assert result.cancelled == 0


async def test_dispatch_during_drain_raises_without_running_the_hook() -> None:
    handler = _Handler()
    app = _app(handler)
    app.state.background_work_tracker.begin_drain()

    with pytest.raises(RuntimeError, match="draining"):
        await _dispatch(app, inbox_ref=WA, user_id="u")
    assert handler.seen == []


async def test_a_cancelled_caller_cancels_the_scheduled_work() -> None:
    handler = _Handler()
    handler.gate = asyncio.Event()
    app = _app(handler)

    task = asyncio.create_task(_dispatch(app))
    await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await asyncio.sleep(0)
    assert app.state.background_work_tracker.active_count == 0


# --- Redis expiry adapter ---------------------------------------------------


def _notification(action: str, identifier: str) -> ExpiryNotification:
    notification = parse_expiry_notification(
        {
            "type": "message",
            "data": f"{WA.cache_namespace}:EXPTRIGGER:{action}:{identifier}",
        }
    )
    assert notification is not None
    return notification


async def _user_actions(
    *, inbox_ref: InboxRef, action: str, identifier: str
) -> str | None:
    """The shape a Host binding takes: facts about its own actions only."""
    if action in {"agent_trigger", "message_sync", "conversation_window"}:
        return identifier
    if action == "template_rollback":
        return None
    raise LookupError(f"Unknown expiry action {action}")


def _expiry(app: Any, subjects: Any = _user_actions) -> ExpiryDispatcher:
    return ExpiryDispatcher(
        run_event=Scheduling.from_app(app).run,
        tracker=app.state.background_work_tracker,
        subjects=subjects,
    )


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ({"type": "subscribe", "data": 1}, None),
        ({"type": "message", "data": ""}, None),
        ({"type": "message", "data": "whatsapp__1:user:abc"}, None),
        (None, None),
    ],
)
def test_messages_that_are_not_expiry_keys_are_ignored(
    message: dict[str, Any] | None, expected: None
) -> None:
    assert parse_expiry_notification(message) is expected


def test_expiry_key_bytes_and_namespaced_actions_parse() -> None:
    parsed = parse_expiry_notification(
        {"type": "message", "data": b"whatsapp__1:EXPTRIGGER:app_episode:CO.x:y"}
    )
    assert parsed is not None
    assert parsed.inbox_ref == InboxRef.whatsapp("1")
    assert parsed.action == "app_episode"
    assert parsed.identifier == "CO.x:y"


def test_a_trigger_with_an_invalid_namespace_is_observable_and_dropped(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        parsed = parse_expiry_notification(
            {"type": "message", "data": "not-qualified:EXPTRIGGER:a:b"}
        )
    assert parsed is None
    assert "invalid Inbox namespace" in caplog.text


async def test_expiry_user_action_gets_the_full_user_context() -> None:
    resolver = _CanonicalResolver({"5730": "CO.abc"})
    handler = _Handler()
    await _expiry(_app(handler, resolver=resolver)).dispatch(
        _notification("agent_trigger", "5730")
    )

    seen = handler.seen[0]
    assert seen.event.source == "redis_expiry"
    assert seen.event.action == "agent_trigger"
    assert seen.event.identifier == "5730"
    assert seen.event.user_id == "CO.abc"
    assert seen.handler.cache_factory.user_id == "CO.abc"
    assert isinstance(seen.handler.whatsapp, WhatsAppMessenger)
    assert seen.sse[:2] == ("111", "CO.abc")


async def test_a_message_keyed_action_stays_inbox_only() -> None:
    resolver = _CanonicalResolver()
    handler = _Handler()
    await _expiry(_app(handler, resolver=resolver)).dispatch(
        _notification("template_rollback", "wamid.HBgM")
    )

    seen = handler.seen[0]
    assert seen.event.identifier == "wamid.HBgM"
    assert seen.handler.user_id is None
    assert seen.handler.cache_factory is None
    assert isinstance(seen.handler.messenger, MessengerPipeline)
    assert seen.sse == ("111", "unknown", None, None)
    assert resolver.calls == []


async def test_without_a_binding_a_phone_shaped_identifier_is_not_a_user() -> None:
    handler = _Handler()
    await _expiry(_app(handler), subjects=None).dispatch(
        _notification("agent_trigger", "573000000000")
    )
    assert handler.seen[0].handler.user_id is None


async def test_an_unknown_binding_is_logged_and_fabricates_no_user(
    caplog: pytest.LogCaptureFixture,
) -> None:
    handler = _Handler()
    with caplog.at_level(logging.ERROR):
        task = _expiry(_app(handler)).dispatch(_notification("mystery", "abc"))
        await asyncio.wait([task])
        await asyncio.sleep(0)
    assert handler.seen == []
    assert "Expiry action failed: action=mystery" in caplog.text


async def test_a_handler_failure_on_expiry_is_logged_not_raised_into_the_listener(
    caplog: pytest.LogCaptureFixture,
) -> None:
    handler = _Handler()
    handler.fail_with = LookupError("business failure")
    with caplog.at_level(logging.ERROR):
        task = _expiry(_app(handler)).dispatch(_notification("agent_trigger", "u"))
        await asyncio.wait([task])
        await asyncio.sleep(0)
    assert "Expiry action failed: action=agent_trigger" in caplog.text


async def test_expiry_work_is_tracked_and_refused_while_draining() -> None:
    handler = _Handler()
    handler.gate = asyncio.Event()
    app = _app(handler)
    expiry = _expiry(app)
    tracker = app.state.background_work_tracker

    task = expiry.dispatch(_notification("agent_trigger", "u"))
    assert tracker.active_count == 1
    handler.gate.set()
    await task

    tracker.begin_drain()
    with pytest.raises(RuntimeError, match="draining"):
        expiry.dispatch(_notification("agent_trigger", "u"))


# --- Static crons -----------------------------------------------------------


class _FakeCronEngine:
    def __init__(self) -> None:
        self.jobs: dict[str, Any] = {}
        self.options: dict[str, dict[str, Any]] = {}

    def cron(self, **options: Any) -> Any:
        def decorate(fn: Any) -> Any:
            self.jobs[options["name"]] = fn
            self.options[options["name"]] = options
            return fn

        return decorate


async def test_a_static_cron_reaches_the_same_hook_with_its_registration() -> None:
    handler = _Handler()
    app = _app(handler)
    engine = _FakeCronEngine()
    cron = StaticCron(
        action="daily_report",
        expr="0 9 * * *",
        inbox_ref=WA,
        tags=["reports"],
        payload={"kind": "summary"},
        max_retries=3,
    )
    register_static_cron(engine, cron, app)  # type: ignore[arg-type]
    await engine.jobs["daily_report"]()

    seen = handler.seen[0]
    assert seen.event.source == "static_cron"
    assert seen.event.action == "daily_report"
    assert seen.event.payload == {"kind": "summary"}
    assert seen.event.metadata == {"cron_expr": "0 9 * * *", "tags": ["reports"]}
    # Inbox-only crons used to lose their Messenger.
    assert isinstance(seen.handler.whatsapp, WhatsAppMessenger)
    assert engine.options["daily_report"]["max_retries"] == 3


async def test_a_static_cron_failure_reaches_the_engines_retry_policy() -> None:
    """Regression: the cron path logged and swallowed every failure."""
    handler = _Handler()
    handler.fail_with = LookupError("business failure")
    engine = _FakeCronEngine()
    register_static_cron(
        engine,  # type: ignore[arg-type]
        StaticCron(action="report", expr="* * * * *"),
        _app(handler),
    )
    with pytest.raises(LookupError):
        await engine.jobs["report"]()


async def test_a_cron_firing_cannot_change_the_next_firings_payload() -> None:
    handler = _Handler()

    async def mutate(bound: Any, event: ScheduledEvent) -> None:
        event.payload["seen"] = True

    handler.body = mutate
    engine = _FakeCronEngine()
    register_static_cron(
        engine,  # type: ignore[arg-type]
        StaticCron(action="r", expr="* * * * *", payload={"n": 1}),
        _app(handler),
    )
    await engine.jobs["r"]()
    await engine.jobs["r"]()
    assert handler.seen[1].event.payload == {"n": 1, "seen": True}
    assert handler.seen[0].event.payload is not handler.seen[1].event.payload


# --- SchedulingPlugin -------------------------------------------------------


def test_expiry_subjects_without_redis_expiry_is_a_configuration_error() -> None:
    async def subject(**_: Any) -> None:
        return None

    with pytest.raises(ValueError, match="requires redis_expiry"):
        SchedulingPlugin(expiry_subjects=subject)


def test_redis_expiry_without_redis_fails_startup() -> None:
    plugin = SchedulingPlugin(event_handler=_Handler(), redis_expiry=True)
    app = WappaBuilder().add_plugin(plugin).build()
    with pytest.raises(RuntimeError, match="requires Redis"), TestClient(app):
        pass


def test_a_plugin_with_no_sources_adds_no_routes_or_engine() -> None:
    plugin = SchedulingPlugin(event_handler=_Handler())
    app = WappaBuilder().add_plugin(plugin).build()
    with TestClient(app) as client:
        assert client.get("/crons/monitor/status").status_code == 404
        assert app.state.wappa_event_handler is plugin.event_handler
    assert plugin._cron_engine is None
    assert plugin._listener_task is None


def test_builder_apps_without_a_handler_fail_startup_explaining_why() -> None:
    app = WappaBuilder().add_plugin(SchedulingPlugin()).build()
    with pytest.raises(RuntimeError, match="event_handler"), TestClient(app):
        pass


def test_wappa_publishes_its_handler_for_scheduling() -> None:
    handler = _Handler()
    application = Wappa()
    application.set_event_handler(handler)
    assert application.asgi.state.wappa_event_handler is handler


def test_prebuilt_apps_receive_the_handler_in_either_order() -> None:
    handler = _Handler()

    first = Wappa()
    first.set_event_handler(handler)
    first_app = FastAPI()
    first.set_app(first_app)
    assert first_app.state.wappa_event_handler is handler

    second = Wappa()
    second_app = FastAPI()
    second.set_app(second_app)
    second.set_event_handler(handler)
    assert second_app.state.wappa_event_handler is handler


def test_real_lifespan_dispatch_from_a_host_callback_needs_no_request() -> None:
    handler = _Handler()
    application = Wappa()
    application.set_event_handler(handler)
    app = application.asgi

    with TestClient(app) as client:
        portal = client.portal
        assert portal is not None
        portal.call(
            Scheduling.from_app(app).dispatch,
            ScheduledEvent(action="beat", source="custom"),
        )
    assert handler.seen[0].event.action == "beat"
    assert handler.seen[0].handler.inbox_ref is None


# --- Removed surface --------------------------------------------------------


@pytest.mark.parametrize(
    "name", ["CronEvent", "ExpiryPlugin", "expiry_registry", "CronPlugin"]
)
def test_old_top_level_names_are_gone(name: str) -> None:
    assert not hasattr(wappa, name)


@pytest.mark.parametrize(
    "name",
    [
        "create_expiry_messenger",
        "create_expiry_cache_factory",
        "parse_inbox_ref_from_expired_key",
        "expiry_registry",
        "ExpirationHandlerRegistry",
        "AppContext",
        "get_app_context",
        "ExpiryContextError",
    ],
)
def test_old_expiry_helpers_are_gone(name: str) -> None:
    import wappa.core.expiry as expiry

    assert not hasattr(expiry, name)


def test_old_handler_hooks_are_gone() -> None:
    assert not hasattr(WappaEventHandler, "process_cron_event")
    assert not hasattr(WappaEventHandler, "handle_cron_event")


# --- Packaged example: a Host scheduler on the common lane ------------------


class _AddScheduleEngine:
    """The APScheduler 4 calls the example uses, firing on demand.

    It keeps job arguments JSON-serializable, as a persistent job store would.
    """

    def __init__(self) -> None:
        self.schedules: dict[str, tuple[Any, Any, dict[str, Any]]] = {}

    async def add_schedule(
        self, func: Any, trigger: Any, *, id: str, kwargs: dict[str, Any]
    ) -> None:
        import json

        self.schedules[id] = (func, trigger, json.loads(json.dumps(kwargs)))

    async def fire(self, schedule_id: str) -> None:
        func, _, kwargs = self.schedules[schedule_id]
        await func(**kwargs)


class _Trigger(SimpleNamespace):
    pass


@pytest.fixture
async def example() -> Any:
    handler = MasterEventHandler()
    sends: list[tuple[str, str]] = []

    app = _app(handler, resolver=_CanonicalResolver({"5551110000": "CO.owner"}))
    app.state.messenger_middleware = [(_RecordingMiddleware(sends), 0)]
    jobs.bind_app(app)
    engine = _AddScheduleEngine()
    await jobs.register_schedules(
        engine,
        date_trigger=_Trigger,
        interval_trigger=_Trigger,
        inbox_id="111",
        user_id="5551234567",
        owners=["5551110000", "5552220000"],
        now=datetime(2026, 11, 6, 12, tzinfo=UTC),
    )
    yield SimpleNamespace(engine=engine, sends=sends, app=app, handler=handler)
    jobs.bind_app(None)


class _RecordingMiddleware:
    """Stops sends at the middleware seam, proving the pipeline runs them."""

    name = "recording"

    def __init__(self, sends: list[tuple[str, str]]) -> None:
        self.sends = sends

    async def handle(self, invocation: Any, call_next: Any) -> Any:
        self.sends.append((invocation.target.address, invocation.arguments["text"]))
        return SimpleNamespace(success=True, message_id="sent", platform=None)


async def test_example_one_time_reminder_runs_in_user_scope(example: Any) -> None:
    await example.engine.fire("reminder-A17")
    assert example.sends == [("5551234567", "Reminder: Appointment at 3 PM")]


async def test_example_recurring_reports_use_scope_for_each_recipient(
    example: Any,
) -> None:
    await example.engine.fire("weekly-report")
    await example.engine.fire("campaign-report")
    assert [address for address, _ in example.sends] == [
        "CO.owner",
        "5552220000",
    ] * 2
    # The end condition is engine configuration; Wappa neither sees nor enforces it.
    _, trigger, _ = example.engine.schedules["campaign-report"]
    assert trigger.end_time == datetime(2026, 12, 6, 12, tzinfo=UTC)


async def test_example_heartbeat_runs_as_system_work(example: Any) -> None:
    await example.engine.fire("heartbeat")
    assert example.sends == []


async def test_example_unknown_action_reaches_the_scheduler(example: Any) -> None:
    with pytest.raises(ValueError, match="Unknown scheduled action"):
        await jobs.run_scheduled_job(action="typo", schedule_id="s")


async def test_generic_host_loop_uses_the_same_lane(example: Any) -> None:
    seen: list[ScheduledEvent] = []
    original = MasterEventHandler.process_scheduled_event

    async def spy(self: Any, event: ScheduledEvent) -> None:
        seen.append(event)
        await original(self, event)

    MasterEventHandler.process_scheduled_event = spy  # type: ignore[method-assign]
    try:
        await jobs.heartbeat_loop(0, beats=2)
    finally:
        MasterEventHandler.process_scheduled_event = original  # type: ignore[method-assign]
    assert [(e.source, e.execution_id) for e in seen] == [
        ("custom_loop", "beat-1"),
        ("custom_loop", "beat-2"),
    ]


async def test_an_episode_style_task_keeps_host_identifiers_opaque() -> None:
    handler = _Handler()
    await _dispatch(
        _app(handler),
        action="episode_step",
        source="apscheduler",
        inbox_ref=WA,
        user_id="u",
        identifier="episode-7",
        execution_id="job-1:2026-11-06T14:00:00Z",
        payload={"block_revision": 3, "queued_attempt": 2},
        metadata={"retry_attempt": 1},
        scheduled_for=datetime(2026, 11, 6, 14, tzinfo=UTC),
    )
    event = handler.seen[0].event
    assert event.identifier == "episode-7"
    assert event.payload == {"block_revision": 3, "queued_attempt": 2}
    assert event.metadata == {"retry_attempt": 1}
    assert event.execution_id == "job-1:2026-11-06T14:00:00Z"
    assert event.dispatched_at >= event.scheduled_for
