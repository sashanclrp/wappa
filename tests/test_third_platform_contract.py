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

import ast
import json
import re
from datetime import UTC, datetime
from functools import cache
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
from wappa.domain.user_profile import PlatformUserProfile
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
    """Records ``send_text``; profiles come from evidence; no capabilities."""

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

    async def resolve_platform_user_profile(
        self, user: UserBase
    ) -> PlatformUserProfile:
        return PlatformUserProfile.from_evidence(FAKE, user).model_copy(
            update={"profile_name": f"Fake {user.platform_user_id}"}
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
        self.platform_messengers: list[tuple[object, object]] = []

    async def process_message(self, webhook: InboundMessageWebhook) -> None:
        assert self.inbox_ref is not None and self.messenger is not None
        self.received.append((webhook, self.inbox_ref, self.messenger))
        self.platform_messengers.append((self.whatsapp, self.instagram))
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
    # The fake entry adds no Platform Messenger: neither Platform's is bound.
    assert platform.handler.platform_messengers == [(None, None)]
    # The reply reached the fake adapter through the Messenger Pipeline.
    (invocation,) = platform.middleware.seen
    assert invocation.method_name == "send_text"
    assert invocation.target.address == "u-7"
    (sent,) = platform.messengers[INBOX_REF].sent
    assert sent[0] == "pong"
    assert sent[1].addresses == DeliveryAddresses.of("u-7")
    (result,) = platform.handler.results
    assert result.success and result.platform == FAKE
    # The core profile read reaches the adapter through the same pipeline.
    profile = await messenger.resolve_platform_user_profile(webhook.user)
    assert profile.found and profile.platform is FAKE
    assert (profile.platform_user_id, profile.profile_name) == ("u-7", "Fake u-7")


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
# adapter folder may name a Platform. Every other path is listed file by file;
# the CLI scaffolds are Host code and get no exemption.
_ADAPTER_PATHS = re.compile(
    r"^(platforms/"
    r"|schemas/core/types\.py"
    r"|domain/inbox/credentials\.py"
    r"|(messaging|webhooks)/(whatsapp|instagram)/"
    r"|connections/(whatsapp|instagram|meta_login)\.py"
    r"|api/routes/whatsapp/)"
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


@cache
def _shared_source_paths() -> tuple[Path, ...]:
    return tuple(
        path
        for path in sorted(WAPPA.rglob("*.py"))
        if not _ADAPTER_PATHS.match(path.relative_to(WAPPA).as_posix())
    )


@cache
def _source_tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text())


@pytest.mark.architecture
def test_shared_code_does_not_branch_on_a_platform() -> None:
    found: dict[str, list[str]] = {}
    for path in _shared_source_paths():
        rel = path.relative_to(WAPPA).as_posix()
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


# Shared files that may import an adapter package, each with its reason.
_ALLOWED_ADAPTER_IMPORTS: dict[str, str] = {
    "api/dependencies/whatsapp_dependencies.py": (
        "dependencies of the WhatsApp extension router, which only WhatsApp mounts"
    ),
    "core/events/event_handler/_state.py": (
        "TYPE_CHECKING-only types of the self.whatsapp / self.instagram Platform "
        "Messenger attributes (ADR-0025 rule 12); the registry builds them"
    ),
}

_ADAPTER_MODULE = re.compile(
    r"^wappa\.(messaging|webhooks)\.(whatsapp|instagram)(\.|$)"
)


def _imported_modules(path: Path) -> list[tuple[int, str]]:
    tree = _source_tree(path)
    package = ".".join(("wappa", *path.relative_to(WAPPA).parent.parts))
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [(node.lineno, alias.name) for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                parent = package.rsplit(".", node.level - 1)[0]
                base = f"{parent}.{base}" if base else parent
            found.append((node.lineno, base))
    return found


@pytest.mark.architecture
def test_shared_code_does_not_import_an_adapter_package() -> None:
    found: dict[str, list[str]] = {}
    for path in _shared_source_paths():
        rel = path.relative_to(WAPPA).as_posix()
        for number, module in _imported_modules(path):
            if _ADAPTER_MODULE.match(module):
                found.setdefault(rel, []).append(f"{number}: {module}")

    unexpected = {
        rel: lines
        for rel, lines in found.items()
        if rel not in _ALLOWED_ADAPTER_IMPORTS
    }
    assert unexpected == {}, (
        "Shared code imports a Platform adapter; move the shape into a neutral "
        f"module or the code into the adapter: {unexpected}"
    )
    stale = set(_ALLOWED_ADAPTER_IMPORTS) - set(found)
    assert stale == set(), f"Allow-list entries no longer needed: {stale}"


# Every Platform, installed or reserved: rule 6 forbids any Platform default.
_PLATFORMS = frozenset(PlatformType.__members__)
_PLATFORM_VALUES = frozenset(member.value for member in PlatformType)


def _names_a_platform(node: ast.AST | None) -> bool:
    """``PlatformType.<MEMBER>`` or a string equal to a Platform value."""
    if isinstance(node, ast.Constant):
        return isinstance(node.value, str) and node.value in _PLATFORM_VALUES
    return (
        isinstance(node, ast.Attribute)
        and node.attr in _PLATFORMS
        and isinstance(node.value, ast.Name)
        and node.value.id == "PlatformType"
    )


def _platform_defaults(path: Path) -> list[int]:
    """Lines where shared code falls back to a Platform.

    Covers parameter defaults, class-body field values, ``default=`` keywords,
    ``x or <platform>`` fallbacks, ``a if b else <platform>`` fallbacks and
    ``.get(key, <platform>)`` fallbacks, each with ``PlatformType.<MEMBER>``
    or the Platform's string value.
    """
    lines: list[int] = []
    for node in ast.walk(_source_tree(path)):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            defaults = [*node.args.defaults, *node.args.kw_defaults]
            lines += [d.lineno for d in defaults if _names_a_platform(d)]
        elif isinstance(node, ast.ClassDef):
            lines += [
                item.lineno
                for item in node.body
                if isinstance(item, ast.AnnAssign) and _names_a_platform(item.value)
            ]
        elif isinstance(node, ast.Call):
            lines += [
                kw.value.lineno
                for kw in node.keywords
                if kw.arg == "default" and _names_a_platform(kw.value)
            ]
            if (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "get"
                and len(node.args) == 2
                and _names_a_platform(node.args[1])
            ):
                lines.append(node.args[1].lineno)
        elif isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or):
            lines += [v.lineno for v in node.values[1:] if _names_a_platform(v)]
        elif isinstance(node, ast.IfExp) and _names_a_platform(node.orelse):
            lines.append(node.orelse.lineno)
    return sorted(lines)


@pytest.mark.architecture
def test_shared_code_has_no_platform_defaults() -> None:
    """ADR-0028 rule 6: a shared API takes the Platform, never defaults it."""
    found: dict[str, list[int]] = {}
    for path in _shared_source_paths():
        rel = path.relative_to(WAPPA).as_posix()
        if lines := _platform_defaults(path):
            found[rel] = lines
    assert found == {}, (
        "Shared code defaults to a Platform; make the Platform a required "
        f"argument: {found}"
    )


@pytest.mark.architecture
def test_the_default_guard_sees_parameters_fields_and_field_defaults(
    tmp_path: Path,
) -> None:
    sample = tmp_path / "sample.py"
    sample.write_text(
        "def send(x, platform=PlatformType.WHATSAPP): ...\n"
        "async def read(*, platform=PlatformType.INSTAGRAM): ...\n"
        "class Result:\n"
        "    platform: PlatformType = PlatformType.WHATSAPP\n"
        "    other: PlatformType = Field(default=PlatformType.INSTAGRAM)\n"
        "def reserved(platform: PlatformType = PlatformType.TELEGRAM): ...\n"
        "def fine(platform: PlatformType | None = None): ...\n"
        "def text(platform: str = 'whatsapp'): ...\n"
        "class Ctx:\n"
        "    platform: str = 'instagram'\n"
        "    other: str = Field(default='whatsapp')\n"
        "a = event.platform or 'whatsapp'\n"
        "b = payload.get('platform', 'instagram')\n"
        "c = w.platform.value if w.platform else 'whatsapp'\n"
        "d = payload.get('platform', '')\n"
        "e = 'whatsapp' in record.name\n"
        "f = report(x, platform='whatsapp')\n"
    )
    assert _platform_defaults(sample) == [1, 2, 4, 5, 6, 8, 10, 11, 12, 13, 14]
