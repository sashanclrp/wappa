"""WhatsApp-shaped carousels, CTA headers, contact arrays and media library.

The neutral values carry WhatsApp's full shape (card image or video by URL or
media ID, CTA media headers, several contact cards, sticker/bytes uploads,
media info and delete) with the shared minimum limits at construction.
WhatsApp maps them 1:1; Instagram emulates or rejects before any I/O.
"""

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from wappa.domain.inbox import InboxRef
from wappa.domain.interactive import (
    CARD_TEXT_MAX,
    CardMedia,
    InteractiveHeader,
    MessageCard,
    ReplyButton,
    check_carousel,
    check_cta_message,
)
from wappa.domain.interfaces.conversation_capabilities import ReadOutcome
from wappa.domain.interfaces.media_library import IMediaLibrary, MediaFamily
from wappa.domain.models.media_result import (
    MediaDeleteResult,
    MediaInfoResult,
    MediaUploadResult,
)
from wappa.domain.results import OperationOutcome
from wappa.messaging import (
    ContactCard,
    DeliveryAddresses,
    DirectMessage,
    UnsupportedOperationError,
)
from wappa.messaging.instagram.messenger import InstagramMessenger
from wappa.messaging.whatsapp.handlers.whatsapp_interactive_handler import (
    WhatsAppInteractiveHandler,
)
from wappa.messaging.whatsapp.handlers.whatsapp_specialized_handler import (
    WhatsAppSpecializedHandler,
)
from wappa.messaging.whatsapp.messenger.whatsapp_messenger import WhatsAppMessenger
from wappa.schemas.core.types import PlatformType

PHONE = "573001112233"
WA_DM = DirectMessage(
    inbox_ref=InboxRef.whatsapp("pnid"), addresses=DeliveryAddresses.of(PHONE)
)
IG_REF = InboxRef(platform=PlatformType.INSTAGRAM, inbox_id="17890001")
IG_DM = DirectMessage(inbox_ref=IG_REF, addresses=DeliveryAddresses.of("12345"))
IMG = "https://example.com/c.png"
VID = "https://example.com/v.mp4"
POSTER = "https://example.com/poster.jpg"
PICK = ReplyButton(id="pick", title="Pick")


