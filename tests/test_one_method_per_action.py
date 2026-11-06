"""ADR-0025: one Messenger method per action on every Platform."""

from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from wappa.domain.inbox import InboxRef
from wappa.domain.models.media_result import MediaDownloadResult
from wappa.messaging import (
    CardMedia,
    DeliveryAddresses,
    DirectMessage,
    ICommentControls,
    IMediaLibrary,
    IMessenger,
    ITemplateMessaging,
    IUserDataRequests,
    MediaFamily,
    MessageCard,
    MessageResult,
    MessengerPipeline,
    ReadOutcome,
    ReplyButton,
    UnsupportedOperationError,
    UrlButton,
)
from wappa.messaging.instagram.messenger import InstagramMessengerAdapter
from wappa.messaging.whatsapp.messenger.whatsapp_messenger import (
    WhatsAppMessengerAdapter,
)
from wappa.schemas.core.types import PlatformType

WA_DM = DirectMessage(
    inbox_ref=InboxRef.whatsapp("pnid"), addresses=DeliveryAddresses.of("573001112233")
)
IG_REF = InboxRef(platform=PlatformType.INSTAGRAM, inbox_id="17890001")
IMG = "https://example.com/c.png"


class _Client:
    def __init__(self) -> None:
        self.posted: list[dict] = []

    async def post_request(self, payload):
        self.posted.append(payload)
        return {
            "messages": [{"id": "wamid.out"}],
            "contacts": [{"input": "573001112233", "wa_id": "573001112233"}],
        }


class _Media:
    def __init__(self, result: MediaDownloadResult) -> None:
        self.result = result

    async def get_media_as_bytes(
        self, media_id: str, *, max_bytes: int | None = None
    ) -> MediaDownloadResult:
        assert media_id == "wa-media-1" and max_bytes is None
        return self.result


def _wa(media: object = None) -> tuple[WhatsAppMessengerAdapter, _Client]:
    client = _Client()
    messenger = WhatsAppMessengerAdapter(
        client=client,  # type: ignore[arg-type]
        media_handler=media,  # type: ignore[arg-type]
        interactive_handler=None,  # type: ignore[arg-type]
        template_handler=None,  # type: ignore[arg-type]
        specialized_handler=None,  # type: ignore[arg-type]
        inbox_id="pnid",
    )
    return messenger, client


def _card(n: int, *buttons) -> MessageCard:
    return MessageCard(
        header=CardMedia.image(url=IMG), title=f"T{n}", subtitle="sub", buttons=buttons
    )


def test_platform_only_primitives_are_not_on_the_contract():
    for name in (
        "mark_seen",
        "set_typing",
        "send_quick_replies",
        "send_buttons",
        "send_card",
        "reply_comment",
        "send_text_template",
        "send_media_template",
        "send_location_template",
        "download_media",
    ):
        assert not hasattr(IMessenger, name), name
    assert hasattr(ICommentControls, "reply_comment")


def test_templates_are_a_whatsapp_capability_not_a_contract_method():
    wa, _ = _wa()
    assert wa.capability(ITemplateMessaging) is wa
    assert wa.capability(ICommentControls) is None
    client = httpx.AsyncClient()
    ig = InstagramMessengerAdapter(
        inbox_ref=IG_REF,
        access_token=SecretStr("tkn"),
        session_provider=lambda: client,
        graph_api_version="v26.0",
        graph_base_url="https://graph.facebook.com",
    )
    assert ig.capability(ITemplateMessaging) is None
    with pytest.raises(UnsupportedOperationError, match="ITemplateMessaging"):
        ig.require_capability(ITemplateMessaging)
    pipeline = MessengerPipeline(wa)
    assert isinstance(pipeline.capability(ITemplateMessaging), ITemplateMessaging)


def test_user_data_requests_are_a_whatsapp_capability_not_a_contract_method():
    for name in ("send_location_request", "send_contact_request"):
        assert not hasattr(IMessenger, name), name
        assert not hasattr(MessengerPipeline, name), name
    wa, _ = _wa()
    assert wa.capability(IUserDataRequests) is wa
    assert not {"send_location_request", "send_contact_request"} & set(
        wa.supported_operations
    )
    pipeline = MessengerPipeline(wa)
    assert isinstance(pipeline.capability(IUserDataRequests), IUserDataRequests)


