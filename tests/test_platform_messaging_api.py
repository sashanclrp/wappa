"""The messaging HTTP API serves every Platform under ``/api/{platform}``.

``/api/whatsapp/...`` URLs are unchanged; ``/api/instagram/...`` reaches the
Instagram Inbox's own Messenger (with app middleware, via ``OutboundRuntime``).
WhatsApp-only routes answer 501 for other Platforms and an action a Platform
cannot perform answers 501.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from wappa.api.dependencies.inbox_context import INBOX_ID_HEADER
from wappa.api.routes.messaging_router import create_messaging_router
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
from wappa.messaging.outbound_runtime import OutboundRuntime
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


# send_text body → failed-result error_code the fake messenger returns.
_FAILURES: dict[str, str | None] = {"reject": None, "too-long": "FILE_SIZE_EXCEEDED"}


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
        if text in _FAILURES:
            return self._failed(_FAILURES[text])
        if text == "local-rule":
            raise ValueError("text breaks a local rule")
        if text == "crash":
            raise RuntimeError("adapter bug")
        return self._ok(getattr(target, "recipient_id", "comment"))

    def _failed(self, error_code: str | None) -> MessageResult:
        return MessageResult(
            success=False,
            platform=self.platform,
            error="Platform rejected the message",
            error_code=error_code,
            inbox_id=self.inbox_id,
        )

    async def mark_as_read(
        self, message_id: str, target: Any, *, typing: bool = False
    ) -> MessageResult:
        self.calls.append(("mark_as_read", (message_id, target, typing)))
        return self._failed(None)

    async def send_location(self, *args: Any, **kwargs: Any) -> MessageResult:
        # Specialized sends map the error_code, not words in the error text.
        return MessageResult(
            success=False,
            platform=self.platform,
            error="401 unauthorized rate limit",
            error_code="INVALID_COORDINATES",
            inbox_id=self.inbox_id,
        )

    async def send_carousel(
        self, cards: Any, target: Any, body: str, reply_to_message_id: Any = None
    ) -> MessageResult:
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
    card = {
        "title": "Plan",
        "header": {"kind": "image", "url": "https://example.com/a.png"},
    }

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


_WHATSAPP_EXTENSION_ROUTES = [
    ("GET", "/messages/limits"),
    ("GET", "/media/limits"),
    ("POST", "/specialized/validate-contact"),
    ("POST", "/specialized/validate-coordinates"),
    ("GET", "/templates/limits"),
    ("GET", "/templates/info"),
    ("GET", "/health"),
]


@pytest.mark.parametrize(("method", "path"), _WHATSAPP_EXTENSION_ROUTES)
def test_whatsapp_extension_routes_are_501_for_instagram(
    method: str, path: str
) -> None:
    app, resolver, _ = _app()

    response = TestClient(app).request(
        method, f"/api/instagram{path}", headers=IG_HEADERS, json={}
    )

    assert response.status_code == 501
    assert "instagram does not provide" in response.json()["detail"]
    assert resolver.calls == [], "the one router gate runs before any Inbox lookup"


@pytest.mark.parametrize(
    "path", ["/messages/limits", "/media/limits", "/templates/limits"]
)
def test_static_whatsapp_extension_routes_serve_whatsapp(path: str) -> None:
    app, _, _ = _app()

    response = TestClient(app).get(f"/api/whatsapp{path}")

    assert response.status_code == 200


def test_whatsapp_health_reports_only_the_inbox_and_api_version() -> None:
    app, _, _ = _app()

    response = TestClient(app).get(
        "/api/whatsapp/health", headers={INBOX_ID_HEADER: WA_INBOX}
    )

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"status", "platform", "inbox_id", "api_version"}
    assert body["platform"] == "whatsapp"
    assert body["inbox_id"] == WA_INBOX


@pytest.mark.parametrize("platform", ["whatsapp", "instagram"])
def test_shared_interactive_limits_serve_every_platform(platform: str) -> None:
    app, _, _ = _app()

    response = TestClient(app).get(f"/api/{platform}/interactive/limits")

    assert response.status_code == 200
    assert response.json()["general"]["supported_platforms"] == [
        "whatsapp",
        "instagram",
    ]


def test_template_send_is_501_where_the_inbox_has_no_template_capability() -> None:
    app, _, runtime = _app()
    ig = InboxRef(platform=PlatformType.INSTAGRAM, inbox_id=IG_INBOX)
    runtime.messengers[ig] = _Messenger(ig)
    runtime.messengers[ig].capability = lambda kind: None  # type: ignore[attr-defined]

    response = TestClient(app).post(
        "/api/instagram/templates/send-text",
        json={
            "recipient": {"kind": "phone_number", "value": "573001112233"},
            "template_name": "welcome",
            "category": "utility",
        },
        headers=IG_HEADERS,
    )

    assert response.status_code == 501
    assert "ITemplateMessaging" in response.json()["detail"]


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
    MediaBytes,
    PostContent,
    ReadOutcome,
    ReadResult,
)
from wappa.domain.interfaces.media_library import (  # noqa: E402
    DeleteResult,
    IMediaLibrary,
    MediaInfo,
    UploadResult,
)
from wappa.domain.models.media_result import MediaDownloadResult  # noqa: E402
from wappa.domain.results import (  # noqa: E402
    CommentControlOperation,
    CommentResult,
    ControlResult,
    OperationOutcome,
)
from wappa.messaging.whatsapp.media_library import WhatsAppMediaLibrary  # noqa: E402


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
    def __init__(
        self, platform: PlatformType = PlatformType.INSTAGRAM, inbox_id: str = IG_INBOX
    ) -> None:
        self.platform = platform
        self.inbox_id = inbox_id
        self.uploaded: list[tuple[str, str, bytes, str | None]] = []
        self.downloads: list[tuple[str, int | None]] = []

    async def upload(
        self,
        source: Any,
        family: Any,
        *,
        mime_type: str | None = None,
        filename: str | None = None,
    ) -> UploadResult:
        self.uploaded.append((filename, family.value, source, mime_type))
        return UploadResult(
            outcome=OperationOutcome.ACCEPTED,
            platform=self.platform,
            inbox_id=self.inbox_id,
            media_id="att-1",
        )

    async def info(self, media_id: str) -> ReadResult[MediaInfo]:
        if self.platform is PlatformType.INSTAGRAM:
            raise UnsupportedOperationError("Instagram has no media info endpoint")
        return ReadResult(
            outcome=ReadOutcome.FOUND,
            value=MediaInfo(media_id=media_id, mime_type="image/png", size=9),
        )

    async def delete(self, media_id: str) -> DeleteResult:
        if self.platform is PlatformType.INSTAGRAM:
            raise UnsupportedOperationError("Instagram has no media delete endpoint")
        return DeleteResult(
            outcome=OperationOutcome.ACCEPTED,
            platform=self.platform,
            inbox_id=self.inbox_id,
            media_id=media_id,
        )

    async def download(
        self, media_id: str, *, max_bytes: int | None = None
    ) -> ReadResult[MediaBytes]:
        self.downloads.append((media_id, max_bytes))
        if "expired" in media_id:
            return ReadResult(outcome=ReadOutcome.NOT_FOUND, error="expired")
        if "big" in media_id:
            return ReadResult(
                outcome=ReadOutcome.REJECTED, error="too big", error_code="SIZE"
            )
        return ReadResult(
            outcome=ReadOutcome.FOUND,
            value=MediaBytes(
                content=b"png-bytes",
                content_type="image/png",
                size=9,
                source_host="lookaside.fbsbx.com",
            ),
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


@pytest.mark.parametrize(
    ("text", "status"),
    [("reject", 400), ("too-long", 413), ("local-rule", 400), ("crash", 500)],
)
def test_private_reply_answers_one_status_per_failure(text: str, status: int) -> None:
    app, _, _ = _app()

    response = TestClient(app).post(
        "/api/instagram/messages/send-private-reply",
        json={"comment_id": "c-9", "text": text},
        headers=IG_HEADERS,
    )

    assert response.status_code == status, response.text


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
    assert caps[IMediaLibrary].uploaded == [
        ("menu.png", "image", b"png-bytes", "image/png")
    ]


def test_whatsapp_media_upload_goes_through_the_media_library() -> None:
    """No Platform branch: WhatsApp uploads through IMediaLibrary too."""
    app, _, runtime = _app()
    wa = InboxRef.whatsapp(WA_INBOX)
    library = _Library(PlatformType.WHATSAPP, WA_INBOX)
    runtime.messengers[wa] = _Messenger(wa)
    runtime.messengers[wa].capability = {IMediaLibrary: library}.get  # type: ignore[attr-defined]

    response = TestClient(app).post(
        "/api/whatsapp/media/upload",
        files={"file": ("voice.ogg", b"ogg-bytes", "application/octet-stream")},
        data={"media_type": "audio/ogg"},
        headers={INBOX_ID_HEADER: WA_INBOX},
    )

    assert response.status_code == 200, response.text
    assert response.json()["platform"] == "whatsapp"
    assert library.uploaded == [("voice.ogg", "audio", b"ogg-bytes", "audio/ogg")]


def test_media_info_and_delete_follow_the_media_library() -> None:
    """No WhatsApp-only gate: Instagram's library has no endpoint, so 501."""
    app, _, runtime = _app()
    _with_instagram_capabilities(runtime)
    wa = InboxRef.whatsapp(WA_INBOX)
    runtime.messengers[wa] = _Messenger(wa)
    runtime.messengers[wa].capability = {  # type: ignore[attr-defined]
        IMediaLibrary: _Library(PlatformType.WHATSAPP, WA_INBOX)
    }.get
    client = TestClient(app)
    wa_headers = {INBOX_ID_HEADER: WA_INBOX}

    ig_info = client.get("/api/instagram/media/info/att-1", headers=IG_HEADERS)
    ig_delete = client.delete("/api/instagram/media/att-1", headers=IG_HEADERS)
    wa_info = client.get("/api/whatsapp/media/info/wa-1", headers=wa_headers)
    wa_delete = client.delete("/api/whatsapp/media/wa-1", headers=wa_headers)

    assert ig_info.status_code == 501 and ig_delete.status_code == 501
    assert wa_info.status_code == 200, wa_info.text
    assert wa_info.json()["media_id"] == "wa-1"
    assert wa_info.json()["file_size"] == 9
    assert wa_delete.status_code == 200 and wa_delete.json()["success"] is True


