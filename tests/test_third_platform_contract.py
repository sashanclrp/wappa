"""A third Platform plugs in through its adapters and one Platform entry.

The fake Platform below is keyed by the reserved ``PlatformType.TELEGRAM`` and
built only from adapters defined in this module, with no edit to ``wappa/``:
a ``PlatformWebhooks`` adapter, an ``IMessenger`` and an ``IInboxConnector``.
The app's Platform Registry table is ``build_platforms(...)`` plus that one
entry. The proof is end to end: a signed callback is admitted and dispatched,
the Host handler sends through the Messenger Pipeline, and the shared HTTP
surfaces answer from the app's table. A guard test keeps shared code free of
new Platform branches.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from pydantic import SecretStr

from wappa import WappaEventHandler
from wappa.api.dependencies.inbox_context import INBOX_ID_HEADER
from wappa.api.routes.messaging_router import create_messaging_router
from wappa.api.routes.webhooks import create_webhook_router
from wappa.connections import (
    ActivationResult,
    AuthorizationRequest,
    ConnectionGrant,
    ConnectionIntent,
    ConnectionStateError,
    DiscoveredInbox,
    IInboxConnector,
    InboxReadiness,
    InMemoryConnectionIntentStore,
)
from wappa.connections.contract import require_platform
from wappa.core.config.meta_application import MetaApplicationConfig
from wappa.core.events import WappaEventDispatcher
from wappa.core.events.field_registry import FieldHandlerRegistry
from wappa.core.factory.inbox_assembly import InboxRuntimeConfiguration
from wappa.core.inbound import SIGNATURE_HEADER, MetaCallbackAuthenticator
from wappa.core.inbound.platform_webhooks import (
    PayloadRoutingError,
    PlatformWebhooks,
    RoutedWebhookDelivery,
)
from wappa.core.lifecycle import BackgroundWorkTracker, SessionLifecycle
from wappa.core.messaging.pipeline import MessengerPipeline, SendInvocation, SendNext
from wappa.domain.inbox import (
    IInboxCredentialResolver,
    InboxCredentialService,
    InboxNotFoundError,
    InboxRef,
    InboxRoutingMode,
    PlatformAccountRef,
    ResolvedInboxCredentials,
)
from wappa.domain.inbox.credentials import CredentialRecord
from wappa.domain.interfaces.messaging_interface import IMessenger
from wappa.domain.interfaces.template_messaging import ITemplateMessaging
from wappa.domain.messaging_targets import DeliveryAddresses, DirectMessage
from wappa.domain.results import MessageResult
from wappa.platforms import (
    BUILTIN_FIELDS,
    MessengerDeps,
    PlatformEntry,
    build_platforms,
)
from wappa.schemas.core.types import PlatformType, UniversalMessageData
from wappa.webhooks import InboundMessageWebhook
from wappa.webhooks.core.base_message import BaseMessageContext, BaseTextMessage
from wappa.webhooks.core.webhook_interfaces.base_components import InboxBase, UserBase
from wappa.webhooks.core.webhook_interfaces.universal_webhooks import (
    UniversalWebhook,
)

FAKE = PlatformType.TELEGRAM
INBOX_ID = "fake-1"
INBOX_REF = InboxRef(platform=FAKE, inbox_id=INBOX_ID)
ACCOUNT_REF = PlatformAccountRef(platform=FAKE, platform_account_id="fake-account")
APP_SECRET = SecretStr("third-platform-secret")
VERIFY_TOKEN = "verify-token"

# ── the fake Platform's adapters (defined here only) ─────────────────────────


class FakeTextMessage(BaseTextMessage):
    """The fake Platform's text message, expressed in the neutral base."""

    mid: str
    sender: str
    text: str
    sent_at: int

    @property
    def platform(self) -> PlatformType:
        return FAKE

    @property
    def message_id(self) -> str:
        return self.mid

    @property
    def sender_id(self) -> str:
        return self.sender

    @property
    def timestamp(self) -> int:
        return self.sent_at

    @property
    def conversation_id(self) -> str:
        return self.sender

    @property
    def text_content(self) -> str:
        return self.text

    @property
    def is_reply(self) -> bool:
        return False

    @property
    def is_forwarded(self) -> bool:
        return False

    def get_reply_context(self) -> tuple[str | None, str | None]:
        return None, None

    def has_context(self) -> bool:
        return False

    def get_context(self) -> BaseMessageContext | None:
        return None

    def to_universal_dict(self) -> UniversalMessageData:
        return {"text": self.text}

    def get_platform_data(self) -> dict[str, Any]:
        return {"mid": self.mid}

    @classmethod
    def from_platform_data(cls, data: dict[str, Any], **kwargs: Any) -> FakeTextMessage:
        return cls(**data)


