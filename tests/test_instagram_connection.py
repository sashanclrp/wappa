"""Inbox Connectors (ADR-0017) and the trusted credential-access seam (offline)."""

import base64
import hashlib
import hmac
import json
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from wappa.connections import (
    ActivationResult,
    ConnectionCancelledError,
    ConnectionGrant,
    ConnectionProviderError,
    ConnectionStateError,
    DiscoveredInbox,
    IInboxConnector,
    InboxReadiness,
    InMemoryConnectionIntentStore,
    InstagramConnector,
    InstagramSubscriptions,
    MetaLoginConfig,
    WhatsAppConnector,
    parse_signed_request,
)
from wappa.connections.contract import build_record
from wappa.connections.instagram import FieldSubscriptionOutcome
from wappa.core.security import CredentialCodec
from wappa.domain.inbox import (
    InboxCredentialAccess,
    InboxCredentialService,
    InboxRef,
    PlatformAccountRef,
)
from wappa.domain.inbox.errors import InboxNotFoundError
from wappa.domain.inbox.ports import IInboxCredentialResolver, ResolvedInboxCredentials
from wappa.schemas.core.types import PlatformType

CONFIG = MetaLoginConfig(
    app_id="111",
    app_secret=SecretStr("app-secret"),
    config_id="cfg-1",
    redirect_uri="https://host.example/connect/instagram/callback",
)


class Clock:
    def __init__(self):
        self.now = 1_800_000_000.0

    def __call__(self):
        return self.now


def provider(
    requests,
    *,
    scopes=("instagram_basic", "instagram_manage_messages"),
    reject_edit=True,
):
    def handler(request):
        requests.append(request)
        path = request.url.path
        params = dict(request.url.params)
        if path.endswith("/oauth/access_token"):
            if params.get("code") == "used":
                return httpx.Response(
                    400, json={"error": {"code": 100, "error_subcode": 36009}}
                )
            return httpx.Response(
                200, json={"access_token": "bisu-token", "token_type": "bearer"}
            )
        if path.endswith("/me/assigned_instagram_accounts"):
            if params.get("after") == "P2":
                return httpx.Response(
                    200, json={"data": [{"id": "1702", "username": "two"}]}
                )
            return httpx.Response(
                200,
                json={
                    "data": [{"id": "1701", "username": "one"}],
                    "paging": {"cursors": {"after": "P2"}, "next": "https://n"},
                },
            )
        if path.endswith("/debug_token"):
            return httpx.Response(
                200,
                json={
                    "data": {
                        "is_valid": True,
                        "scopes": list(scopes),
                        "granular_scopes": [
                            {
                                "scope": "instagram_manage_messages",
                                "target_ids": ["1701"],
                            }
                        ],
                    }
                },
            )
        if path.endswith("/subscribed_apps"):
            fields = params.get("subscribed_fields", "")
            if reject_edit and "message_edit" in fields:
                return httpx.Response(400, json={"error": {"code": 100}})
            return httpx.Response(200, json={"success": True})
        return httpx.Response(404)

    return handler


async def test_full_login_binds_state_discovers_accounts_and_scopes():
    requests = []
    clock = Clock()
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(provider(requests))
    ) as client:
        login = InstagramConnector(
            CONFIG,
            client_provider=lambda: client,
            intent_store=InMemoryConnectionIntentStore(),
            clock=clock,
        )
        request = await login.begin("operator-7")
        query = parse_qs(urlsplit(request.url).query)
        assert urlsplit(request.url).path == "/v26.0/dialog/oauth"
        assert query["config_id"] == ["cfg-1"] and query["state"] == [request.state]
        assert "client_secret" not in request.url
        grant = await login.complete(
            state=request.state, host_subject="operator-7", code="abc#_"
        )
        with pytest.raises(ConnectionStateError, match="already used"):
            await login.complete(
                state=request.state, host_subject="operator-7", code="abc"
            )
    assert grant.access_token.get_secret_value() == "bisu-token"
    assert [i.inbox_ref.inbox_id for i in grant.inboxes] == ["1701", "1702"]
    assert grant.platform is PlatformType.INSTAGRAM
    assert grant.inboxes[0].display_name == "one"
    assert requests[0].url.params["code"] == "abc"
    assert grant.inboxes[0].readiness.conversation_ready
    second = grant.inboxes[1].readiness
    assert not second.conversation_ready and second.missing_required_scopes == (
        "instagram_manage_messages",
    )
    assert second.features == {"comments": False}
    assert "bisu-token" not in repr(grant)


