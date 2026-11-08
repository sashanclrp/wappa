"""Every resolver call site passes the same qualified InboxRef (0.34.1)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from wappa.api.dependencies.cache_dependencies import get_handler_state_service
from wappa.api.dependencies.event_dependencies import dispatch_api_message_event
from wappa.api.dependencies.whatsapp_dependencies import get_template_state_service
from wappa.api.utils.event_decorators import fire_api_event, resolve_event_user_id
from wappa.core.dispatch.context_builder import DispatchContextBuilder
from wappa.core.lifecycle import BackgroundWorkTracker
from wappa.core.logging.context import bind_inbox_context, reset_inbox_context
from wappa.domain.inbox.identity import InboxRef
from wappa.domain.interfaces.identity_resolver import (
    IIdentityResolver,
    PassthroughIdentityResolver,
)
from wappa.domain.results import MessageResult
from wappa.messaging.whatsapp.models.template_models import TemplateStateConfig
from wappa.schemas.core.types import PlatformType

RAW_ID = "17841400000000"
RECIPIENT = "5730000000"
WA = InboxRef.whatsapp(RAW_ID)
WA_OTHER = InboxRef.whatsapp("99999")
IG = InboxRef(platform=PlatformType.INSTAGRAM, inbox_id=RAW_ID)


class _Spy(IIdentityResolver):
    def __init__(self) -> None:
        self.refs: list[Any] = []

    async def resolve(self, recipient: str, *, inbox_ref: InboxRef) -> str:
        self.refs.append(inbox_ref)
        return f"{inbox_ref.platform.value}/{inbox_ref.inbox_id}/{recipient}"


def _request(resolver: IIdentityResolver | None) -> Any:
    return SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                identity_resolver=resolver,
                wappa_cache_type="memory",
                background_work_tracker=BackgroundWorkTracker(),
            )
        )
    )


def _context(ref: InboxRef) -> Any:
    return SimpleNamespace(inbox_ref=ref)


def _builder(resolver: IIdentityResolver | None) -> DispatchContextBuilder:
    builder = DispatchContextBuilder.__new__(DispatchContextBuilder)
    builder.capabilities = SimpleNamespace(  # type: ignore[assignment]
        identity_resolver=resolver, cache_type="memory"
    )
    return builder


@pytest.mark.parametrize("ref", [WA, IG])
async def test_dispatch_scope_passes_the_original_ref(ref: InboxRef) -> None:
    spy = _Spy()

    await _builder(spy).canonical_user(ref, RECIPIENT)

    assert spy.refs == [ref]


@pytest.mark.parametrize("ref", [WA, IG])
async def test_api_handler_state_passes_the_selected_ref_not_a_namespace(
    ref: InboxRef,
) -> None:
    spy = _Spy()
    service = await get_handler_state_service(_request(spy), _context(ref))

    await service.set_handler_state(RECIPIENT, "flow", ttl_seconds=60)

    assert spy.refs == [ref]
    assert isinstance(spy.refs[0], InboxRef)
    assert service.cache_factory.inbox_id == ref.cache_namespace


async def test_template_state_passes_the_whatsapp_ref_not_a_namespace() -> None:
    spy = _Spy()
    service = await get_template_state_service(_request(spy), _context(WA))

    created = await service.set_template_state(
        RECIPIENT,
        TemplateStateConfig(state_value="followup", ttl_seconds=120),
        "wamid.1",
        "welcome",
    )

    assert created is True
    assert spy.refs == [WA]


@pytest.mark.parametrize("ref", [WA, IG])
async def test_api_event_path_passes_the_ref_of_the_sending_platform(
    ref: InboxRef,
) -> None:
    spy = _Spy()
    request = _request(spy)
    dispatched: list[Any] = []

    class _Dispatcher:
        async def dispatch(self, event: Any, _request: Any) -> None:
            dispatched.append(event)

    token = bind_inbox_context(ref.inbox_id)
    try:
        fire_api_event(
            _Dispatcher(),
            message_type="text",
            result=MessageResult(
                message_id="m1",
                success=True,
                error=None,
                platform=ref.platform,
            ),
            request_payload={},
            recipient=RECIPIENT,
            fastapi_request=request,
        )
        await request.app.state.background_work_tracker.drain(timeout=1)
    finally:
        reset_inbox_context(token)

    assert spy.refs == [ref]
    assert dispatched[0].user_id == f"{ref.platform.value}/{ref.inbox_id}/{RECIPIENT}"


@pytest.mark.parametrize("ref", [WA, IG])
async def test_awaited_api_event_dependency_passes_the_same_ref(ref: InboxRef) -> None:
    spy = _Spy()
    request = _request(spy)
    dispatcher = AsyncMock()

    token = bind_inbox_context(ref.inbox_id)
    try:
        await dispatch_api_message_event(
            dispatcher=dispatcher,
            message_type="text",
            result=MessageResult(
                message_id="m1", success=True, error=None, platform=ref.platform
            ),
            request_payload={},
            recipient=RECIPIENT,
            request=request,
        )
        await request.app.state.background_work_tracker.drain(timeout=1)
    finally:
        reset_inbox_context(token)

    assert spy.refs == [ref]


async def test_platforms_sharing_a_raw_id_and_numeric_recipient_stay_apart() -> None:
    spy = _Spy()
    builder = _builder(spy)

    whatsapp_user = await builder.canonical_user(WA, RECIPIENT)
    instagram_user = await builder.canonical_user(IG, RECIPIENT)

    assert whatsapp_user != instagram_user
    assert (
        builder.cache_factory(WA, whatsapp_user).inbox_id
        != builder.cache_factory(IG, instagram_user).inbox_id
    )


async def test_two_whatsapp_inboxes_resolve_independently() -> None:
    builder = _builder(_Spy())

    assert await builder.canonical_user(WA, RECIPIENT) != await builder.canonical_user(
        WA_OTHER, RECIPIENT
    )


async def test_api_and_scheduled_paths_agree_on_the_canonical_user() -> None:
    spy = _Spy()

    scheduled = await _builder(spy).canonical_user(WA, RECIPIENT)
    service = await get_handler_state_service(_request(spy), _context(WA))
    api_state = await service._resolve_user_id(RECIPIENT, None)
    api_event = await resolve_event_user_id(
        RECIPIENT, None, _request(spy), inbox_ref=WA
    )

    assert scheduled == api_state == api_event


async def test_an_explicit_user_bypasses_the_resolver() -> None:
    spy = _Spy()
    service = await get_handler_state_service(_request(spy), _context(WA))

    await service.set_handler_state(RECIPIENT, "flow", 60, user_id="canonical")
    event_user = await resolve_event_user_id(
        RECIPIENT, "canonical", _request(spy), inbox_ref=WA
    )

    assert spy.refs == []
    assert event_user == "canonical"


async def test_without_a_resolver_the_recipient_passes_through() -> None:
    assert await _builder(None).canonical_user(WA, RECIPIENT) == RECIPIENT
    assert (
        await PassthroughIdentityResolver().resolve(RECIPIENT, inbox_ref=IG)
        == RECIPIENT
    )
    assert (
        await resolve_event_user_id(RECIPIENT, None, _request(None), inbox_ref=WA)
        == RECIPIENT
    )


async def test_resolver_failures_propagate_on_the_handler_state_path() -> None:
    class _Broken(IIdentityResolver):
        async def resolve(self, recipient: str, *, inbox_ref: InboxRef) -> str:
            raise ConnectionError("identity store down")

    service = await get_handler_state_service(_request(_Broken()), _context(WA))

    with pytest.raises(ConnectionError):
        await service.set_handler_state(RECIPIENT, "flow", 60)