class FakeWebhooks:
    """``PlatformWebhooks``: one Inbox per payload, read from ``inbox``."""

    platform = FAKE
    builtin_fields: frozenset[str] = frozenset()

    async def route(
        self, payload: dict[str, Any], resolver: IInboxCredentialResolver
    ) -> tuple[RoutedWebhookDelivery, ...]:
        inbox_id = payload.get("inbox")
        if not isinstance(inbox_id, str):
            raise PayloadRoutingError("fake payload names no inbox")
        credentials = await resolver.resolve_credentials(
            InboxRef(platform=FAKE, inbox_id=inbox_id)
        )
        return (
            RoutedWebhookDelivery(
                inbox_ref=credentials.inbox_ref,
                account_ref=credentials.account_ref,
                credentials=credentials,
                payload=payload,
            ),
        )

    async def translate(
        self, payload: dict[str, Any], *, inbox_id: str
    ) -> UniversalWebhook:
        message = payload["message"]
        return InboundMessageWebhook(
            inbox=InboxBase(
                inbox_id=inbox_id,
                display_address=None,
                platform_account_id=ACCOUNT_REF.platform_account_id,
            ),
            user=UserBase(platform_user_id=message["sender"]),
            message=FakeTextMessage(
                mid=message["mid"],
                sender=message["sender"],
                text=message["text"],
                sent_at=1,
            ),
            timestamp=datetime.now(UTC),
            platform=FAKE,
            webhook_id=message["mid"],
        )


class FakeMessenger(IMessenger):
    """Records ``send_text``; registers no capabilities."""

    def __init__(self, inbox_ref: InboxRef) -> None:
        self._inbox_ref = inbox_ref
        self.sent: list[tuple[str, DirectMessage]] = []

    @property
    def platform(self) -> PlatformType:
        return self._inbox_ref.platform

    @property
    def inbox_id(self) -> str:
        return self._inbox_ref.inbox_id

    async def send_text(
        self,
        text: str,
        target: Any,
        reply_to_message_id: str | None = None,
        disable_preview: bool = False,
    ) -> MessageResult:
        self.sent.append((text, target))
        return MessageResult(
            success=True,
            platform=FAKE,
            message_id=f"fake.{len(self.sent)}",
            recipient=target.recipient_id,
            inbox_id=self.inbox_id,
            platform_response={"ok": True},
        )