async def test_state_mismatch_expiry_cancel_and_provider_errors():
    requests = []
    clock = Clock()
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(provider(requests))
    ) as client:
        login = InstagramConnector(
            CONFIG,
            client_provider=lambda: client,
            intent_store=InMemoryConnectionIntentStore(),
            clock=clock,
        )
        a = await login.begin("operator-a")
        with pytest.raises(ConnectionStateError, match="different operator"):
            await login.complete(state=a.state, host_subject="operator-b", code="x")
        b = await login.begin("operator-a")
        clock.now += 601
        with pytest.raises(ConnectionStateError, match="expired"):
            await login.complete(state=b.state, host_subject="operator-a", code="x")
        c = await login.begin("operator-a")
        with pytest.raises(ConnectionCancelledError):
            await login.complete(
                state=c.state,
                host_subject="operator-a",
                error="access_denied",
                error_reason="user_denied",
            )
        d = await login.begin("operator-a")
        with pytest.raises(ConnectionProviderError) as exc:
            await login.complete(state=d.state, host_subject="operator-a", code="used")
        assert exc.value.code == "100/36009"
        with pytest.raises(ConnectionStateError):
            await login.complete(state=None, host_subject="operator-a", code="x")
    assert all("oauth" not in r.url.path for r in requests[:0])


async def test_subscription_reports_unverified_field_and_restores_core_set():
    requests = []
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(provider(requests))
    ) as client:
        login = InstagramConnector(
            CONFIG,
            client_provider=lambda: client,
            intent_store=InMemoryConnectionIntentStore(),
        )
        result = await login.subscriptions.subscribe("1701", SecretStr("bisu-token"))
    assert result.core_subscribed
    assert result.fields["message_edit"] is FieldSubscriptionOutcome.REJECTED
    assert result.fields["comments"] is FieldSubscriptionOutcome.SUBSCRIBED
    calls = [r.url.params["subscribed_fields"] for r in requests]
    assert len(calls) == 3 and "message_edit" not in calls[-1]
    assert all(r.headers["Authorization"] == "Bearer bisu-token" for r in requests)


def test_record_build_rotation_and_signed_request():
    service = InboxCredentialService(CredentialCodec(CredentialCodec.generate_key()))
    ref = InboxRef(platform=PlatformType.INSTAGRAM, inbox_id="1701")
    account = DiscoveredInbox(
        inbox_ref=ref,
        account_ref=PlatformAccountRef(
            platform=PlatformType.INSTAGRAM, platform_account_id="1701"
        ),
        readiness=InboxReadiness(conversation_ready=True),
    )
    record = build_record(service, account, SecretStr("t1"))
    rotated = build_record(service, account, SecretStr("t2"), previous=record)
    assert rotated.credential_version == 2
    with pytest.raises(ValueError, match="inactive"):
        build_record(
            service,
            account,
            SecretStr("t3"),
            previous=service.create_inactive_record(rotated),
        )
    payload = (
        base64.urlsafe_b64encode(
            json.dumps({"algorithm": "HMAC-SHA256", "user_id": "9"}).encode()
        )
        .decode()
        .rstrip("=")
    )
    sig = (
        base64.urlsafe_b64encode(
            hmac.new(b"app-secret", payload.encode(), hashlib.sha256).digest()
        )
        .decode()
        .rstrip("=")
    )
    assert (
        parse_signed_request(f"{sig}.{payload}", SecretStr("app-secret"))["user_id"]
        == "9"
    )
    with pytest.raises(ConnectionStateError):
        parse_signed_request(f"{sig}.{payload}", SecretStr("other"))


class Resolver(IInboxCredentialResolver):
    def __init__(self):
        self.version = 1
        self.active = True

    async def resolve_credentials(self, ref):
        if not self.active:
            raise InboxNotFoundError(ref)
        return ResolvedInboxCredentials(
            inbox_ref=ref,
            account_ref=PlatformAccountRef(
                platform=ref.platform, platform_account_id=ref.inbox_id
            ),
            access_token=SecretStr(f"token-v{self.version}"),
            credential_version=self.version,
        )

    async def list_inbox_refs_for_platform_account(self, ref):
        return ()


async def test_trusted_credential_access_follows_rotation_and_deactivation():
    resolver = Resolver()
    access = InboxCredentialAccess(resolver)
    ref = InboxRef(platform=PlatformType.INSTAGRAM, inbox_id="1701")
    first = await access.resolve(ref)
    assert first.credential_version == 1 and "token-v1" not in repr(first)
    assert first.authorization_header() == {"Authorization": "Bearer token-v1"}
    assert first.graph_base_url == "https://graph.facebook.com"
    resolver.version = 2
    assert (await access.resolve(ref)).access_token.get_secret_value() == "token-v2"
    resolver.active = False
    with pytest.raises(InboxNotFoundError):
        await access.resolve(ref)


