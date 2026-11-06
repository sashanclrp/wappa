"""Prebuilt Platform Messengers on the handler (ADR-0025 rule 12).

Every dispatch binds ``self.messenger`` and, from the Platform Registry entry,
the matching Platform Messenger (``self.whatsapp`` or ``self.instagram``); the
other is ``None``. A Platform Messenger extends the same pipeline-wrapped
Messenger, so its sends, Templates and User Data Requests run the middleware.
Shared capabilities are attributes on the core Messenger (``media``).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from wappa import WappaEventHandler
from wappa.core.dispatch.context_builder import (
    DispatchContextBuilder,
    RuntimeCapabilities,
)
from wappa.core.messaging.pipeline import MessengerPipeline, SendInvocation, SendNext
from wappa.domain.inbox import InboxRef
from wappa.domain.interfaces.conversation_capabilities import (
    ICommentControls,
    IConversationContentReader,
)
from wappa.domain.interfaces.history_reader import IConversationHistoryReader
from wappa.domain.interfaces.media_library import IMediaLibrary
from wappa.domain.interfaces.messaging_interface import IMessenger
from wappa.domain.interfaces.template_messaging import ITemplateMessaging
from wappa.domain.messaging_targets import (
    DeliveryAddresses,
    DirectMessage,
    UnsupportedOperationError,
)
from wappa.domain.results import MessageResult
from wappa.domain.user_profile import PlatformUserProfile
from wappa.messaging.instagram import InstagramMessenger
from wappa.messaging.instagram.media.library import InstagramMediaLibrary
from wappa.messaging.instagram.messenger import InstagramMessengerAdapter
from wappa.messaging.whatsapp import WhatsAppMessenger
from wappa.messaging.whatsapp.media.library import WhatsAppMediaLibrary
from wappa.messaging.whatsapp.messenger import WhatsAppMessengerAdapter
from wappa.platforms import PLATFORMS, platform_messenger
from wappa.schemas.core.types import PlatformType
from wappa.webhooks import InboundMessageWebhook
from wappa.webhooks.core.webhook_interfaces.base_components import UserBase

WA_REF = InboxRef.whatsapp("pnid")
IG_REF = InboxRef(platform=PlatformType.INSTAGRAM, inbox_id="17890001")
ROOT = Path(__file__).resolve().parents[1]


def _whatsapp_adapter() -> WhatsAppMessengerAdapter:
    return WhatsAppMessengerAdapter(
        client=None,  # type: ignore[arg-type]
        media_transport=None,  # type: ignore[arg-type]
        inbox_id=WA_REF.inbox_id,
    )


def _instagram_adapter() -> InstagramMessengerAdapter:
    return InstagramMessengerAdapter(
        inbox_ref=IG_REF,
        access_token=SecretStr("tkn"),
        session_provider=httpx.AsyncClient,
        graph_api_version="v26.0",
        graph_base_url="https://graph.facebook.com",
    )


class _Recording:
    """Middleware that records each invocation and answers without I/O."""

    name = "recording"

    def __init__(self) -> None:
        self.seen: list[SendInvocation] = []

    async def handle(
        self, invocation: SendInvocation, call_next: SendNext
    ) -> MessageResult:
        self.seen.append(invocation)
        return MessageResult(
            success=True,
            platform=invocation.target.inbox_ref.platform,
            inbox_id=invocation.target.inbox_ref.inbox_id,
        )


class _Handler(WappaEventHandler):
    async def process_message(self, webhook: InboundMessageWebhook) -> None:
        return None


def _target(ref: InboxRef) -> DirectMessage:
    return DirectMessage(inbox_ref=ref, addresses=DeliveryAddresses.of("u-1"))


def _bind(messenger: IMessenger | None) -> _Handler:
    return _Handler().with_context(
        inbox_id=messenger.inbox_id if messenger else None,
        user_id="u-1",
        messenger=messenger,
        cache_factory=None,
    )


# ── the handler gets its dispatch's Platform Messenger ───────────────────────


def test_a_whatsapp_dispatch_binds_self_whatsapp_and_no_instagram() -> None:
    messenger = MessengerPipeline(_whatsapp_adapter())
    handler = _bind(messenger)
    assert isinstance(handler.whatsapp, WhatsAppMessenger)
    assert handler.whatsapp.messenger is messenger
    assert handler.instagram is None


def test_an_instagram_dispatch_binds_self_instagram_and_no_whatsapp() -> None:
    messenger = MessengerPipeline(_instagram_adapter())
    handler = _bind(messenger)
    assert isinstance(handler.instagram, InstagramMessenger)
    assert handler.instagram.messenger is messenger
    assert handler.whatsapp is None


def test_no_messenger_binds_no_platform_messenger() -> None:
    handler = _bind(None)
    assert (handler.whatsapp, handler.instagram) == (None, None)


def test_a_reclone_drops_the_previous_platform_messenger() -> None:
    whatsapp = _bind(MessengerPipeline(_whatsapp_adapter()))
    instagram = whatsapp.with_context(
        inbox_id=IG_REF.inbox_id,
        user_id="u-1",
        messenger=MessengerPipeline(_instagram_adapter()),
        cache_factory=None,
    )
    assert instagram.whatsapp is None
    assert isinstance(instagram.instagram, InstagramMessenger)


def test_the_dispatch_context_builder_binds_from_the_apps_table() -> None:
    capabilities = RuntimeCapabilities(
        session_provider=httpx.AsyncClient,
        media_download_client_provider=httpx.AsyncClient,
        credential_resolver=None,  # type: ignore[arg-type]
        messenger_middleware=(),
        cache_type="memory",
        background_work_tracker=None,
        platforms=PLATFORMS,
    )
    builder = DispatchContextBuilder(capabilities)
    handler = builder.bind_handler(
        _Handler(),
        inbox_ref=WA_REF,
        user_id="u-1",
        messenger=MessengerPipeline(_whatsapp_adapter()),
        cache_factory=None,
    )
    assert isinstance(handler.whatsapp, WhatsAppMessenger)
    assert handler.instagram is None


def test_an_entry_without_a_platform_messenger_builder_adds_none() -> None:
    messenger = MessengerPipeline(_whatsapp_adapter())
    entry = PLATFORMS[PlatformType.WHATSAPP]
    table = {
        PlatformType.WHATSAPP: type(entry)(
            webhooks=entry.webhooks,
            build_messenger=entry.build_messenger,
            display_name=entry.display_name,
        )
    }
    assert platform_messenger(messenger, table) is None
    assert platform_messenger(messenger, {}) is None


# ── Platform Messenger calls run the Messenger Pipeline ──────────────────────


async def test_whatsapp_platform_messenger_sends_run_the_middleware() -> None:
    recording = _Recording()
    handler = _bind(MessengerPipeline(_whatsapp_adapter(), [(recording, 50)]))
    whatsapp = handler.whatsapp
    assert whatsapp is not None
    target = _target(WA_REF)

    await whatsapp.send_text("hi", target)
    await whatsapp.templates.send_text_template(
        "welcome", target, template_type="utility"
    )
    await whatsapp.send_location_request("Where are you?", target)
    await whatsapp.send_contact_request("Your phone?", target)

    assert [i.method_name for i in recording.seen] == [
        "send_text",
        "send_text_template",
        "send_location_request",
        "send_contact_request",
    ]
    assert isinstance(whatsapp.templates, ITemplateMessaging)


async def test_instagram_platform_messenger_sends_run_the_middleware() -> None:
    recording = _Recording()
    handler = _bind(MessengerPipeline(_instagram_adapter(), [(recording, 50)]))
    instagram = handler.instagram
    assert instagram is not None

    await instagram.send_text("hi", _target(IG_REF))

    assert [i.method_name for i in recording.seen] == ["send_text"]
    assert isinstance(instagram.comments, ICommentControls)
    assert isinstance(instagram.content, IConversationContentReader)
    assert isinstance(instagram.history, IConversationHistoryReader)


def test_whatsapp_has_no_instagram_attributes_and_the_reverse() -> None:
    whatsapp = _bind(MessengerPipeline(_whatsapp_adapter())).whatsapp
    instagram = _bind(MessengerPipeline(_instagram_adapter())).instagram
    for name in ("comments", "content", "history"):
        assert not hasattr(whatsapp, name), name
    for name in ("templates", "send_location_request", "send_contact_request"):
        assert not hasattr(instagram, name), name


# ── shared capabilities are attributes on the core Messenger ─────────────────


def test_media_is_ready_on_every_platforms_messenger() -> None:
    whatsapp = MessengerPipeline(_whatsapp_adapter())
    instagram = MessengerPipeline(_instagram_adapter())
    assert isinstance(whatsapp.media, WhatsAppMediaLibrary)
    assert isinstance(instagram.media, InstagramMediaLibrary)
    handler = _bind(whatsapp)
    assert handler.whatsapp is not None
    assert handler.whatsapp.media is whatsapp.media


def test_media_raises_on_a_messenger_without_a_media_library() -> None:
    class _Bare(IMessenger):
        platform = PlatformType.TELEGRAM
        inbox_id = "t-1"

        async def send_text(self, *args: Any, **kwargs: Any) -> MessageResult:
            raise AssertionError

        async def resolve_platform_user_profile(
            self, user: UserBase
        ) -> PlatformUserProfile:
            raise AssertionError

    with pytest.raises(UnsupportedOperationError, match="IMediaLibrary"):
        _ = _Bare().media
    assert isinstance(IMediaLibrary, type)


# ── guards ───────────────────────────────────────────────────────────────────


def test_the_handler_imports_platform_messengers_for_typing_only() -> None:
    path = ROOT / "wappa/core/events/event_handler/_state.py"
    tree = ast.parse(path.read_text())
    adapter = re.compile(r"^wappa\.messaging\.(whatsapp|instagram)\b")
    typing_only = {
        id(child)
        for node in ast.walk(tree)
        if isinstance(node, ast.If) and getattr(node.test, "id", "") == "TYPE_CHECKING"
        for child in ast.walk(node)
    }
    imports = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and adapter.match(node.module or "")
    ]
    assert imports, "the Platform Messenger attribute types are imported"
    for node in imports:
        assert id(node) in typing_only, node.module


_HOST_FACING = [
    *sorted((ROOT / "wappa/cli/examples").rglob("*.py")),
    *sorted((ROOT / "wappa/cli/examples").rglob("*.md")),
    *sorted((ROOT / "wappa/cli/skills").rglob("*.md")),
    *sorted((ROOT / "wappa/cli/skills").rglob("*.json")),
]


def test_host_facing_examples_and_skills_never_look_up_a_capability() -> None:
    lookup = re.compile(r"\brequire_capability\b|\.capability\(")
    found = {
        path.relative_to(ROOT).as_posix(): [
            number
            for number, line in enumerate(path.read_text().splitlines(), start=1)
            if lookup.search(line)
        ]
        for path in _HOST_FACING
    }
    assert {path: lines for path, lines in found.items() if lines} == {}


# ── outside a dispatch: OutboundRuntime builds the same Platform Messenger ───


async def test_outbound_runtime_builds_the_platform_messenger_over_its_pipeline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from wappa.messaging.outbound_runtime import OutboundRuntime

    recording = _Recording()
    runtime = OutboundRuntime(
        session_provider=httpx.AsyncClient,
        media_download_client_provider=httpx.AsyncClient,
        credential_resolver=None,  # type: ignore[arg-type]
    )

    async def fake_messenger(inbox_ref: InboxRef, **_: Any) -> IMessenger:
        adapter = _whatsapp_adapter() if inbox_ref == WA_REF else _instagram_adapter()
        return MessengerPipeline(adapter, [(recording, 50)])

    monkeypatch.setattr(runtime, "messenger", fake_messenger)

    whatsapp = await runtime.platform_messenger(WA_REF)
    instagram = await runtime.platform_messenger(IG_REF)

    assert isinstance(whatsapp, WhatsAppMessenger)
    assert isinstance(instagram, InstagramMessenger)
    await whatsapp.templates.send_text_template(
        "welcome", _target(WA_REF), template_type="utility"
    )
    assert [i.method_name for i in recording.seen] == ["send_text_template"]


def test_binding_needs_no_capability_until_one_is_used() -> None:
    whatsapp_adapter = _whatsapp_adapter()
    whatsapp_adapter._capabilities = {}
    instagram_adapter = _instagram_adapter()
    instagram_adapter._capabilities = {}

    whatsapp = _bind(whatsapp_adapter).whatsapp
    instagram = _bind(instagram_adapter).instagram

    assert whatsapp is not None and instagram is not None
    with pytest.raises(UnsupportedOperationError):
        _ = whatsapp.templates
    with pytest.raises(UnsupportedOperationError):
        _ = instagram.comments


def test_instagram_content_offers_the_mention_reads() -> None:
    instagram = _bind(_instagram_adapter()).instagram
    assert instagram is not None
    assert callable(instagram.content.get_mentioned_post)
    assert callable(instagram.content.get_mentioned_comment)