async def test_pipeline_user_data_requests_run_the_middleware_chain():
    wa, _ = _wa()
    seen: list[tuple[str, str]] = []
    sent: list[tuple[str, str]] = []

    class _Spy:
        async def handle(self, invocation, call_next):
            seen.append((invocation.method_name, invocation.message_type))
            return await call_next(invocation)

    def _fake(name: str):
        async def send(body, target, reply_to_message_id=None):
            sent.append((name, body))
            return MessageResult(success=True, platform=PlatformType.WHATSAPP)

        return send

    wa.send_location_request = _fake("loc")  # type: ignore[method-assign]
    wa.send_contact_request = _fake("phone")  # type: ignore[method-assign]
    requests = MessengerPipeline(wa, middleware=[(_Spy(), 50)]).require_capability(
        IUserDataRequests
    )
    assert (await requests.send_location_request("Where?", WA_DM)).success
    assert (await requests.send_contact_request("Phone?", WA_DM)).success
    assert seen == [
        ("send_location_request", "location_request"),
        ("send_contact_request", "request_contact_info"),
    ]
    assert sent == [("loc", "Where?"), ("phone", "Phone?")]


def test_capability_resolves_by_interface_only():
    wa, _ = _wa()
    library = wa.capability(IMediaLibrary)
    assert library is not None
    assert wa.capability(type(library)) is None


async def test_whatsapp_carousel_uses_interactive_media_carousel():
    wa, client = _wa()
    result = await wa.send_carousel(
        [
            _card(1, ReplyButton(id="pick:1", title="Pick")),
            _card(2, ReplyButton(id="pick:2", title="Pick")),
        ],
        WA_DM,
        "Our picks",
    )
    assert result.success
    interactive = client.posted[0]["interactive"]
    assert interactive["type"] == "carousel"
    assert interactive["body"] == {"text": "Our picks"}
    first = interactive["action"]["cards"][0]
    assert first["card_index"] == 0
    # Live 400 (code 100) without it: Meta requires type on quick-reply cards.
    assert first["type"] == "cta_url"
    assert first["header"] == {"type": "image", "image": {"link": IMG}}
    assert first["body"] == {"text": "T1\nsub"}
    assert first["action"]["buttons"][0] == {
        "type": "quick_reply",
        "quick_reply": {"id": "pick:1", "title": "Pick"},
    }


async def test_whatsapp_carousel_url_cards_and_local_rules():
    wa, client = _wa()
    url = UrlButton(title="Open", url="https://example.com/x")
    assert (await wa.send_carousel([_card(1, url), _card(2, url)], WA_DM, "b")).success
    assert client.posted[0]["interactive"]["action"]["cards"][1]["type"] == "cta_url"
    with pytest.raises(ValueError, match="2–10 cards"):
        await wa.send_carousel([_card(1, url)], WA_DM, "b")
    with pytest.raises(ValueError, match="same button kind"):
        await wa.send_carousel(
            [_card(1, url), _card(2, ReplyButton(id="a", title="A"))], WA_DM, "b"
        )
    with pytest.raises(ValidationError, match="header"):
        MessageCard(title="x", buttons=(url,))  # type: ignore[call-arg]
    assert len(client.posted) == 1


async def test_whatsapp_media_library_download_returns_the_shared_read_result():
    ok = MediaDownloadResult(
        platform=PlatformType.WHATSAPP,
        success=True,
        file_data=b"abc",
        mime_type="image/jpeg",
        file_size=3,
    )
    wa, _ = _wa(_Media(ok))
    got = await wa.require_capability(IMediaLibrary).download("wa-media-1")
    assert got.found and got.value and got.value.content == b"abc"
    assert got.value.content_type == "image/jpeg"
    failed = MediaDownloadResult(
        platform=PlatformType.WHATSAPP, success=False, error="gone", error_code="404"
    )
    wa, _ = _wa(_Media(failed))
    miss = await wa.require_capability(IMediaLibrary).download("wa-media-1")
    assert miss.outcome is ReadOutcome.UNAVAILABLE and miss.error_code == "404"


