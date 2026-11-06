"""The messaging HTTP API serves every Platform under ``/api/{platform}``.

``/api/whatsapp/...`` URLs are unchanged; ``/api/instagram/...`` reaches the
Instagram Inbox's own Messenger (with app middleware, via ``OutboundRuntime``).
WhatsApp-only routes answer 501 for other Platforms and an action a Platform
cannot perform answers 501.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from wappa.api.dependencies.inbox_context import INBOX_ID_HEADER
from wappa.api.routes.whatsapp_combined import create_messaging_router
from wappa.core.factory.inbox_assembly import InboxRuntimeConfiguration
from wappa.core.lifecycle import BackgroundWorkTracker, SessionLifecycle
from wappa.domain.inbox import (
    IInboxCredentialResolver,
    InboxNotFoundError,
    InboxRef,
    InboxRoutingMode,
    PlatformAccountRef,
    ResolvedInboxCredentials,
)
from wappa.domain.messaging_targets import UnsupportedOperationError
from wappa.domain.results import MessageResult
from wappa.messaging.template_transport import OutboundRuntime
from wappa.schemas.core.types import PlatformType

IG_INBOX = "17841457247424017"
WA_INBOX = "1014417365082534"


class _Resolver(IInboxCredentialResolver):
    def __init__(self) -> None:
        self.calls: list[InboxRef] = []

    async def resolve_credentials(
        self, inbox_ref: InboxRef
    ) -> ResolvedInboxCredentials:
        self.calls.append(inbox_ref)
        known = {
            InboxRef(platform=PlatformType.INSTAGRAM, inbox_id=IG_INBOX),
            InboxRef.whatsapp(WA_INBOX),
        }
        if inbox_ref not in known:
            raise InboxNotFoundError(inbox_ref)
        return ResolvedInboxCredentials(
            inbox_ref=inbox_ref,
            account_ref=PlatformAccountRef(
                platform=inbox_ref.platform, platform_account_id="acct-1"
            ),
            access_token=SecretStr("token"),
            credential_version=1,
        )

    async def list_inbox_refs_for_platform_account(
        self, account_ref: PlatformAccountRef
    ) -> tuple[InboxRef, ...]:
        return ()


class _Messenger:
    """Records calls; Instagram has no location request (501 path)."""

    def __init__(self, inbox_ref: InboxRef) -> None:
        self.platform = inbox_ref.platform
        self.inbox_id = inbox_ref.inbox_id
        self.calls: list[tuple[str, Any]] = []

    def _ok(self, recipient: str) -> MessageResult:
        return MessageResult(
            success=True,
            platform=self.platform,
            message_id="mid.1",
            recipient=recipient,
            inbox_id=self.inbox_id,
        )

    async def send_text(self, text: str, target: Any, **_: Any) -> MessageResult:
        self.calls.append(("send_text", target))
        return self._ok(getattr(target, "recipient_id", "comment"))

    async def send_carousel(self, cards: Any, target: Any, body: str) -> MessageResult:
        self.calls.append(("send_carousel", (len(cards), body)))
        return self._ok(target.recipient_id)

    async def send_location_request(self, *args: Any, **kwargs: Any) -> MessageResult:
        raise UnsupportedOperationError(
            f"{self.platform.value} does not support send_location_request"
        )


class _Runtime(OutboundRuntime):
    def __init__(self) -> None:  # no Wappa resources needed
        self.built: list[tuple[InboxRef, bool]] = []
        self.messengers: dict[InboxRef, _Messenger] = {}

    async def messenger(  # type: ignore[override]
        self, inbox_ref: InboxRef, *, credentials: Any = None
    ) -> Any:
        self.built.append((inbox_ref, credentials is not None))
        return self.messengers.setdefault(inbox_ref, _Messenger(inbox_ref))


def _app(
    mode: InboxRoutingMode = InboxRoutingMode.EXPLICIT,
) -> tuple[FastAPI, _Resolver, _Runtime]:
    app = FastAPI()
    resolver, runtime = _Resolver(), _Runtime()
    app.state.session_lifecycle = SessionLifecycle(object())  # type: ignore[arg-type]
    app.state.background_work_tracker = BackgroundWorkTracker()
    app.state.outbound_runtime = runtime
    app.state.inbox_runtime = InboxRuntimeConfiguration(
        mode=mode,
        credential_resolver=resolver,
        default_inbox_ref=(
            InboxRef.whatsapp(WA_INBOX) if mode is InboxRoutingMode.LEGACY else None
        ),
    )
    app.include_router(create_messaging_router(include_template_transport=True))
    return app, resolver, runtime


IG_HEADERS = {INBOX_ID_HEADER: IG_INBOX}
TEXT = {"recipient": "6551596044932863", "text": "hola"}


def test_instagram_send_reaches_the_instagram_inbox_messenger() -> None:
    app, resolver, runtime = _app()

    response = TestClient(app).post(
        "/api/instagram/messages/send-text", json=TEXT, headers=IG_HEADERS
    )

    assert response.status_code == 200, response.text
    ig = InboxRef(platform=PlatformType.INSTAGRAM, inbox_id=IG_INBOX)
    assert resolver.calls == [ig], "one directory lookup, scoped to Instagram"
    assert runtime.built == [(ig, True)], "messenger reuses resolved credentials"
    target = runtime.messengers[ig].calls[0][1]
    assert target.inbox_ref == ig and target.recipient_id == TEXT["recipient"]


def test_whatsapp_urls_are_unchanged_and_carry_every_address() -> None:
    app, _, runtime = _app()

    response = TestClient(app).post(
        "/api/whatsapp/messages/send-text",
        json={**TEXT, "recipient": "573001112233", "addresses": ["CO.123456789"]},
        headers={INBOX_ID_HEADER: WA_INBOX},
    )

    assert response.status_code == 200, response.text
    target = runtime.messengers[InboxRef.whatsapp(WA_INBOX)].calls[0][1]
    assert target.addresses.values == ("573001112233", "CO.123456789")


def test_carousel_route_calls_the_one_carousel_method() -> None:
    app, _, runtime = _app()
    card = {"title": "Plan", "image_url": "https://example.com/a.png"}

    response = TestClient(app).post(
        "/api/instagram/interactive/send-carousel",
        json={"recipient": "6551596044932863", "body": "Pick", "cards": [card, card]},
        headers=IG_HEADERS,
    )

    assert response.status_code == 200, response.text
    ig = InboxRef(platform=PlatformType.INSTAGRAM, inbox_id=IG_INBOX)
    assert runtime.messengers[ig].calls == [("send_carousel", (2, "Pick"))]


def test_an_action_the_platform_lacks_is_501() -> None:
    app, _, _ = _app()

    response = TestClient(app).post(
        "/api/instagram/specialized/send-location-request",
        json={"recipient": "6551596044932863", "body": "Where are you?"},
        headers=IG_HEADERS,
    )

    assert response.status_code == 501
    assert "instagram" in response.json()["detail"]


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/instagram/templates/info"),
        ("GET", "/api/instagram/media/info/1234567890"),
        ("GET", "/api/instagram/health"),
    ],
)
def test_whatsapp_only_routes_are_501_for_instagram(method: str, path: str) -> None:
    app, _, _ = _app()

    response = TestClient(app).request(method, path, headers=IG_HEADERS)

    assert response.status_code == 501
    assert "instagram does not provide" in response.json()["detail"]


def test_unknown_platform_is_rejected() -> None:
    app, resolver, _ = _app()

    response = TestClient(app).post(
        "/api/telegram/messages/send-text", json=TEXT, headers=IG_HEADERS
    )

    assert response.status_code == 404
    assert "telegram" in response.text
    assert resolver.calls == [], "rejected before any directory lookup"


def test_legacy_default_inbox_never_answers_for_another_platform() -> None:
    app, resolver, _ = _app(InboxRoutingMode.LEGACY)
    client = TestClient(app)

    assert client.post("/api/whatsapp/messages/send-text", json=TEXT).status_code == 200
    response = client.post("/api/instagram/messages/send-text", json=TEXT)

    assert response.status_code == 400, "the WhatsApp default is not an Instagram Inbox"
    assert resolver.calls == [InboxRef.whatsapp(WA_INBOX)]


def test_openapi_documents_the_platform_path_parameter() -> None:
    app, _, _ = _app()

    operation = app.openapi()["paths"]["/api/{platform}/messages/send-text"]["post"]
    platform = next(p for p in operation["parameters"] if p["name"] == "platform")

    assert platform["in"] == "path"


# ── capability-gated routes (comments, reads, history, upload) ───────────────

from wappa.domain.interfaces.conversation_capabilities import (  # noqa: E402
    ICommentControls,
    IConversationContentReader,
    PostContent,
    ReadOutcome,
    ReadResult,
)
from wappa.domain.interfaces.media_library import (  # noqa: E402
    IMediaLibrary,
    UploadResult,
)
from wappa.domain.results import (  # noqa: E402
    CommentControlOperation,
    CommentResult,
    ControlResult,
    OperationOutcome,
)


class _Controls:
    def __init__(self, inbox_id: str) -> None:
        self.inbox_id = inbox_id
        self.calls: list[tuple[str, str]] = []

    def _done(self, op: CommentControlOperation, resource: str) -> ControlResult:
        self.calls.append((op.value, resource))
        return ControlResult(
            outcome=OperationOutcome.ACCEPTED,
            platform=PlatformType.INSTAGRAM,
            inbox_id=self.inbox_id,
            operation=op,
            resource_id=resource,
        )

    async def reply_comment(self, ref: Any, text: str) -> CommentResult:
        self.calls.append(("reply", ref.comment_id))
        return CommentResult(
            outcome=OperationOutcome.ACCEPTED,
            platform=PlatformType.INSTAGRAM,
            inbox_id=self.inbox_id,
            comment_id="c-new",
            parent_comment_id=ref.comment_id,
        )

    async def hide_comment(self, ref: Any) -> ControlResult:
        return self._done(CommentControlOperation.HIDE, ref.comment_id)

    async def delete_comment(self, ref: Any) -> ControlResult:
        return self._done(CommentControlOperation.DELETE, ref.comment_id)


class _Reader:
    async def get_post(self, ref: Any) -> ReadResult[PostContent]:
        if ref.media_id == "missing":
            return ReadResult(outcome=ReadOutcome.NOT_FOUND, error="no such post")
        return ReadResult(
            outcome=ReadOutcome.FOUND,
            value=PostContent(post_ref=ref, caption="hello"),
        )


class _Library:
    def __init__(self) -> None:
        self.uploaded: list[tuple[str, str, bytes]] = []

    async def upload(self, source: Any, family: Any) -> UploadResult:
        self.uploaded.append((source.name, family.value, source.read_bytes()))
        return UploadResult(
            outcome=OperationOutcome.ACCEPTED,
            platform=PlatformType.INSTAGRAM,
            inbox_id=IG_INBOX,
            media_id="att-1",
        )


def _with_instagram_capabilities(runtime: _Runtime) -> dict[Any, Any]:
    ig = InboxRef(platform=PlatformType.INSTAGRAM, inbox_id=IG_INBOX)
    caps: dict[Any, Any] = {
        ICommentControls: _Controls(IG_INBOX),
        IConversationContentReader: _Reader(),
        IMediaLibrary: _Library(),
    }
    messenger = runtime.messengers.setdefault(ig, _Messenger(ig))
    messenger.capability = caps.get  # type: ignore[attr-defined]
    return caps


def test_comment_controls_reach_the_instagram_capability() -> None:
    app, _, runtime = _app()
    caps = _with_instagram_capabilities(runtime)
    client = TestClient(app)

    reply = client.post(
        "/api/instagram/comments/c-1/reply",
        json={"text": "Thanks!"},
        headers=IG_HEADERS,
    )
    hidden = client.post("/api/instagram/comments/c-2/hide", headers=IG_HEADERS)
    deleted = client.delete("/api/instagram/comments/c-3", headers=IG_HEADERS)

    assert reply.status_code == 200 and reply.json()["comment_id"] == "c-new"
    assert hidden.status_code == 200 and deleted.status_code == 200
    assert caps[ICommentControls].calls == [
        ("reply", "c-1"),
        ("hide", "c-2"),
        ("delete", "c-3"),
    ]


def test_capability_routes_are_501_where_the_platform_lacks_them() -> None:
    app, _, runtime = _app()
    wa = InboxRef.whatsapp(WA_INBOX)
    runtime.messengers[wa] = _Messenger(wa)
    runtime.messengers[wa].capability = lambda kind: None  # type: ignore[attr-defined]
    client = TestClient(app)
    headers = {INBOX_ID_HEADER: WA_INBOX}

    hide = client.post("/api/whatsapp/comments/c-1/hide", headers=headers)
    post = client.get("/api/whatsapp/posts/123", headers=headers)
    history = client.get("/api/whatsapp/conversations/u1/messages", headers=headers)

    assert hide.status_code == post.status_code == history.status_code == 501
    assert hide.json()["detail"] == "whatsapp does not provide ICommentControls"
    assert "IConversationHistoryReader" in history.json()["detail"]


def test_reads_map_outcomes_to_http_status() -> None:
    app, _, runtime = _app()
    _with_instagram_capabilities(runtime)
    client = TestClient(app)

    found = client.get("/api/instagram/posts/123", headers=IG_HEADERS)
    missing = client.get("/api/instagram/posts/missing", headers=IG_HEADERS)

    assert found.status_code == 200 and found.json()["caption"] == "hello"
    assert missing.status_code == 404 and missing.json()["detail"] == "no such post"


def test_private_reply_sends_text_to_the_comment() -> None:
    app, _, runtime = _app()
    client = TestClient(app)

    response = client.post(
        "/api/instagram/messages/send-private-reply",
        json={"comment_id": "c-9", "text": "Te escribo por DM"},
        headers=IG_HEADERS,
    )

    assert response.status_code == 200, response.text
    ig = InboxRef(platform=PlatformType.INSTAGRAM, inbox_id=IG_INBOX)
    target = runtime.messengers[ig].calls[0][1]
    assert target.kind == "private_reply" and target.comment_ref.comment_id == "c-9"


def test_media_upload_uses_the_instagram_media_library() -> None:
    app, _, runtime = _app()
    caps = _with_instagram_capabilities(runtime)

    response = TestClient(app).post(
        "/api/instagram/media/upload",
        files={"file": ("menu.png", b"png-bytes", "image/png")},
        headers=IG_HEADERS,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["media_id"] == "att-1" and body["platform"] == "instagram"
    assert caps[IMediaLibrary].uploaded == [("menu.png", "image", b"png-bytes")]
