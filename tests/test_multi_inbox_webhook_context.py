"""Authenticated intake, isolation, and all-or-nothing admission (PRDs 3 and 5)."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from fastapi import HTTPException
from pydantic import SecretStr

from wappa.api.controllers.webhook_controller import WebhookController
from wappa.core.config.meta_application import MetaApplicationConfig
from wappa.core.dispatch.context_builder import RuntimeCapabilities
from wappa.core.events.event_dispatcher import WappaEventDispatcher
from wappa.core.events.event_handler import WappaEventHandler
from wappa.core.factory.inbox_assembly import InboxRuntimeConfiguration
from wappa.core.inbound import (
    InboundRuntime,
    MetaCallbackAuthenticator,
    PayloadInboxMismatchError,
    RoutedWebhookDelivery,
)
from wappa.core.lifecycle import BackgroundWorkTracker, SessionLifecycle
from wappa.core.logging.context import get_current_inbox_context
from wappa.domain.inbox import (
    IInboxCredentialResolver,
    InboxDirectoryUnavailableError,
    InboxNotFoundError,
    InboxRef,
    InboxRoutingMode,
    PlatformAccountRef,
    ResolvedInboxCredentials,
)
from wappa.webhooks import InboundMessageWebhook, SystemWebhook

INBOX_1 = "111111111111111"
INBOX_2 = "222222222222222"
WABA_1 = "1111111111"
WABA_2 = "2222222222"
APP_SECRET = SecretStr("meta-app-secret")
META_CONFIG = MetaApplicationConfig(
    app_secret=APP_SECRET, whatsapp_webhook_verify_token=SecretStr("verify")
)


class _Resolver(IInboxCredentialResolver):
    def __init__(self, memberships: dict[str, str] | None = None) -> None:
        self.memberships = memberships or {INBOX_1: WABA_1, INBOX_2: WABA_2}
        self.calls: list[str] = []
        self.unavailable = False

    async def resolve_credentials(
        self, inbox_ref: InboxRef
    ) -> ResolvedInboxCredentials:
        self.calls.append(inbox_ref.inbox_id)
        if self.unavailable:
            raise InboxDirectoryUnavailableError("credential database unavailable")
        waba = self.memberships.get(inbox_ref.inbox_id)
        if waba is None:
            raise InboxNotFoundError(inbox_ref)
        return ResolvedInboxCredentials(
            inbox_ref=inbox_ref,
            account_ref=PlatformAccountRef.whatsapp(waba),
            access_token=SecretStr(f"token-inbox-{inbox_ref.inbox_id[0]}"),
            credential_version=1,
        )

    async def list_inbox_refs_for_platform_account(
        self, account_ref: PlatformAccountRef
    ) -> tuple[InboxRef, ...]:
        if self.unavailable:
            raise InboxDirectoryUnavailableError("credential database unavailable")
        return tuple(
            sorted(
                InboxRef.whatsapp(inbox_id)
                for inbox_id, waba in self.memberships.items()
                if waba == account_ref.platform_account_id
            )
        )


class _RecordingHTTPSession:
    def __init__(self) -> None:
        self.posts: list[dict[str, Any]] = []

    async def post(
        self,
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
    ) -> httpx.Response:
        payload = json or data or {}
        self.posts.append({"url": url, "headers": headers, "payload": payload})
        recipient = str(payload.get("recipient") or payload.get("to") or "")
        contact = {"input": recipient}
        if recipient.startswith("CO."):
            contact["user_id"] = recipient
        else:
            contact["wa_id"] = recipient
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={
                "messaging_product": "whatsapp",
                "contacts": [contact],
                "messages": [{"id": f"wamid.{len(self.posts)}"}],
            },
        )


class _RecordingHandler(WappaEventHandler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[dict[str, Any]] = []

    async def process_message(self, webhook: InboundMessageWebhook) -> None:
        assert self.inbox_id and self.user_id and self.messenger and self.cache_factory
        state_cache = self.cache_factory.create_state_cache()
        await state_cache.upsert(
            "multi-inbox-context",
            {"handler_inbox_id": self.inbox_id, "user_id": self.user_id},
        )
        cached_state = await state_cache.get("multi-inbox-context")
        send_result = await self.messenger.send_text(
            text=f"reply from {self.inbox_id}", recipient=webhook.user.user_id
        )
        self.records.append(
            {
                "handler_inbox_id": self.inbox_id,
                "handler_user_id": self.user_id,
                "webhook_inbox_id": webhook.inbox.inbox_id,
                "cache_inbox_id": state_cache.inbox,
                "cached_state": cached_state,
                "messenger_inbox_id": self.messenger.inbox_id,
                "send_result_inbox_id": send_result.inbox_id,
                "context_inbox_id": get_current_inbox_context(),
            }
        )


class _SystemRecordingHandler(WappaEventHandler):
    def __init__(self) -> None:
        super().__init__()
        self.inboxes: list[str] = []

    async def process_message(self, webhook: InboundMessageWebhook) -> None:
        return None

    async def process_system_webhook(self, webhook: SystemWebhook) -> None:
        assert webhook.inbox.inbox_id == self.inbox_id
        self.inboxes.append(self.inbox_id or "")


def _message_payload(
    *, inbox_id: str, waba_id: str, user_id: str, phone_number: str, message_id: str
) -> dict[str, Any]:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": waba_id,
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "15551234567",
                                "phone_number_id": inbox_id,
                            },
                            "contacts": [
                                {
                                    "wa_id": phone_number,
                                    "user_id": user_id,
                                    "profile": {"name": f"User {user_id}"},
                                }
                            ],
                            "messages": [
                                {
                                    "from": phone_number,
                                    "from_user_id": user_id,
                                    "id": message_id,
                                    "timestamp": "1710000000",
                                    "type": "text",
                                    "text": {"body": "hello"},
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }


def _capabilities(
    resolver: IInboxCredentialResolver, session: Any
) -> RuntimeCapabilities:
    return RuntimeCapabilities(
        session_provider=lambda: session,
        media_download_client_provider=lambda: session,
        credential_resolver=resolver,
        messenger_middleware=[],
        cache_type="memory",
        background_work_tracker=BackgroundWorkTracker(),
    )


def _request(resolver: IInboxCredentialResolver, session: Any) -> Any:
    return SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                session_lifecycle=SessionLifecycle(session),
                inbox_runtime=InboxRuntimeConfiguration(
                    mode=InboxRoutingMode.EXPLICIT, credential_resolver=resolver
                ),
                meta_application_config=META_CONFIG,
                messenger_middleware=[],
                wappa_cache_type="memory",
                background_work_tracker=BackgroundWorkTracker(),
            )
        )
    )


def _signed(payload: dict[str, Any]) -> tuple[bytes, str]:
    body = json.dumps(payload).encode()
    return body, MetaCallbackAuthenticator(APP_SECRET).sign(body)


async def _delivery(
    resolver: _Resolver, inbox_id: str, waba_id: str, payload: dict[str, Any]
) -> RoutedWebhookDelivery:
    ref = InboxRef.whatsapp(inbox_id)
    return RoutedWebhookDelivery(
        inbox_ref=ref,
        account_ref=PlatformAccountRef.whatsapp(waba_id),
        credentials=await resolver.resolve_credentials(ref),
        payload=payload,
    )


# ── Dispatch Context isolation ─────────────────────────────────────────────


async def test_webhooks_from_multiple_inboxes_get_isolated_handler_contexts() -> None:
    handler = _RecordingHandler()
    runtime = InboundRuntime(WappaEventDispatcher(handler))
    resolver = _Resolver()
    session = _RecordingHTTPSession()
    capabilities = _capabilities(resolver, session)

    for inbox_id, waba, user, phone, mid in (
        (INBOX_1, WABA_1, "CO.USER111", "573001111111", "wamid.0000000001"),
        (INBOX_2, WABA_2, "CO.USER222", "573002222222", "wamid.0000000002"),
    ):
        delivery = await _delivery(
            resolver,
            inbox_id,
            waba,
            _message_payload(
                inbox_id=inbox_id,
                waba_id=waba,
                user_id=user,
                phone_number=phone,
                message_id=mid,
            ),
        )
        context = await runtime.build_dispatch_context(
            delivery, dependencies=capabilities
        )
        await runtime.dispatch(context)

    assert [r["handler_inbox_id"] for r in handler.records] == [INBOX_1, INBOX_2]
    assert [r["cache_inbox_id"] for r in handler.records] == [INBOX_1, INBOX_2]
    assert [r["messenger_inbox_id"] for r in handler.records] == [INBOX_1, INBOX_2]
    assert [r["send_result_inbox_id"] for r in handler.records] == [INBOX_1, INBOX_2]
    assert [r["context_inbox_id"] for r in handler.records] == [INBOX_1, INBOX_2]
    assert [r["cached_state"]["handler_inbox_id"] for r in handler.records] == [
        INBOX_1,
        INBOX_2,
    ]
    assert [p["headers"]["Authorization"] for p in session.posts] == [
        "Bearer token-inbox-1",
        "Bearer token-inbox-2",
    ]
    assert [p["url"].rsplit("/", 2)[-2] for p in session.posts] == [INBOX_1, INBOX_2]


async def test_building_contexts_does_not_leave_ambient_inbox_bound() -> None:
    runtime = InboundRuntime(WappaEventDispatcher(_RecordingHandler()))
    resolver = _Resolver()
    capabilities = _capabilities(resolver, _RecordingHTTPSession())
    delivery = await _delivery(
        resolver,
        INBOX_1,
        WABA_1,
        _message_payload(
            inbox_id=INBOX_1,
            waba_id=WABA_1,
            user_id="CO.U",
            phone_number="5730",
            message_id="wamid.0000000009",
        ),
    )

    await runtime.build_dispatch_context(delivery, dependencies=capabilities)

    assert get_current_inbox_context() is None


async def test_inbound_runtime_rejects_payload_inbox_mismatch() -> None:
    runtime = InboundRuntime(WappaEventDispatcher(_RecordingHandler()))
    resolver = _Resolver()
    capabilities = _capabilities(resolver, _RecordingHTTPSession())
    delivery = await _delivery(
        resolver,
        INBOX_1,
        WABA_1,
        _message_payload(
            inbox_id=INBOX_2,
            waba_id=WABA_2,
            user_id="CO.U",
            phone_number="5730",
            message_id="wamid.0000000009",
        ),
    )

    with pytest.raises(
        PayloadInboxMismatchError, match="does not match routed inbox_id"
    ):
        await runtime.build_dispatch_context(delivery, dependencies=capabilities)


# ── Controller: authentication, status matrix, admission ───────────────────


async def _process(
    controller: WebhookController,
    request: Any,
    payload: dict[str, Any] | bytes,
    *,
    signature: str | None = "valid",
) -> Any:
    if isinstance(payload, bytes):
        body = payload
        sig = (
            MetaCallbackAuthenticator(APP_SECRET).sign(body)
            if signature == "valid"
            else signature
        )
    else:
        body, computed = _signed(payload)
        sig = computed if signature == "valid" else signature
    return await controller.process_webhook(
        request=request, platform="whatsapp", body=body, signature=sig
    )


async def test_controller_routes_from_payload_and_accepts() -> None:
    handler = _RecordingHandler()
    controller = WebhookController(WappaEventDispatcher(handler))
    request = _request(_Resolver(), _RecordingHTTPSession())

    result = await _process(
        controller,
        request,
        _message_payload(
            inbox_id=INBOX_2,
            waba_id=WABA_2,
            user_id="CO.USER222",
            phone_number="5730",
            message_id="wamid.0000000009",
        ),
    )
    await request.app.state.background_work_tracker.drain(timeout=1)

    assert result == {"status": "accepted"}
    assert handler.records[0]["handler_inbox_id"] == INBOX_2


@pytest.mark.parametrize("signature", [None, "", "sha256=deadbeef", "wrong"])
async def test_unauthenticated_posts_are_401_before_any_directory_call(
    signature: str | None,
) -> None:
    resolver = _Resolver()
    controller = WebhookController(WappaEventDispatcher(_RecordingHandler()))
    request = _request(resolver, _RecordingHTTPSession())

    with pytest.raises(HTTPException) as exc_info:
        await _process(controller, request, b"not even json", signature=signature)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Unauthorized"
    assert resolver.calls == []
    assert request.app.state.background_work_tracker.active_count == 0


async def test_signature_failures_are_indistinguishable() -> None:
    controller = WebhookController(WappaEventDispatcher(_RecordingHandler()))
    request = _request(_Resolver(), _RecordingHTTPSession())
    details = set()
    for signature in (None, "sha1=abc", "sha256=" + "0" * 64):
        with pytest.raises(HTTPException) as exc_info:
            await _process(controller, request, b"{}", signature=signature)
        details.add((exc_info.value.status_code, exc_info.value.detail))
    assert details == {(401, "Unauthorized")}


@pytest.mark.parametrize(
    "body", [b"[]", b"null", b'"text"', b"42", b"true", b"{not json"]
)
async def test_non_object_roots_are_400_after_authentication(body: bytes) -> None:
    controller = WebhookController(WappaEventDispatcher(_RecordingHandler()))
    request = _request(_Resolver(), _RecordingHTTPSession())

    with pytest.raises(HTTPException) as exc_info:
        await _process(controller, request, body)

    assert exc_info.value.status_code == 400


async def test_unknown_payload_inbox_is_400_not_401() -> None:
    controller = WebhookController(WappaEventDispatcher(_RecordingHandler()))
    request = _request(_Resolver(), _RecordingHTTPSession())

    with pytest.raises(HTTPException) as exc_info:
        await _process(
            controller,
            request,
            _message_payload(
                inbox_id="999999999999999",
                waba_id="9999",
                user_id="CO.U",
                phone_number="5730",
                message_id="wamid.0000000009",
            ),
        )

    assert exc_info.value.status_code == 400


async def test_phone_to_waba_mismatch_is_400_with_no_scheduled_work() -> None:
    handler = _RecordingHandler()
    controller = WebhookController(WappaEventDispatcher(handler))
    request = _request(_Resolver(), _RecordingHTTPSession())

    with pytest.raises(HTTPException) as exc_info:
        await _process(
            controller,
            request,
            _message_payload(
                inbox_id=INBOX_1,
                waba_id=WABA_2,
                user_id="CO.U",
                phone_number="5730",
                message_id="wamid.0000000009",
            ),
        )

    assert exc_info.value.status_code == 400
    assert request.app.state.background_work_tracker.active_count == 0
    assert handler.records == []


async def test_empty_waba_is_400() -> None:
    controller = WebhookController(WappaEventDispatcher(_RecordingHandler()))
    request = _request(_Resolver(), _RecordingHTTPSession())
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {"id": "7777", "changes": [{"field": "account_update", "value": {"x": 1}}]}
        ],
    }

    with pytest.raises(HTTPException) as exc_info:
        await _process(controller, request, payload)

    assert exc_info.value.status_code == 400


async def test_directory_outage_during_routing_is_503() -> None:
    resolver = _Resolver()
    resolver.unavailable = True
    controller = WebhookController(WappaEventDispatcher(_RecordingHandler()))
    request = _request(resolver, _RecordingHTTPSession())

    with pytest.raises(HTTPException) as exc_info:
        await _process(
            controller,
            request,
            _message_payload(
                inbox_id=INBOX_1,
                waba_id=WABA_1,
                user_id="CO.U",
                phone_number="5730",
                message_id="wamid.0000000009",
            ),
        )

    assert exc_info.value.status_code == 503
    assert request.app.state.background_work_tracker.active_count == 0


async def test_invalid_later_change_schedules_none_of_the_batch() -> None:
    handler = _RecordingHandler()
    controller = WebhookController(WappaEventDispatcher(handler))
    request = _request(_Resolver(), _RecordingHTTPSession())
    valid = _message_payload(
        inbox_id=INBOX_1,
        waba_id=WABA_1,
        user_id="CO.USER111",
        phone_number="5730",
        message_id="wamid.000000000a",
    )
    invalid = _message_payload(
        inbox_id="999999999999999",
        waba_id="9999",
        user_id="CO.USER999",
        phone_number="5739",
        message_id="wamid.000000000b",
    )
    batch = {
        "object": "whatsapp_business_account",
        "entry": [*valid["entry"], *invalid["entry"]],
    }

    with pytest.raises(HTTPException) as exc_info:
        await _process(controller, request, batch)

    assert exc_info.value.status_code == 400
    assert request.app.state.background_work_tracker.active_count == 0
    assert handler.records == []


async def test_waba_only_event_fans_out_with_isolated_inbox_contexts() -> None:
    handler = _SystemRecordingHandler()
    controller = WebhookController(WappaEventDispatcher(handler))
    request = _request(
        _Resolver({INBOX_1: WABA_1, INBOX_2: WABA_1}), _RecordingHTTPSession()
    )
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": WABA_1,
                "changes": [
                    {
                        "field": "account_offboarded",
                        "value": {
                            "waba_id": WABA_1,
                            "timestamp": 1710000000,
                            "reason": "USER_INITIATED",
                        },
                    }
                ],
            }
        ],
    }

    result = await _process(controller, request, payload)
    await request.app.state.background_work_tracker.drain(timeout=1)

    assert result == {"status": "accepted"}
    assert handler.inboxes == [INBOX_1, INBOX_2]


async def test_missing_meta_configuration_is_503() -> None:
    controller = WebhookController(WappaEventDispatcher(_RecordingHandler()))
    request = _request(_Resolver(), _RecordingHTTPSession())
    request.app.state.meta_application_config = None

    with pytest.raises(HTTPException) as exc_info:
        await _process(controller, request, b"{}")

    assert exc_info.value.status_code == 503


# ── nothing observes the payload before authentication ─────────────────────


async def test_no_payload_content_is_logged_before_authentication(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A rejected callback must leave no trace of its body in the logs.

    The structural proof (no directory call, no scheduling) does not stop a
    future debug log of the raw body from landing before the signature check.
    """
    import logging

    secret_marker = "s3cret-message-body-marker"
    payload = _message_payload(
        inbox_id=INBOX_1,
        waba_id=WABA_1,
        user_id="CO.USER111",
        phone_number="573001111111",
        message_id="wamid.0000000042",
    )
    payload["entry"][0]["changes"][0]["value"]["messages"][0]["text"] = {
        "body": secret_marker
    }
    resolver = _Resolver()
    controller = WebhookController(WappaEventDispatcher(_RecordingHandler()))
    request = _request(resolver, _RecordingHTTPSession())

    with caplog.at_level(logging.DEBUG), pytest.raises(HTTPException) as exc_info:
        await _process(controller, request, payload, signature="sha256=" + "0" * 64)

    assert exc_info.value.status_code == 401
    assert resolver.calls == []
    assert request.app.state.background_work_tracker.active_count == 0
    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert secret_marker not in logged
    assert "573001111111" not in logged


async def test_the_app_secret_never_appears_in_logs_or_responses(
    caplog: pytest.LogCaptureFixture,
) -> None:
    import logging

    controller = WebhookController(WappaEventDispatcher(_RecordingHandler()))
    request = _request(_Resolver(), _RecordingHTTPSession())

    with caplog.at_level(logging.DEBUG), pytest.raises(HTTPException) as exc_info:
        await _process(controller, request, b"{}", signature=None)

    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert APP_SECRET.get_secret_value() not in logged
    assert APP_SECRET.get_secret_value() not in str(exc_info.value.detail)
