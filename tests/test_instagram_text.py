"""First Instagram contract: signed HTTP callback -> handler -> native text send."""

import json
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from pydantic import SecretStr, ValidationError

import wappa.core.inbound.runtime as inbound_runtime
from wappa import WappaEventHandler
from wappa.api.routes.webhooks import create_webhook_router
from wappa.core.config.meta_application import MetaApplicationConfig
from wappa.core.events import WappaEventDispatcher
from wappa.core.inbound import MetaCallbackAuthenticator, PayloadRoutingError
from wappa.core.lifecycle import BackgroundWorkTracker, SessionLifecycle
from wappa.core.security import CredentialCodec
from wappa.domain.inbox import (
    InboxCredentialService,
    InboxRef,
    PlatformAccountRef,
    parse_inbox_credential_record,
)
from wappa.domain.inbox.errors import InboxNotFoundError
from wappa.domain.inbox.ports import IInboxCredentialResolver, ResolvedInboxCredentials
from wappa.domain.interfaces.user_data_requests import IUserDataRequests
from wappa.messaging import (
    DeliveryAddresses,
    DirectMessage,
    MessengerPipeline,
    UnsupportedOperationError,
)
from wappa.messaging.instagram.messenger import InstagramMessengerAdapter
from wappa.schemas.core.types import PlatformType
from wappa.webhooks import (
    EchoOrigin,
    InboundMessageWebhook,
    SystemEventType,
    SystemWebhook,
)
from wappa.webhooks.instagram.processor import InstagramWebhookProcessor
from wappa.webhooks.instagram.routing import route_instagram_payload

# The routed Inbox the runtime passes to translate().
INBOX_ID = "routed-inbox"

SECRET = SecretStr("test-meta-secret")
ACCOUNT = "17890001"


def event(user="12345", **parts):
    return {
        "sender": {"id": user},
        "recipient": {"id": ACCOUNT},
        "timestamp": 1793710000123,
        **(parts or {"message": {"mid": "ig.mid", "text": " hello 🌎 "}}),
    }


def payload(*events, account=ACCOUNT):
    return {
        "object": "instagram",
        "entry": [{"id": account, "messaging": list(events)}],
    }


class Resolver(IInboxCredentialResolver):
    def __init__(self):
        self.calls = []

    async def resolve_credentials(self, ref):
        self.calls.append(ref)
        if ref.inbox_id != ACCOUNT:
            raise InboxNotFoundError(ref)
        return ResolvedInboxCredentials(
            inbox_ref=ref,
            account_ref=PlatformAccountRef(
                platform=ref.platform, platform_account_id=ref.inbox_id
            ),
            access_token=SecretStr("test-account-token"),
            credential_version=1,
        )

    async def list_inbox_refs_for_platform_account(self, ref):
        return ()


class Echo(WappaEventHandler):
    def __init__(self):
        super().__init__()
        self.seen = []
        self.system = []
        self.echoes = []

    async def process_outbound_echo(self, webhook):
        self.echoes.append(webhook)

    async def process_message(self, webhook):
        await self.messenger.send_text(
            webhook.get_message_text(),
            target=DirectMessage(
                inbox_ref=self.inbox_ref,
                addresses=DeliveryAddresses.of(webhook.user.user_id),
            ),
        )

    async def process_status(self, webhook):
        self.seen.append(webhook)

    async def process_system_webhook(self, webhook):
        self.system.append(webhook)