async def test_instagram_media_library_download_reads_the_attachment_url():
    cdn = "https://scontent.cdninstagram.com/v/abc.jpg"

    def handler(request: httpx.Request) -> httpx.Response:
        assert "Authorization" not in request.headers
        return httpx.Response(
            200, content=b"img", headers={"content-type": "image/jpeg"}
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    ig = InstagramMessengerAdapter(
        inbox_ref=IG_REF,
        access_token=SecretStr("tkn"),
        session_provider=lambda: client,
        graph_api_version="v26.0",
        graph_base_url="https://graph.facebook.com",
    )
    async with client:
        got = await ig.require_capability(IMediaLibrary).download(cdn)
    assert got.found and got.value and got.value.content == b"img"


class _Uploads:
    def __init__(self) -> None:
        self.paths: list = []

    async def upload_media(self, path, media_type=None, filename=None):
        from wappa.domain.models.media_result import MediaUploadResult

        self.paths.append(path)
        return MediaUploadResult(
            platform=PlatformType.WHATSAPP, success=True, media_id="wa-up-1"
        )


async def test_upload_once_then_send_by_media_id_on_both_platforms(tmp_path):
    jpg = tmp_path / "menu.jpg"
    jpg.write_bytes(b"\xff\xd8test")

    uploads = _Uploads()
    wa, client = _wa(uploads)
    up = await wa.require_capability(IMediaLibrary).upload(jpg, MediaFamily.IMAGE)
    assert up.success and up.media_id == "wa-up-1" and uploads.paths == [jpg]

    sent: list[httpx.Request] = []

    def graph(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        if request.url.path.endswith("/message_attachments"):
            return httpx.Response(200, json={"attachment_id": "att-9"})
        return httpx.Response(200, json={"recipient_id": "u1", "message_id": "mid"})

    http = httpx.AsyncClient(transport=httpx.MockTransport(graph))
    ig = InstagramMessengerAdapter(
        inbox_ref=IG_REF,
        access_token=SecretStr("tkn"),
        session_provider=lambda: http,
        graph_api_version="v26.0",
        graph_base_url="https://graph.facebook.com",
    )
    ig_dm = DirectMessage(inbox_ref=IG_REF, addresses=DeliveryAddresses.of("u1"))
    async with http:
        stored = await ig.require_capability(IMediaLibrary).upload(
            jpg, MediaFamily.IMAGE
        )
        assert stored.success and stored.media_id == "att-9"
        sent_result = await ig.send_image(stored.media_id, ig_dm)
    assert sent_result.success
    import json as _json

    body = _json.loads(sent[-1].content)
    assert body["message"]["attachment"]["payload"] == {"attachment_id": "att-9"}


async def test_whatsapp_sticker_picks_the_webp_rendition():
    # Live: a PNG link was accepted (200) and then failed as status 131053.
    wa, client = _wa()
    for bad in ("https://example.com/s.png", "s.gif", ["a.png", "b.jpg"]):
        with pytest.raises(ValueError, match="webp"):
            await wa.send_sticker(bad, WA_DM)
    assert client.posted == []
    both = ["https://example.com/s.png", "https://example.com/s.webp?v=2"]
    assert (await wa.send_sticker(both, WA_DM)).success
    assert client.posted[0]["sticker"] == {"link": "https://example.com/s.webp?v=2"}


def test_pick_rendition_rules():
    from wappa.domain.media_renditions import pick_rendition

    webp = frozenset({".webp"})
    assert pick_rendition("1234567890", webp, what="x") == "1234567890"  # media ID
    assert pick_rendition(Path("s.WEBP"), webp, what="x") == Path("s.WEBP")
    with pytest.raises(ValueError, match="at least one"):
        pick_rendition([], webp, what="x")
    with pytest.raises(ValueError):  # two IDs: ambiguous, never guessed
        pick_rendition(["111", "222"], webp, what="x")


async def test_voice_note_flag_reaches_whatsapp_through_the_pipeline():
    """`is_voice` is on IMessenger, so app code behind the pipeline can ask for it."""
    from wappa.core.messaging.pipeline import MessengerPipeline

    wa, client = _wa()
    pipeline = MessengerPipeline(wa)
    voice = "https://example.com/v.ogg"

    assert (await pipeline.send_audio(voice, WA_DM, is_voice=True)).success
    assert (await pipeline.send_audio(voice, WA_DM)).success

    assert client.posted[0]["audio"] == {"link": voice, "voice": True}
    assert "voice" not in client.posted[1]["audio"]


async def test_whatsapp_voice_and_sticker_by_media_id_check_the_mime_type():
    """Live: non-OGG voice notes showed no waveform; a PNG sticker failed 131053."""
    from types import SimpleNamespace

    class _Media:
        def __init__(self, mime: str | None, success: bool = True) -> None:
            self.mime, self.success, self.asked = mime, success, []

        async def get_media_info(self, media_id: str):
            self.asked.append(media_id)
            return SimpleNamespace(success=self.success, mime_type=self.mime)

    wa, client = _wa(_Media("audio/mpeg"))
    with pytest.raises(ValueError, match="audio/mpeg"):
        await wa.send_audio("1234567890", WA_DM, is_voice=True)
    assert (await wa.send_audio("1234567890", WA_DM)).success  # plain audio: no lookup
    assert wa.media_handler.asked == ["1234567890"]

    for mime, ok in (("audio/ogg; codecs=opus", True), (None, True)):
        wa, client = _wa(_Media(mime))
        assert (await wa.send_audio("555", WA_DM, is_voice=True)).success is ok
        assert client.posted[0]["audio"] == {"id": "555", "voice": True}

    wa, client = _wa(_Media("audio/mpeg", success=False))  # lookup failed: Meta decides
    assert (await wa.send_audio("777", WA_DM, is_voice=True)).success

    wa, client = _wa(_Media("image/png"))  # live: PNG sticker failed 131053
    with pytest.raises(ValueError, match="sticker accepts WebP"):
        await wa.send_sticker("888", WA_DM)
    wa, client = _wa(_Media("image/webp"))
    assert (await wa.send_sticker("888", WA_DM)).success


async def test_voice_note_renditions_serve_both_platforms_from_one_call():
    """Live: an OGG voice note sent to Instagram failed with 100/2534080.

    One call with ``[.ogg, .m4a]`` and ``is_voice=True``: WhatsApp sends the
    OGG/Opus voice note, Instagram (no OGG) the M4A. No Platform branch.
    """
    both = ["https://example.com/v.ogg", "https://example.com/v.m4a"]

    wa, client = _wa()
    assert (await wa.send_audio(both, WA_DM, is_voice=True)).success
    assert client.posted[0]["audio"] == {"link": both[0], "voice": True}
    with pytest.raises(ValueError, match="voice note"):  # m4a never renders a waveform
        await wa.send_audio("https://example.com/v.m4a", WA_DM, is_voice=True)
    with pytest.raises(ValueError, match="WhatsApp audio"):
        await wa.send_audio("https://example.com/v.wav", WA_DM)
    assert len(client.posted) == 1

    sent: list[httpx.Request] = []

    def graph(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200, json={"recipient_id": "u1", "message_id": "mid"})

    http = httpx.AsyncClient(transport=httpx.MockTransport(graph))
    ig = InstagramMessengerAdapter(
        inbox_ref=IG_REF,
        access_token=SecretStr("tkn"),
        session_provider=lambda: http,
        graph_api_version="v26.0",
        graph_base_url="https://graph.facebook.com",
    )
    ig_dm = DirectMessage(inbox_ref=IG_REF, addresses=DeliveryAddresses.of("u1"))
    async with http:
        assert (await ig.send_audio(both, ig_dm, is_voice=True)).success
        # A local OGG cannot be attached or linked: rejected before any call.
        with pytest.raises(ValueError, match="Instagram audio.*Media Adaptation"):
            await ig.send_audio(Path("v.ogg"), ig_dm)
        assert len(sent) == 1
        # An OGG URL alone is shared as a link instead of failing.
        assert (await ig.send_audio("https://example.com/v.ogg", ig_dm)).success
    import json as _json

    body = _json.loads(sent[0].content)
    assert body["message"]["attachment"] == {
        "type": "audio",
        "payload": {"url": both[1]},
    }
    assert _json.loads(sent[1].content)["message"] == {
        "text": "🎵 v.ogg\nhttps://example.com/v.ogg"
    }
    assert len(sent) == 2