# ── one contract, two Platforms ──────────────────────────────────────────


async def test_instagram_activate_subscribes_then_returns_encrypted_record():
    requests = []
    service = InboxCredentialService(CredentialCodec(CredentialCodec.generate_key()))
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(provider(requests))
    ) as client:
        connector = InstagramConnector(
            CONFIG,
            client_provider=lambda: client,
            intent_store=InMemoryConnectionIntentStore(),
        )
        request = await connector.begin("op")
        grant = await connector.complete(
            state=request.state, host_subject="op", code="abc"
        )
        ref = grant.inboxes[0].inbox_ref
        activated = await connector.activate(grant, ref, credentials=service)
        assert await connector.disconnect(
            ref, grant.inboxes[0].account_ref, grant.access_token
        )
    assert activated.webhooks_subscribed
    assert activated.details["message_edit"] == "rejected"
    assert activated.record.inbox_ref == ref and activated.record.is_active
    assert requests[-1].method == "DELETE"


def whatsapp_provider(requests, *, shared=True):
    def handler(request):
        requests.append(request)
        path = request.url.path
        if path.endswith("/oauth/access_token"):
            return httpx.Response(200, json={"access_token": "es-token"})
        if path.endswith("/debug_token"):
            data = {
                "is_valid": True,
                "scopes": [
                    "whatsapp_business_management",
                    "whatsapp_business_messaging",
                ],
                "granular_scopes": [
                    {"scope": "whatsapp_business_management", "target_ids": ["W1"]}
                ],
            }
            if not shared:
                data["granular_scopes"] = []
            return httpx.Response(200, json={"data": data})
        if path.endswith("/W1/phone_numbers"):
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "P1",
                            "display_phone_number": "+57 300",
                            "verified_name": "Mimeia",
                        },
                        {"id": "P2", "display_phone_number": "+57 301"},
                    ]
                },
            )
        if path.endswith("/W1/subscribed_apps"):
            return httpx.Response(200, json={"success": True})
        return httpx.Response(404)

    return handler


async def test_whatsapp_embedded_signup_discovers_numbers_and_activates_waba():
    requests = []
    service = InboxCredentialService(CredentialCodec(CredentialCodec.generate_key()))
    config = MetaLoginConfig(
        app_id="111", app_secret=SecretStr("app-secret"), config_id="es-cfg"
    )
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(whatsapp_provider(requests))
    ) as client:
        connector: IInboxConnector = WhatsAppConnector(
            config,
            client_provider=lambda: client,
            intent_store=InMemoryConnectionIntentStore(),
        )
        request = await connector.begin("op")
        query = parse_qs(urlsplit(request.url).query)
        assert json.loads(query["extras"][0]) == {"sessionInfoVersion": "3"}
        assert "redirect_uri" not in query  # JS SDK popup flow
        grant = await connector.complete(
            state=request.state, host_subject="op", code="es-code"
        )
        p1 = InboxRef.whatsapp("P1")
        activated = await connector.activate(grant, p1, credentials=service)
        assert await connector.disconnect(
            p1, PlatformAccountRef.whatsapp("W1"), grant.access_token
        )
    assert connector.platform is PlatformType.WHATSAPP
    assert [i.inbox_ref for i in grant.inboxes] == [p1, InboxRef.whatsapp("P2")]
    assert grant.inboxes[0].display_name == "Mimeia"
    assert grant.inboxes[1].display_name == "+57 301"
    assert all(
        i.account_ref == PlatformAccountRef.whatsapp("W1") for i in grant.inboxes
    )
    assert grant.inboxes[0].readiness.conversation_ready
    assert "redirect_uri" not in requests[0].url.params
    assert activated.webhooks_subscribed and activated.record.inbox_ref == p1
    assert activated.details == {"waba_subscribed_apps": "subscribed"}
    subscribe = [r for r in requests if r.url.path.endswith("/subscribed_apps")]
    assert [r.method for r in subscribe] == ["POST", "DELETE"]
    assert subscribe[0].headers["Authorization"] == "Bearer es-token"


async def test_whatsapp_without_shared_waba_is_an_explicit_provider_error():
    requests = []
    config = MetaLoginConfig(
        app_id="111", app_secret=SecretStr("app-secret"), config_id="es-cfg"
    )
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(whatsapp_provider(requests, shared=False))
    ) as client:
        connector = WhatsAppConnector(
            config,
            client_provider=lambda: client,
            intent_store=InMemoryConnectionIntentStore(),
        )
        request = await connector.begin("op")
        with pytest.raises(ConnectionProviderError) as exc:
            await connector.complete(state=request.state, host_subject="op", code="c")
    assert exc.value.code == "NO_WABA"