@pytest.mark.asyncio
async def test_real_http_callback_routes_each_user_and_does_not_reply_to_echo_or_seen(
    monkeypatch,
):
    # Short settle window: the echo of Wappa's own send ("sent.mid") races the
    # send call, as in production.
    monkeypatch.setattr(inbound_runtime, "ECHO_SETTLE_DELAYS_SECONDS", (0.05, 0.2))
    outgoing = []

    def transport(request):
        outgoing.append(request)
        return httpx.Response(
            200,
            json={
                "recipient_id": json.loads(request.content)["recipient"]["id"],
                "message_id": "sent.mid",
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as provider:
        resolver = Resolver()
        handler = Echo()
        tracker = BackgroundWorkTracker()
        app = FastAPI()
        app.include_router(create_webhook_router(WappaEventDispatcher(handler)))
        app.state.meta_application_config = MetaApplicationConfig(
            app_secret=SECRET, whatsapp_webhook_verify_token=SecretStr("verify")
        )
        app.state.session_lifecycle = SessionLifecycle(provider)
        app.state.inbox_runtime = SimpleNamespace(credential_resolver=resolver)
        app.state.background_work_tracker = tracker
        app.state.messenger_middleware = []
        app.state.wappa_cache_type = "memory"
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://test"
        ) as client:
            path = "/webhook/inboxes/instagram"
            challenge = await client.get(
                path,
                params={
                    "hub.mode": "subscribe",
                    "hub.verify_token": "verify",
                    "hub.challenge": "123",
                },
            )
            assert challenge.status_code == 200 and challenge.text == "123"
            assert resolver.calls == []
            bad = await client.post(path, content=b"not json")
            assert bad.status_code == 401 and resolver.calls == []
            body = json.dumps(
                payload(
                    event(),
                    event("67890"),
                    event(read={"mid": "sent.mid"}),
                    event(
                        message={"mid": "echo.mid", "text": "hello", "is_echo": True}
                    ),
                    event(
                        message={"mid": "sent.mid", "text": "hello", "is_echo": True}
                    ),
                )
            ).encode()
            response = await client.post(
                path,
                content=body,
                headers={
                    "X-Hub-Signature-256": MetaCallbackAuthenticator(SECRET).sign(body)
                },
            )
            assert response.status_code == 200, response.text
            await tracker.drain()
            assert len(outgoing) == 2
            assert [json.loads(r.content)["recipient"]["id"] for r in outgoing] == [
                "12345",
                "67890",
            ]
            assert all(
                json.loads(r.content)["message"]["text"] == " hello 🌎 "
                for r in outgoing
            )
            assert all(r.url.path == f"/v26.0/{ACCOUNT}/messages" for r in outgoing)
            assert all(
                r.headers["Authorization"] == "Bearer test-account-token"
                for r in outgoing
            )
            assert handler.seen[0].recipient_id == "12345"
            assert handler.seen[0].recipient_phone_id == ""
            # Fixed filter (ADR-0023): the echo of Wappa's own send is dropped;
            # the message sent from the Instagram app arrives typed.
            assert [e.message_id for e in handler.echoes] == ["echo.mid"]
            assert handler.echoes[0].origin is EchoOrigin.BUSINESS_APP
            assert handler.echoes[0].get_text() == "hello"
            assert handler.system == []
        await app.state.session_lifecycle.close()


@pytest.mark.asyncio
async def test_processor_has_native_identity_and_preserves_text():
    parsed = await InstagramWebhookProcessor().translate(
        payload(event()), inbox_id=INBOX_ID
    )
    assert isinstance(parsed, InboundMessageWebhook)
    assert parsed.user.user_id == "12345"
    assert parsed.user.phone_number == "" and parsed.user.bsuid is None
    assert parsed.get_message_text() == " hello 🌎 "
    assert parsed.inbox.display_address is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ({"mid": "x", "text": "deleted", "is_deleted": True}, "MessageUpdateWebhook"),
        (
            {"mid": "x", "text": "choice", "quick_reply": {"payload": "x"}},
            "InboundMessageWebhook",
        ),
        ({"mid": "x", "attachments": [{"type": "image"}]}, "InboundMessageWebhook"),
        ({"mid": "x", "is_unsupported": True}, "SystemWebhook"),
        ({"mid": "x", "attachments": [{"type": "ephemeral"}]}, "SystemWebhook"),
    ],
)
async def test_nontext_events_never_enter_echo_lane(message, expected):
    parsed = await InstagramWebhookProcessor().translate(
        payload(event(message=message)), inbox_id=INBOX_ID
    )
    assert type(parsed).__name__ == expected
    if isinstance(parsed, SystemWebhook):
        assert parsed.system_event_type is SystemEventType.UNSUPPORTED_EVENT
    if isinstance(parsed, InboundMessageWebhook):
        assert parsed.message.message_type.value != "text"


@pytest.mark.asyncio
async def test_routing_rejects_wrong_platform_and_conflicting_recipient():
    resolver = Resolver()
    with pytest.raises(PayloadRoutingError):
        await route_instagram_payload({"object": "page", "entry": []}, resolver)
    e = event()
    e["recipient"] = {"id": "different"}
    with pytest.raises(PayloadRoutingError):
        await route_instagram_payload(payload(e), resolver)
    assert resolver.calls == []


@pytest.mark.asyncio
async def test_unknown_later_account_keeps_the_registered_delivery():
    resolver = Resolver()
    batch = payload(event())
    batch["entry"].append(
        {"id": "unregistered", "messaging": [event(user="unregistered")]}
    )
    deliveries = await route_instagram_payload(batch, resolver)
    assert len(deliveries) == 1
    assert deliveries[0].inbox_ref.inbox_id == ACCOUNT


@pytest.mark.asyncio
async def test_target_and_unsupported_operations_make_no_http_call():
    calls = []
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: calls.append(r))
    ) as client:
        ref = InboxRef(platform=PlatformType.INSTAGRAM, inbox_id=ACCOUNT)
        raw = InstagramMessengerAdapter(
            inbox_ref=ref,
            access_token=SecretStr("test"),
            session_provider=lambda: client,
            graph_api_version="v26.0",
            graph_base_url="https://graph.facebook.com",
        )
        messenger = MessengerPipeline(raw)
        other = DirectMessage(
            inbox_ref=InboxRef.whatsapp(ACCOUNT),
            addresses=DeliveryAddresses.of("12345"),
        )
        with pytest.raises(ValueError, match="different Inbox"):
            await messenger.send_text("hello", target=other)
        target = DirectMessage(inbox_ref=ref, addresses=DeliveryAddresses.of("12345"))
        with pytest.raises(UnsupportedOperationError, match="IUserDataRequests"):
            messenger.require_capability(IUserDataRequests)
        assert target.inbox_ref == ref
        assert calls == []


