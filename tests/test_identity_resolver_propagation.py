"""
Tests for IIdentityResolver propagation across resolver-aware Wappa surfaces.

Covers the framework guarantee that, when a host application registers an
``IIdentityResolver`` via ``WappaBuilder.with_identity_resolver``, every
per-user state seam keys cache and pub/sub envelopes by the canonical id —
not by the raw transport recipient. Default behavior (no resolver) keeps
the recipient as the cache key, byte-identical to pre-0.7.0 deployments.
"""

from __future__ import annotations

from typing import Any

import pytest

from wappa.api.services.handler_state_service import HandlerStateService
from wappa.api.services.template_state_service import TemplateStateService
from wappa.domain.events.api_message_event import APIMessageEvent
from wappa.domain.interfaces.identity_resolver import IIdentityResolver
from wappa.messaging.whatsapp.models.template_models import TemplateStateConfig


class _FakeStateCache:
    """In-memory IStateCache stand-in capturing the (user_id, key) tuple."""

    def __init__(self, user_id: str, store: dict[tuple[str, str], dict[str, Any]]):
        self._user_id = user_id
        self._store = store

    async def upsert(
        self,
        handler_name: str = "",
        state_data: dict[str, Any] | None = None,
        ttl: int | None = None,
        # Positional fallback for HandlerStateService.upsert(cache_key, data, ttl)
        *args: Any,
    ) -> bool:
        if args:
            handler_name = handler_name or args[0]
        if isinstance(state_data, int):
            ttl = state_data
            state_data = None
        self._store[(self._user_id, handler_name)] = {
            "data": state_data or {},
            "ttl": ttl,
        }
        return True

    async def get(self, handler_name: str) -> dict[str, Any] | None:
        entry = self._store.get((self._user_id, handler_name))
        return entry["data"] if entry else None

    async def delete(self, handler_name: str) -> int:
        return 1 if self._store.pop((self._user_id, handler_name), None) else 0

    async def exists(self, handler_name: str) -> bool:
        return (self._user_id, handler_name) in self._store


class _RecordingCacheFactory:
    """Minimal ICacheFactory that records the user_id used per create_*_cache call."""

    def __init__(self):
        self.store: dict[tuple[str, str], dict[str, Any]] = {}
        self.observed_user_ids: list[str] = []

    def create_state_cache(self, user_id: str | None = None, **_):
        assert user_id is not None, "callers must pass user_id explicitly in tests"
        self.observed_user_ids.append(user_id)
        return _FakeStateCache(user_id, self.store)


class _PrefixResolver(IIdentityResolver):
    """Test resolver that maps any recipient to ``CO.<recipient>``."""

    async def resolve(self, recipient: str) -> str:
        return f"CO.{recipient}"


# ---------------------------------------------------------------------------
# HandlerStateService
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handler_state_default_passthrough_uses_recipient():
    factory = _RecordingCacheFactory()
    service = HandlerStateService(factory)  # default = PassthroughIdentityResolver

    await service.set_handler_state(
        recipient="573168227670", handler_value="flow_a", ttl_seconds=60
    )

    assert factory.observed_user_ids == ["573168227670"]
    assert ("573168227670", "api-handler-flow_a") in factory.store


@pytest.mark.asyncio
async def test_handler_state_custom_resolver_keys_under_canonical_id():
    factory = _RecordingCacheFactory()
    service = HandlerStateService(factory, identity_resolver=_PrefixResolver())

    await service.set_handler_state(
        recipient="573168227670", handler_value="flow_a", ttl_seconds=60
    )

    # Cache must be keyed under the resolver's canonical id, not the phone.
    assert factory.observed_user_ids == ["CO.573168227670"]
    assert ("CO.573168227670", "api-handler-flow_a") in factory.store


@pytest.mark.asyncio
async def test_handler_state_explicit_user_id_bypasses_resolver():
    factory = _RecordingCacheFactory()
    service = HandlerStateService(factory, identity_resolver=_PrefixResolver())

    await service.set_handler_state(
        recipient="573168227670",
        handler_value="flow_a",
        ttl_seconds=60,
        user_id="CO.OVERRIDE",
    )

    # Explicit user_id wins over the resolver.
    assert factory.observed_user_ids == ["CO.OVERRIDE"]
    assert ("CO.OVERRIDE", "api-handler-flow_a") in factory.store