class FakeConnector(IInboxConnector):
    """``IInboxConnector`` with an in-memory one-use state store."""

    def __init__(self) -> None:
        self.intents = InMemoryConnectionIntentStore()

    @property
    def platform(self) -> PlatformType:
        return FAKE

    async def begin(
        self, host_subject: str, *, metadata: dict[str, str] | None = None
    ) -> AuthorizationRequest:
        state = f"state-{host_subject}"
        await self.intents.save(
            ConnectionIntent(
                state=state,
                host_subject=host_subject,
                created_at=0.0,
                expires_at=60.0,
                metadata=metadata or {},
            )
        )
        return AuthorizationRequest(
            url=f"https://fake.example/authorize?state={state}",
            state=state,
            expires_at=60.0,
        )

    async def complete(
        self,
        *,
        state: str | None,
        host_subject: str,
        code: str | None = None,
        error: str | None = None,
        error_reason: str | None = None,
    ) -> ConnectionGrant:
        intent = await self.intents.consume(state or "")
        if intent is None or intent.host_subject != host_subject:
            raise ConnectionStateError("unknown or replayed state")
        return ConnectionGrant(
            platform=FAKE,
            intent_subject=host_subject,
            access_token=SecretStr(f"token-for-{code}"),
            inboxes=(
                DiscoveredInbox(
                    inbox_ref=INBOX_REF,
                    account_ref=ACCOUNT_REF,
                    readiness=InboxReadiness(conversation_ready=True),
                ),
            ),
        )

    async def activate(
        self,
        grant: ConnectionGrant,
        inbox_ref: InboxRef,
        *,
        credentials: InboxCredentialService,
        previous: CredentialRecord | None = None,
    ) -> ActivationResult:
        require_platform(FAKE, grant, inbox_ref)
        raise NotImplementedError("the fake Platform persists no record")

    async def disconnect(
        self, inbox_ref: InboxRef, account_ref: PlatformAccountRef, token: SecretStr
    ) -> bool:
        return True


# ── the app ──────────────────────────────────────────────────────────────────


class Resolver(IInboxCredentialResolver):
    """In-memory credentials for the fake Inbox; no Inbox Directory record."""

    async def resolve_credentials(
        self, inbox_ref: InboxRef
    ) -> ResolvedInboxCredentials:
        if inbox_ref != INBOX_REF:
            raise InboxNotFoundError(inbox_ref)
        return ResolvedInboxCredentials(
            inbox_ref=inbox_ref,
            account_ref=ACCOUNT_REF,
            access_token=SecretStr("fake-token"),
            credential_version=1,
        )

    async def list_inbox_refs_for_platform_account(
        self, account_ref: PlatformAccountRef
    ) -> tuple[InboxRef, ...]:
        return ()


class RecordingMiddleware:
    name = "recording"

    def __init__(self) -> None:
        self.seen: list[SendInvocation] = []

    async def handle(
        self, invocation: SendInvocation, call_next: SendNext
    ) -> MessageResult:
        self.seen.append(invocation)
        return await call_next(invocation)


class Pong(WappaEventHandler):
    def __init__(self) -> None:
        super().__init__()
        self.received: list[tuple[InboundMessageWebhook, InboxRef, IMessenger]] = []
        self.results: list[MessageResult] = []

    async def process_message(self, webhook: InboundMessageWebhook) -> None:
        assert self.inbox_ref is not None and self.messenger is not None
        self.received.append((webhook, self.inbox_ref, self.messenger))
        self.results.append(
            await self.messenger.send_text(
                "pong",
                DirectMessage(
                    inbox_ref=self.inbox_ref,
                    addresses=webhook.user.delivery_addresses(),
                ),
            )
        )


class FakePlatform:
    """The app plus the fakes the assertions read."""

    def __init__(self, provider: httpx.AsyncClient) -> None:
        self.messengers: dict[InboxRef, FakeMessenger] = {}
        self.middleware = RecordingMiddleware()
        self.handler = Pong()
        self.tracker = BackgroundWorkTracker()

        def build_messenger(
            credentials: ResolvedInboxCredentials, deps: MessengerDeps
        ) -> IMessenger:
            return self.messengers.setdefault(
                credentials.inbox_ref, FakeMessenger(credentials.inbox_ref)
            )

        webhooks: PlatformWebhooks = FakeWebhooks()
        platforms = {
            **build_platforms(FieldHandlerRegistry(BUILTIN_FIELDS)),
            FAKE: PlatformEntry(
                webhooks=webhooks,
                build_messenger=build_messenger,
                display_name="Fake",
            ),
        }
        app = FastAPI()
        app.include_router(create_webhook_router(WappaEventDispatcher(self.handler)))
        app.include_router(create_messaging_router(include_template_transport=True))
        app.state.platforms = MappingProxyType(platforms)
        app.state.meta_application_config = MetaApplicationConfig(
            app_secret=APP_SECRET,
            whatsapp_webhook_verify_token=SecretStr(VERIFY_TOKEN),
        )
        app.state.session_lifecycle = SessionLifecycle(provider)
        app.state.inbox_runtime = InboxRuntimeConfiguration(
            mode=InboxRoutingMode.EXPLICIT, credential_resolver=Resolver()
        )
        app.state.background_work_tracker = self.tracker
        app.state.messenger_middleware = [(self.middleware, 50)]
        app.state.wappa_cache_type = "memory"
        self.app = app

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app), base_url="http://test"
        )