def test_instagram_encrypted_record_roundtrip_rotation_and_deactivation():
    service = InboxCredentialService(CredentialCodec(CredentialCodec.generate_key()))
    ref = InboxRef(platform=PlatformType.INSTAGRAM, inbox_id=ACCOUNT)
    account = PlatformAccountRef(platform=ref.platform, platform_account_id=ACCOUNT)
    record = service.create_active_record(
        inbox_ref=ref, account_ref=account, access_token=SecretStr("test-token")
    )
    assert "test-token" not in json.dumps(record.for_storage())
    assert parse_inbox_credential_record(record.for_storage()) == record
    rotated = service.rotate_active_record(record, access_token=SecretStr("next-token"))
    assert rotated.credential_version == 2
    inactive = service.create_inactive_record(rotated)
    assert not inactive.is_active and "access_token" not in inactive.for_storage()
    with pytest.raises(ValidationError):
        service.create_active_record(
            inbox_ref=ref,
            account_ref=PlatformAccountRef(
                platform=ref.platform, platform_account_id="other"
            ),
            access_token=SecretStr("token"),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,body,expected",
    [
        (
            400,
            {"error": {"code": 190, "message": "do not expose test-account-token"}},
            "190",
        ),
        (429, {"error": {"code": 4}}, "4"),
        (503, {"error": {"code": 2}}, "INDETERMINATE"),
        (200, {}, "INDETERMINATE"),
    ],
)
async def test_send_errors_are_bounded_and_never_retried(status, body, expected):
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(status, json=body)

    ref = InboxRef(platform=PlatformType.INSTAGRAM, inbox_id=ACCOUNT)
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        raw = InstagramMessengerAdapter(
            inbox_ref=ref,
            access_token=SecretStr("test-account-token"),
            session_provider=lambda: client,
            graph_api_version="v26.0",
            graph_base_url="https://graph.facebook.com",
        )
        result = await raw.send_text(
            "hello",
            target=DirectMessage(
                inbox_ref=ref, addresses=DeliveryAddresses.of("12345")
            ),
        )
    assert not result.success and result.error_code == expected
    assert len(requests) == 1
    assert "test-account-token" not in result.model_dump_json()


@pytest.mark.asyncio
async def test_network_timeout_is_indeterminate_without_retry():
    requests = []

    def timeout(request):
        requests.append(request)
        raise httpx.ReadTimeout("test-account-token must not leak", request=request)

    ref = InboxRef(platform=PlatformType.INSTAGRAM, inbox_id=ACCOUNT)
    async with httpx.AsyncClient(transport=httpx.MockTransport(timeout)) as client:
        raw = InstagramMessengerAdapter(
            inbox_ref=ref,
            access_token=SecretStr("test-account-token"),
            session_provider=lambda: client,
            graph_api_version="v26.0",
            graph_base_url="https://graph.facebook.com",
        )
        result = await raw.send_text(
            "hello",
            target=DirectMessage(
                inbox_ref=ref, addresses=DeliveryAddresses.of("12345")
            ),
        )
    assert not result.success and result.error_code == "INDETERMINATE"
    assert len(requests) == 1 and "test-account-token" not in result.model_dump_json()


@pytest.mark.asyncio
async def test_instagram_directory_source_decrypts_and_revokes():
    from wappa.domain.inbox import InboxDirectory
    from wappa.persistence import create_system_table_cache
    from wappa.persistence.inbox_directory import InboxDirectoryTable

    codec = CredentialCodec(CredentialCodec.generate_key())
    service = InboxCredentialService(codec)
    ref = InboxRef(platform=PlatformType.INSTAGRAM, inbox_id="178900099")
    account = PlatformAccountRef(
        platform=ref.platform, platform_account_id=ref.inbox_id
    )

    class Source:
        record = service.create_active_record(
            inbox_ref=ref, account_ref=account, access_token=SecretStr("first")
        )

        async def get_inbox(self, inbox_ref):
            return self.record if inbox_ref == ref else None

        async def list_inboxes_for_platform_account(self, account_ref):
            return (self.record,) if account_ref == account else ()

    source = Source()
    directory = InboxDirectory(
        source=source,
        table=InboxDirectoryTable(create_system_table_cache("memory")),
        codec=codec,
    )
    resolved = await directory.resolve_credentials(ref)
    assert resolved.access_token.get_secret_value() == "first"
    source.record = service.rotate_active_record(
        source.record, access_token=SecretStr("second")
    )
    await directory.refresh_inbox(ref)
    assert (
        await directory.resolve_credentials(ref)
    ).access_token.get_secret_value() == "second"
    source.record = service.create_inactive_record(source.record)
    await directory.deactivate_inbox(ref)
    with pytest.raises(InboxNotFoundError):
        await directory.resolve_credentials(ref)