# ── shared Platform precondition and typed record (H-29) ────────────────


def _grant(platform, inbox_ref, account_ref):
    return ConnectionGrant(
        platform=platform,
        intent_subject="op",
        access_token=SecretStr("t"),
        inboxes=(
            DiscoveredInbox(
                inbox_ref=inbox_ref,
                account_ref=account_ref,
                readiness=InboxReadiness(conversation_ready=True),
            ),
        ),
    )


@pytest.mark.parametrize("connector_type", [InstagramConnector, WhatsAppConnector])
async def test_activate_rejects_another_platforms_grant_before_any_graph_call(
    connector_type,
):
    requests = []
    service = InboxCredentialService(CredentialCodec(CredentialCodec.generate_key()))
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(provider(requests))
    ) as client:
        connector = connector_type(
            CONFIG,
            client_provider=lambda: client,
            intent_store=InMemoryConnectionIntentStore(),
        )
        other = (
            PlatformType.WHATSAPP
            if connector.platform is PlatformType.INSTAGRAM
            else PlatformType.INSTAGRAM
        )
        foreign_ref = InboxRef(platform=other, inbox_id="1701")
        foreign_account = PlatformAccountRef(platform=other, platform_account_id="1701")
        with pytest.raises(ValueError, match="grant"):
            await connector.activate(
                _grant(other, foreign_ref, foreign_account),
                foreign_ref,
                credentials=service,
            )
        own_ref = InboxRef(platform=connector.platform, inbox_id="1701")
        own_account = PlatformAccountRef(
            platform=connector.platform, platform_account_id="1701"
        )
        with pytest.raises(ValueError, match="cannot activate"):
            await connector.activate(
                _grant(connector.platform, own_ref, own_account),
                foreign_ref,
                credentials=service,
            )
    assert requests == []


def test_activation_result_record_is_a_typed_active_credential_record():
    with pytest.raises(ValidationError):
        ActivationResult(
            inbox_ref=InboxRef(platform=PlatformType.INSTAGRAM, inbox_id="1701"),
            record={"not": "a record"},
            webhooks_subscribed=True,
        )


# ── subscriptions share the Instagram Graph classification (H-30) ───────


async def _subscriptions_against(handler):
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        subscriptions = InstagramSubscriptions(
            client_provider=lambda: client,
            graph_base=CONFIG.graph_base,
            app_id="111",
        )
        token = SecretStr("bisu-token")
        result = await subscriptions.subscribe("1701", token, try_unverified=())
        unsubscribed = await subscriptions.unsubscribe("1701", token)
        try:
            fields = await subscriptions.subscribed_fields("1701", token)
        except ConnectionProviderError as exc:
            fields = exc.code
    return result, unsubscribed, fields


async def test_subscription_outcomes_follow_the_shared_graph_classification():
    def server_error(request):
        return httpx.Response(503, json={"error": {"code": 2}})

    result, unsubscribed, fields = await _subscriptions_against(server_error)
    assert set(result.fields.values()) == {FieldSubscriptionOutcome.UNKNOWN}
    assert result.error_code == "INDETERMINATE"
    assert unsubscribed is False and fields == "INDETERMINATE"

    def transport_down(request):
        raise httpx.ConnectError("down", request=request)

    result, unsubscribed, fields = await _subscriptions_against(transport_down)
    assert set(result.fields.values()) == {FieldSubscriptionOutcome.UNKNOWN}
    assert unsubscribed is False and fields == "INDETERMINATE"

    def rejected(request):
        return httpx.Response(400, json={"error": {"code": 100, "error_subcode": 33}})

    result, unsubscribed, fields = await _subscriptions_against(rejected)
    assert set(result.fields.values()) == {FieldSubscriptionOutcome.REJECTED}
    assert result.error_code == "100/33"
    assert unsubscribed is False and fields == "100/33"

    def accepted(request):
        assert request.url.path == "/v26.0/1701/subscribed_apps"
        assert request.headers["Authorization"] == "Bearer bisu-token"
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"id": "111", "subscribed_fields": ["messages"]},
                        {"id": "999", "subscribed_fields": ["comments"]},
                    ]
                },
            )
        return httpx.Response(200, json={"success": True})

    result, unsubscribed, fields = await _subscriptions_against(accepted)
    assert result.core_subscribed and result.error_code is None
    assert unsubscribed is True and fields == ("messages",)