def test_media_download_serves_the_instagram_attachment() -> None:
    app, _, runtime = _app()
    caps = _with_instagram_capabilities(runtime)
    client = TestClient(app)
    url = "https://lookaside.fbsbx.com/ig_messaging_cdn/?asset_id=1&signature=x"
    encoded = url.replace(":", "%3A").replace("?", "%3F").replace("&", "%26")

    found = client.get(f"/api/instagram/media/download/{encoded}", headers=IG_HEADERS)
    expired = client.get("/api/instagram/media/download/expired", headers=IG_HEADERS)
    big = client.get("/api/instagram/media/download/big", headers=IG_HEADERS)

    assert found.status_code == 200, found.text
    assert found.content == b"png-bytes"
    assert found.headers["content-type"] == "image/png"
    assert caps[IMediaLibrary].downloads[0] == (url, None)
    assert expired.status_code == 404 and big.status_code == 413


def test_whatsapp_download_of_a_dead_media_id_answers_404() -> None:
    app, _, runtime = _app()
    wa = InboxRef.whatsapp(WA_INBOX)
    handler = MagicMock()
    handler.get_media_as_bytes = AsyncMock(
        return_value=MediaDownloadResult(
            success=False, error="unknown media", error_code="HTTP_400"
        )
    )
    library = WhatsAppMediaLibrary(handler, WA_INBOX)
    runtime.messengers[wa] = _Messenger(wa)
    runtime.messengers[wa].capability = {IMediaLibrary: library}.get  # type: ignore[attr-defined]

    response = TestClient(app).get(
        "/api/whatsapp/media/download/dead", headers={INBOX_ID_HEADER: WA_INBOX}
    )

    assert response.status_code == 404