@pytest.mark.asyncio
async def test_handler_state_get_uses_resolved_user_id():
    factory = _RecordingCacheFactory()
    service = HandlerStateService(factory, identity_resolver=_PrefixResolver())

    await service.set_handler_state(
        recipient="573168227670", handler_value="flow_a", ttl_seconds=60
    )

    # Get and exists must scope the same way as set.
    state = await service.get_handler_state("573168227670", "flow_a")
    assert state is not None
    assert state["user_id"] == "CO.573168227670"

    assert await service.handler_state_exists("573168227670", "flow_a") is True


@pytest.mark.asyncio
async def test_handler_state_delete_uses_resolved_user_id():
    factory = _RecordingCacheFactory()
    service = HandlerStateService(factory, identity_resolver=_PrefixResolver())

    await service.set_handler_state(
        recipient="573168227670", handler_value="flow_a", ttl_seconds=60
    )

    deleted = await service.delete_handler_state("573168227670", "flow_a")
    assert deleted is True
    assert ("CO.573168227670", "api-handler-flow_a") not in factory.store


# ---------------------------------------------------------------------------
# TemplateStateService — regression for v0.6.1 contract
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_template_state_default_passthrough_uses_recipient():
    factory = _RecordingCacheFactory()
    service = TemplateStateService(factory)  # default resolver

    cfg = TemplateStateConfig(state_value="human_takeover", ttl_seconds=120)
    ok = await service.set_template_state(
        recipient="573168227670",
        state_config=cfg,
        message_id="wamid.AAA",
        template_name="takeover",
    )

    assert ok is True
    assert factory.observed_user_ids == ["573168227670"]


@pytest.mark.asyncio
async def test_template_state_custom_resolver_keys_under_canonical_id():
    factory = _RecordingCacheFactory()
    service = TemplateStateService(factory, identity_resolver=_PrefixResolver())

    cfg = TemplateStateConfig(state_value="human_takeover", ttl_seconds=120)
    await service.set_template_state(
        recipient="573168227670",
        state_config=cfg,
        message_id="wamid.AAA",
        template_name="takeover",
    )

    assert factory.observed_user_ids == ["CO.573168227670"]


# ---------------------------------------------------------------------------
# APIMessageEvent + dispatch helpers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_event_user_id_explicit_wins():
    from wappa.api.utils.event_decorators import resolve_event_user_id

    user_id = await resolve_event_user_id(
        recipient="573168227670",
        explicit_user_id="CO.EXPLICIT",
        fastapi_request=None,
    )
    assert user_id == "CO.EXPLICIT"


@pytest.mark.asyncio
async def test_resolve_event_user_id_uses_app_state_resolver():
    from types import SimpleNamespace

    from wappa.api.utils.event_decorators import resolve_event_user_id

    fake_request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(identity_resolver=_PrefixResolver()))
    )

    user_id = await resolve_event_user_id(
        recipient="573168227670",
        explicit_user_id=None,
        fastapi_request=fake_request,
    )
    assert user_id == "CO.573168227670"


@pytest.mark.asyncio
async def test_resolve_event_user_id_default_is_recipient():
    from types import SimpleNamespace

    from wappa.api.utils.event_decorators import resolve_event_user_id

    fake_request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))

    user_id = await resolve_event_user_id(
        recipient="573168227670",
        explicit_user_id=None,
        fastapi_request=fake_request,
    )
    assert user_id == "573168227670"


# ---------------------------------------------------------------------------
# Pub/sub envelope shape
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_publish_api_notification_uses_event_user_id(monkeypatch):
    """publish_api_notification keys the envelope by event.user_id."""
    from wappa.core.pubsub import handlers as pubsub_handlers

    captured: dict[str, Any] = {}

    async def fake_publish(event_type, tenant, user_id, platform, data):
        captured.update(
            event_type=event_type,
            tenant=tenant,
            user_id=user_id,
            platform=platform,
            data=data,
        )
        return 1

    monkeypatch.setattr(pubsub_handlers, "publish_notification", fake_publish)

    event = APIMessageEvent(
        message_type="text",
        message_id="wamid.X",
        recipient="573168227670",
        user_id="CO.573168227670",
        request_payload={"message": "hi", "recipient": "573168227670"},
        response_success=True,
        tenant_id="tenant-1",
    )

    await pubsub_handlers.publish_api_notification(event)

    assert captured["user_id"] == "CO.573168227670"
    assert captured["data"]["recipient"] == "573168227670"