def _signed(body: bytes) -> dict[str, str]:
    return {
        SIGNATURE_HEADER: MetaCallbackAuthenticator(APP_SECRET).sign(body),
        "Content-Type": "application/json",
    }


@pytest.fixture
async def platform() -> Any:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(500))
    ) as provider:
        fake = FakePlatform(provider)
        yield fake
        await fake.app.state.session_lifecycle.close()


# ── the contract ─────────────────────────────────────────────────────────────


async def test_a_signed_callback_dispatches_and_the_reply_runs_the_pipeline(
    platform: FakePlatform,
) -> None:
    body = json.dumps(
        {"inbox": INBOX_ID, "message": {"mid": "m1", "sender": "u-7", "text": "ping"}}
    ).encode()

    async with platform.client() as client:
        unsigned = await client.post("/webhook/inboxes/telegram", content=body)
        response = await client.post(
            "/webhook/inboxes/telegram", content=body, headers=_signed(body)
        )
    await platform.tracker.drain()

    assert unsigned.status_code == 401
    assert response.status_code == 200, response.text
    ((webhook, inbox_ref, messenger),) = platform.handler.received
    assert inbox_ref == InboxRef(platform=FAKE, inbox_id=INBOX_ID)
    assert webhook.platform is FAKE and webhook.get_message_text() == "ping"
    assert isinstance(messenger, MessengerPipeline)
    assert messenger.platform is FAKE
    # The reply reached the fake adapter through the Messenger Pipeline.
    (invocation,) = platform.middleware.seen
    assert invocation.method_name == "send_text"
    assert invocation.target.address == "u-7"
    (sent,) = platform.messengers[INBOX_REF].sent
    assert sent[0] == "pong"
    assert sent[1].addresses == DeliveryAddresses.of("u-7")
    (result,) = platform.handler.results
    assert result.success and result.platform == FAKE


async def test_the_app_table_is_the_installed_set(platform: FakePlatform) -> None:
    async with platform.client() as client:
        listed = await client.get("/webhook/platforms")
        challenge = await client.get(
            "/webhook/inboxes/telegram",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": VERIFY_TOKEN,
                "hub.challenge": "42",
            },
        )
        teams_get = await client.get(
            "/webhook/inboxes/teams",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": VERIFY_TOKEN,
                "hub.challenge": "42",
            },
        )
        body = b"{}"
        teams_post = await client.post(
            "/webhook/inboxes/teams", content=body, headers=_signed(body)
        )

    assert "telegram" in listed.json()["installed_platforms"]
    assert "teams" not in listed.json()["installed_platforms"]
    assert challenge.status_code == 200 and challenge.text == "42"
    # Registered vocabulary, not installed: rejected, never treated as WhatsApp.
    assert teams_get.status_code == teams_post.status_code == 400


async def test_a_capability_the_platform_lacks_is_none_and_its_routes_501(
    platform: FakePlatform,
) -> None:
    async with platform.client() as client:
        templates = await client.post(
            "/api/telegram/templates/send-text",
            json={},
            headers={INBOX_ID_HEADER: INBOX_ID},
        )
        extension = await client.get(
            "/api/telegram/messages/limits", headers={INBOX_ID_HEADER: INBOX_ID}
        )
        sent = await client.post(
            "/api/telegram/messages/send-text",
            json={"recipient": "6551596044932863", "text": "hello"},
            headers={INBOX_ID_HEADER: INBOX_ID},
        )

    assert templates.status_code == 501
    assert "ITemplateMessaging" in templates.json()["detail"]
    assert extension.status_code == 501, "WhatsApp extension routes stay WhatsApp-only"
    assert sent.status_code == 200, sent.text
    messenger = platform.messengers[INBOX_REF]
    assert messenger.capability(ITemplateMessaging) is None
    assert messenger.sent[-1][0] == "hello"