def test_media_routes_are_501_without_a_media_library() -> None:
    app, _, runtime = _app()
    wa = InboxRef.whatsapp(WA_INBOX)
    runtime.messengers[wa] = _Messenger(wa)
    runtime.messengers[wa].capability = lambda kind: None  # type: ignore[attr-defined]
    client = TestClient(app)
    headers = {INBOX_ID_HEADER: WA_INBOX}

    download = client.get("/api/whatsapp/media/download/123", headers=headers)
    upload = client.post(
        "/api/whatsapp/media/upload",
        files={"file": ("a.png", b"x", "image/png")},
        headers=headers,
    )

    assert download.status_code == upload.status_code == 501
    assert download.json()["detail"] == "whatsapp does not provide IMediaLibrary"


@pytest.mark.parametrize(
    ("text", "status"),
    [("reject", 400), ("too-long", 413), ("local-rule", 400), ("crash", 500)],
)
def test_send_text_answers_one_status_per_failure(text: str, status: int) -> None:
    app, _, _ = _app()

    response = TestClient(app).post(
        "/api/instagram/messages/send-text",
        json={**TEXT, "text": text},
        headers=IG_HEADERS,
    )

    assert response.status_code == status, response.text


def test_failed_mark_as_read_is_a_4xx_not_a_200() -> None:
    app, _, runtime = _app()

    response = TestClient(app).post(
        "/api/whatsapp/messages/mark-as-read",
        json={"message_id": "wamid.1", "recipient": "573001112233", "typing": True},
        headers={INBOX_ID_HEADER: WA_INBOX},
    )

    assert response.status_code == 400, response.text
    _, (message_id, target, typing) = runtime.messengers[
        InboxRef.whatsapp(WA_INBOX)
    ].calls[0]
    assert (message_id, target.recipient_id, typing) == (
        "wamid.1",
        "573001112233",
        True,
    )


def test_specialized_failure_maps_the_error_code_not_the_error_text() -> None:
    app, _, _ = _app()

    response = TestClient(app).post(
        "/api/whatsapp/specialized/send-location",
        json={"recipient": "573001112233", "latitude": 4.6, "longitude": -74.1},
        headers={INBOX_ID_HEADER: WA_INBOX},
    )

    assert response.status_code == 400, response.text


def test_api_event_names_the_platform_that_sent_even_when_it_failed() -> None:
    app, _, _ = _app()
    events: list[Any] = []

    class _Dispatcher:
        async def dispatch(self, event: Any, request: Any) -> None:
            events.append(event)

    app.state.api_event_dispatcher = _Dispatcher()
    client = TestClient(app)

    ok = client.post("/api/instagram/messages/send-text", json=TEXT, headers=IG_HEADERS)
    failed = client.post(
        "/api/instagram/messages/send-text",
        json={**TEXT, "text": "reject"},
        headers=IG_HEADERS,
    )

    assert (ok.status_code, failed.status_code) == (200, 400)
    assert [(e.platform, e.response_success) for e in events] == [
        ("instagram", True),
        ("instagram", False),
    ]