class _Client:
    def __init__(self) -> None:
        self.posted: list[dict[str, Any]] = []

    async def post_request(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.posted.append(payload)
        return {
            "contacts": [{"input": PHONE, "wa_id": PHONE}],
            "messages": [{"id": "wamid.ok"}],
        }


class _MediaHandler:
    """The WhatsAppMediaHandler calls WhatsAppMediaLibrary makes."""

    def __init__(self) -> None:
        self.calls: list[tuple[Any, ...]] = []

    async def upload_media_from_bytes(
        self, file_data: bytes, media_type: str, filename: str
    ) -> MediaUploadResult:
        self.calls.append(("bytes", file_data, media_type, filename))
        return MediaUploadResult(success=True, media_id="wa-bytes-1")

    async def get_media_info(self, media_id: str) -> MediaInfoResult:
        if media_id == "gone":
            return MediaInfoResult(success=False, error="no", error_code="HTTP_404")
        return MediaInfoResult(
            success=True,
            media_id=media_id,
            url="https://lookaside.fbsbx.com/x",
            mime_type="image/jpeg",
            file_size=12,
            sha256="abc",
        )

    async def delete_media(self, media_id: str) -> MediaDeleteResult:
        if media_id == "gone":
            return MediaDeleteResult(success=False, error="no", error_code="HTTP_404")
        if media_id == "net":
            return MediaDeleteResult(
                success=False, error="timeout", error_code="DELETION_FAILED"
            )
        return MediaDeleteResult(success=True, media_id=media_id)


def _wa(media: object = None) -> tuple[WhatsAppMessenger, _Client]:
    client = _Client()
    messenger = WhatsAppMessenger(
        client=client,  # type: ignore[arg-type]
        media_handler=media,  # type: ignore[arg-type]
        interactive_handler=WhatsAppInteractiveHandler(client, "pnid"),  # type: ignore[arg-type]
        template_handler=None,  # type: ignore[arg-type]
        specialized_handler=WhatsAppSpecializedHandler(client, "pnid"),  # type: ignore[arg-type]
        inbox_id="pnid",
    )
    return messenger, client


def _ig() -> tuple[InstagramMessenger, httpx.AsyncClient, list[httpx.Request]]:
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        if request.url.path.endswith("/message_attachments"):
            return httpx.Response(200, json={"attachment_id": "att-1"})
        return httpx.Response(
            200, json={"recipient_id": "12345", "message_id": f"mid.{len(sent)}"}
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    messenger = InstagramMessenger(
        inbox_ref=IG_REF,
        access_token=SecretStr("tkn"),
        session_provider=lambda: client,
        graph_api_version="v26.0",
        graph_base_url="https://graph.facebook.com",
    )
    return messenger, client, sent


def _bodies(sent: list[httpx.Request]) -> list[dict[str, Any]]:
    return [json.loads(r.content) for r in sent]


def _card(header: CardMedia | None, title: str = "T") -> MessageCard:
    return MessageCard(header=header, title=title, subtitle="sub", buttons=(PICK,))


# ── limits at construction (minimum across WhatsApp and Instagram) ──────


@pytest.mark.parametrize(
    "fields",
    [
        {"title": "t" * 81},  # Instagram card title 80
        {"title": "t", "subtitle": "s" * 81},  # Instagram card subtitle 80
        {"title": "t" * 80, "subtitle": "s" * 80},  # WhatsApp card body 160
        {"title": "t", "buttons": [{"id": str(i), "title": "x"} for i in range(3)]},
    ],
)
def test_card_limits_hold_when_the_card_is_built(fields: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        MessageCard.model_validate(fields)
    assert CARD_TEXT_MAX == 160


def test_carousel_and_cta_limits_are_checked_before_any_call() -> None:
    card = _card(CardMedia.image(url=IMG))
    with pytest.raises(ValueError, match="2–10 cards"):
        check_carousel([card], "b")
    with pytest.raises(ValueError, match="Carousel body"):
        check_carousel([card, card], "b" * 1001)
    with pytest.raises(ValueError, match="CTA message body"):
        check_cta_message("Open", IMG, "b" * 641, None)
    with pytest.raises(ValidationError):
        check_cta_message("x" * 21, IMG, "b", None)  # WhatsApp display_text 20
    with pytest.raises(ValidationError):
        check_cta_message("Open", "ftp://example.com", "b", None)


# ── F3 carousel card media ──────────────────────────────────────────────


async def test_whatsapp_card_header_is_image_or_video_by_link() -> None:
    wa, client = _wa()
    cards = [
        _card(CardMedia.image(url=IMG)),
        _card(CardMedia.video(url=VID, poster_url=POSTER)),
    ]

    result = await wa.send_carousel(cards, WA_DM, "Picks", reply_to_message_id="w1")

    assert result.success
    payload = client.posted[0]
    headers = [c["header"] for c in payload["interactive"]["action"]["cards"]]
    # Card headers are a public link; poster_url never reaches WhatsApp.
    assert headers == [
        {"type": "image", "image": {"link": IMG}},
        {"type": "video", "video": {"link": VID}},
    ]
    assert payload["context"] == {"message_id": "w1"}


async def test_instagram_video_card_shows_its_poster_and_opens_the_video() -> None:
    ig, client, sent = _ig()
    cards = [
        _card(CardMedia.image(url=IMG)),
        _card(CardMedia.video(url=VID, poster_url=POSTER)),
        MessageCard(
            header=CardMedia.video(url=VID, poster_url=POSTER),
            title="Own link",
            default_url="https://example.com/page",
        ),
    ]
    async with client:
        result = await ig.send_carousel(cards, IG_DM, "Picks", reply_to_message_id="m1")

    assert result.success
    intro, carousel = _bodies(sent)
    assert intro["message"] == {"text": "Picks"} and intro["reply_to"] == {"mid": "m1"}
    assert "reply_to" not in carousel
    image, video, own = carousel["message"]["attachment"]["payload"]["elements"]
    assert image["image_url"] == IMG
    assert video["image_url"] == POSTER
    assert video["default_action"] == {"type": "web_url", "url": VID}
    assert own["default_action"]["url"] == "https://example.com/page"


def test_card_media_is_url_only() -> None:
    with pytest.raises(ValidationError):
        CardMedia.model_validate({"kind": "image", "media_id": "img-1"})
    with pytest.raises(ValidationError):
        CardMedia.model_validate({"kind": "image", "url": IMG, "media_id": "img-1"})


async def test_instagram_rejects_a_video_card_without_poster_before_any_call() -> None:
    ig, client, sent = _ig()
    async with client:
        with pytest.raises(UnsupportedOperationError, match="pass poster_url"):
            await ig.send_carousel(
                [_card(CardMedia.video(url=VID)), _card(CardMedia.image(url=IMG))],
                IG_DM,
                "b",
            )
    assert sent == []


# ── F4 CTA headers ──────────────────────────────────────────────────────


async def test_whatsapp_cta_header_maps_one_to_one() -> None:
    wa, client = _wa()
    header = InteractiveHeader.of_document(
        url="https://example.com/menu.pdf", filename="menu.pdf"
    )

    result = await wa.send_cta_message(
        "Open", "https://example.com", WA_DM, "Body", header=header, footer="F"
    )

    assert result.success
    interactive = client.posted[0]["interactive"]
    assert interactive["header"] == {
        "type": "document",
        "document": {"link": "https://example.com/menu.pdf", "filename": "menu.pdf"},
    }
    assert interactive["footer"] == {"text": "F"}


async def test_instagram_cta_sends_a_media_header_first_then_the_button() -> None:
    ig, client, sent = _ig()
    async with client:
        result = await ig.send_cta_message(
            "Open",
            "https://example.com",
            IG_DM,
            "Body",
            header=InteractiveHeader.of_video(url=VID),
            footer="Foot",
            reply_to_message_id="m1",
        )
        text_header = await ig.send_cta_message(
            "Open",
            "https://example.com",
            IG_DM,
            "Body",
            header=InteractiveHeader.of_text("Head"),
        )

    assert result.success and text_header.success
    media, cta, folded = _bodies(sent)
    assert media["message"]["attachment"] == {"type": "video", "payload": {"url": VID}}
    assert media["reply_to"] == {"mid": "m1"} and "reply_to" not in cta
    template = cta["message"]["attachment"]["payload"]
    assert template["text"] == "Body\n\nFoot"
    assert template["buttons"] == [
        {"type": "web_url", "title": "Open", "url": "https://example.com/"}
    ]
    assert folded["message"]["attachment"]["payload"]["text"] == "Head\n\nBody"


# ── F9 several contact cards; phones optional ───────────────────────────


def _contact(name: str, phone: str | None = None) -> ContactCard:
    data: dict[str, Any] = {"name": {"formatted_name": name}}
    if phone:
        data["phones"] = [{"phone": phone}]
    return ContactCard.model_validate(data)


async def test_whatsapp_sends_several_cards_in_one_contacts_message() -> None:
    wa, client = _wa()

    result = await wa.send_contact(
        [_contact("Ana", "+57 300 111 2233"), _contact("Front desk")], WA_DM
    )

    assert result.success
    contacts = client.posted[0]["contacts"]
    assert contacts == [
        {"name": {"formatted_name": "Ana"}, "phones": [{"phone": "+57 300 111 2233"}]},
        {"name": {"formatted_name": "Front desk"}},
    ]
    assert (await wa.send_contact(_contact("Solo"), WA_DM)).success


async def test_instagram_renders_each_card_as_a_text_block_split_over_1000_bytes() -> (
    None
):
    ig, client, sent = _ig()
    many = [
        _contact(f"Person {i:02d} " + "x" * 60, "+57 300 111 2233") for i in range(14)
    ]
    async with client:
        short = await ig.send_contact([_contact("Ana"), _contact("Bo")], IG_DM)
        long = await ig.send_contact(many, IG_DM)

    assert short.success and long.success
    bodies = _bodies(sent)
    assert bodies[0]["message"]["text"] == "👤 Ana\n\n👤 Bo"
    chunks = [b["message"]["text"] for b in bodies[1:]]
    assert len(chunks) > 1
    assert all(len(c.encode("utf-8")) <= 1000 for c in chunks)


async def test_send_contact_needs_at_least_one_card() -> None:
    wa, _ = _wa()
    with pytest.raises(ValueError, match="at least one"):
        await wa.send_contact([], WA_DM)


# ── F10 media library: sticker, bytes, info, delete ─────────────────────


async def test_whatsapp_library_uploads_bytes_and_reads_info_and_deletes() -> None:
    handler = _MediaHandler()
    wa, _ = _wa(handler)
    library = wa.require_capability(IMediaLibrary)

    up = await library.upload(b"webp", MediaFamily.STICKER, filename="s.webp")
    info = await library.info("m1")
    missing = await library.info("gone")
    deleted = await library.delete("m1")
    refused = await library.delete("gone")
    unknown = await library.delete("net")

    assert up.success and up.media_id == "wa-bytes-1"
    assert handler.calls == [("bytes", b"webp", "image/webp", "s.webp")]
    assert info.found and info.value is not None
    assert (info.value.mime_type, info.value.size, info.value.sha256) == (
        "image/jpeg",
        12,
        "abc",
    )
    assert missing.outcome is ReadOutcome.NOT_FOUND
    assert deleted.success and deleted.media_id == "m1"
    assert refused.outcome is OperationOutcome.REJECTED
    assert unknown.outcome is OperationOutcome.INDETERMINATE
    with pytest.raises(ValueError, match="mime_type"):
        await library.upload(b"?", MediaFamily.DOCUMENT)


async def test_instagram_library_uploads_bytes_and_stickers_as_images(
    tmp_path: Path,
) -> None:
    ig, client, sent = _ig()
    sticker = tmp_path / "sticker.png"
    sticker.write_bytes(b"png")
    library = ig.require_capability(IMediaLibrary)
    async with client:
        from_bytes = await library.upload(
            b"jpeg-bytes", MediaFamily.IMAGE, mime_type="image/jpeg"
        )
        from_sticker = await library.upload(sticker, MediaFamily.STICKER)
        with pytest.raises(ValueError, match="filename or a known mime_type"):
            await library.upload(b"?", MediaFamily.IMAGE)
        with pytest.raises(UnsupportedOperationError, match="describe"):
            await library.info("att-1")
        with pytest.raises(UnsupportedOperationError, match="delete"):
            await library.delete("att-1")

    assert from_bytes.success and from_sticker.success
    first, second = (r.content for r in sent)
    assert b'filename="upload.jpg"' in first and b"jpeg-bytes" in first
    assert b'"type": "image"' in second and b'filename="sticker.png"' in second


async def test_limits_endpoint_reports_the_shared_cta_and_card_limits() -> None:
    from wappa.api.routes.interactive import get_interactive_limits

    limits = await get_interactive_limits()

    assert limits["cta_messages"]["max_button_text_length"] == 20
    assert limits["cta_messages"]["max_body_length"] == 640
    assert limits["carousels"]["max_card_title_length"] == 80
    assert limits["carousels"]["max_card_text_length"] == 160
    assert limits["carousels"]["max_card_buttons"] == 2
    assert limits["carousels"]["supported_card_header_kinds"] == ["image", "video"]