async def test_the_connector_round_trips_and_rejects_another_platforms_grant() -> None:
    connector = FakeConnector()
    request = await connector.begin("operator-1")
    grant = await connector.complete(
        state=request.state, host_subject="operator-1", code="c1"
    )
    assert grant.inbox(INBOX_REF).readiness.conversation_ready
    with pytest.raises(ConnectionStateError):
        await connector.complete(
            state=request.state, host_subject="operator-1", code="c1"
        )

    whatsapp_ref = InboxRef.whatsapp("1014417365082534")
    whatsapp_grant = ConnectionGrant(
        platform=PlatformType.WHATSAPP,
        intent_subject="operator-1",
        access_token=SecretStr("t"),
        inboxes=(
            DiscoveredInbox(
                inbox_ref=whatsapp_ref,
                account_ref=PlatformAccountRef.whatsapp("1111"),
                readiness=InboxReadiness(conversation_ready=True),
            ),
        ),
    )
    credentials = InboxCredentialService.__new__(InboxCredentialService)
    with pytest.raises(ValueError, match="cannot activate"):
        await connector.activate(whatsapp_grant, INBOX_REF, credentials=credentials)
    with pytest.raises(ValueError, match="cannot activate"):
        await connector.activate(grant, whatsapp_ref, credentials=credentials)


# ── guard: no new Platform branches in shared code ───────────────────────────

WAPPA = Path(__file__).resolve().parents[1] / "wappa"

# Platform vocabulary, the composition root, the credential union and every
# adapter folder may name a Platform.
_ADAPTER_PATHS = re.compile(
    r"^(platforms\.py"
    r"|schemas/core/types\.py"
    r"|domain/inbox/credentials\.py"
    r"|(messaging|webhooks)/(whatsapp|instagram)/"
    r"|processors/(whatsapp|instagram)_processor\.py"
    r"|core/inbound/(whatsapp|instagram)_routing\.py"
    r"|connections/(whatsapp|instagram|meta_login)\.py"
    r"|api/routes/whatsapp/"
    r"|cli/)"
)

# Known legitimate shared-code sites, each with its reason.
_ALLOWED_BRANCHES: dict[str, str] = {
    "api/dependencies/whatsapp_dependencies.py": (
        "whatsapp_only: the one Platform-name gate of the WhatsApp extension router"
    ),
    "core/plugins/wappa_core_plugin.py": (
        "legacy routing mode is the WhatsApp settings bundle; only its URL is logged"
    ),
}

_PLATFORM = r"PlatformType\.(?:WHATSAPP|INSTAGRAM)\b"
_COMPARISON = re.compile(
    rf"(?:==|!=|\bis(?:\s+not)?\b|\bin\b)\s*[\(\[{{]?\s*{_PLATFORM}"
    rf"|{_PLATFORM}(?:\.value)?\s*(?:==|!=|\bis\b|\bin\b)"
)


def test_shared_code_does_not_branch_on_a_platform() -> None:
    found: dict[str, list[str]] = {}
    for path in sorted(WAPPA.rglob("*.py")):
        rel = path.relative_to(WAPPA).as_posix()
        if _ADAPTER_PATHS.match(rel):
            continue
        for number, line in enumerate(path.read_text().splitlines(), start=1):
            if _COMPARISON.search(line):
                found.setdefault(rel, []).append(f"{number}: {line.strip()}")

    unexpected = {
        rel: lines for rel, lines in found.items() if rel not in _ALLOWED_BRANCHES
    }
    assert unexpected == {}, (
        "Shared code branches on a Platform; move the rule into the adapter or "
        f"the Platform Registry: {unexpected}"
    )
    stale = set(_ALLOWED_BRANCHES) - set(found)
    assert stale == set(), f"Allow-list entries no longer needed: {stale}"
