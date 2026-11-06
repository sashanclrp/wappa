"""WhatsApp-shaped interactive values with the shared minimum limits.

``InteractiveHeader`` mirrors the Cloud API header (text, image, video,
document by URL or media ID); every limit is the minimum across WhatsApp and
Instagram and holds when the value is built. Instagram emulates what it has no
slot for instead of rejecting WhatsApp-valid input.
"""

import json
from typing import Any

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from wappa.domain.inbox import InboxRef
from wappa.domain.interactive import (
    InteractiveHeader,
    ListRow,
    ListSection,
    MediaRef,
    ReplyButton,
    check_button_message,
    check_list_message,
)
from wappa.messaging import CommentRef, DeliveryAddresses, DirectMessage, PrivateReply
from wappa.messaging.instagram.messenger import InstagramMessenger
from wappa.messaging.whatsapp.handlers.whatsapp_interactive_handler import (
    WhatsAppInteractiveHandler,
)
from wappa.messaging.whatsapp.messenger.whatsapp_messenger import WhatsAppMessenger
from wappa.messaging.whatsapp.payload_builders import WhatsAppMediaPayloadBuilder
from wappa.schemas.core.types import PlatformType

PHONE = "573001112233"
WA_DM = DirectMessage(
    inbox_ref=InboxRef.whatsapp("pnid"), addresses=DeliveryAddresses.of(PHONE)
)
IG_REF = InboxRef(platform=PlatformType.INSTAGRAM, inbox_id="17890001")
IG_DM = DirectMessage(inbox_ref=IG_REF, addresses=DeliveryAddresses.of("12345"))
BUTTONS = [ReplyButton(id="y", title="Yes")]
SECTIONS = [ListSection(rows=[ListRow(id="a", title="A")])]


class _Client:
    def __init__(self) -> None:
        self.posted: list[dict[str, Any]] = []

    async def post_request(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.posted.append(payload)
        return {
            "contacts": [{"input": PHONE, "wa_id": PHONE}],
            "messages": [{"id": "wamid.ok"}],
        }


def _wa() -> tuple[WhatsAppMessenger, _Client]:
    client = _Client()
    messenger = WhatsAppMessenger(
        client=client,  # type: ignore[arg-type]
        media_handler=None,  # type: ignore[arg-type]
        interactive_handler=WhatsAppInteractiveHandler(client, "pnid"),  # type: ignore[arg-type]
        template_handler=None,  # type: ignore[arg-type]
        specialized_handler=None,  # type: ignore[arg-type]
        inbox_id="pnid",
    )
    return messenger, client


def _ig() -> tuple[InstagramMessenger, httpx.AsyncClient, list[dict[str, Any]]]:
    sent: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
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


# ── values: shape and limits at construction ────────────────────────────


@pytest.mark.parametrize(
    "fields",
    [
        {"kind": "text"},
        {"kind": "text", "text": "   "},
        {"kind": "text", "text": "x" * 61},
        {"kind": "text", "text": "Hi", "media": {"url": "https://example.com/a"}},
        {"kind": "image"},
        {"kind": "image", "text": "Hi", "media": {"media_id": "m1"}},
        {"kind": "video", "media": {"media_id": "m1"}, "filename": "a.mp4"},
        {"kind": "audio", "media": {"media_id": "m1"}},
    ],
)
def test_interactive_header_matches_its_kind(fields: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        InteractiveHeader.model_validate(fields)


def test_media_ref_needs_a_url_or_a_media_id() -> None:
    with pytest.raises(ValidationError):
        MediaRef.model_validate({})
    both = MediaRef.model_validate(
        {"url": "https://example.com/a.png", "media_id": "m1"}
    )
    assert both.media_id == "m1" and str(both.url) == "https://example.com/a.png"


@pytest.mark.parametrize(
    ("model", "fields"),
    [
        (ReplyButton, {"id": "a", "title": "t" * 21}),
        (ReplyButton, {"id": "a" * 257, "title": "t"}),
        (ListRow, {"id": "a", "title": "t" * 21}),  # WhatsApp 24, Instagram 20
        (ListRow, {"id": "a" * 201, "title": "t"}),
        (ListRow, {"id": "a", "title": "t", "description": "d" * 73}),
        (ListSection, {"title": "s" * 25, "rows": [{"id": "a", "title": "t"}]}),
        (ListSection, {"rows": [{"id": str(i), "title": "t"} for i in range(11)]}),
    ],
)
def test_limits_hold_when_values_are_built(
    model: type[ReplyButton | ListRow | ListSection], fields: dict[str, Any]
) -> None:
    with pytest.raises(ValidationError):
        model.model_validate(fields)


@pytest.mark.parametrize(
    ("buttons", "body", "footer", "match"),
    [
        (BUTTONS * 2, "Body", None, "unique"),
        ([ReplyButton(id=str(i), title="t") for i in range(4)], "Body", None, "1–3"),
        (BUTTONS, "b" * 641, None, "limit is 640"),  # WhatsApp 1024, Instagram 640
        (BUTTONS, "Body", "f" * 61, "limit is 60"),
    ],
)
def test_button_message_limits(
    buttons: list[ReplyButton], body: str, footer: str | None, match: str
) -> None:
    with pytest.raises(ValueError, match=match):
        check_button_message(buttons, body, footer)


def _section(title: str | None, *ids: str) -> ListSection:
    return ListSection(title=title, rows=[ListRow(id=i, title=i) for i in ids])


@pytest.mark.parametrize(
    ("sections", "body", "header", "match"),
    [
        ([_section("a", *"012345"), _section("b", *"6789X")], "B", None, "in total"),
        ([_section("a", "1"), _section("b", "1")], "B", None, "unique"),
        ([_section("a", "1"), _section(None, "2")], "B", None, "title"),
        ([_section(None, "1")] * 11, "B", None, "sections"),
        ([_section(None, "1")], "b" * 1001, None, "limit is 1000"),
        ([_section(None, "1")], "B", "h" * 61, "limit is 60"),
    ],
)
def test_list_message_limits(
    sections: list[ListSection], body: str, header: str | None, match: str
) -> None:
    with pytest.raises(ValueError, match=match):
        check_list_message(sections, body, "Open", header, None)


# ── WhatsApp maps 1:1 ───────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("header", "wire"),
    [
        (InteractiveHeader.of_text("Pick one"), {"type": "text", "text": "Pick one"}),
        (
            InteractiveHeader.of_image(url="https://example.com/a.png"),
            {"type": "image", "image": {"link": "https://example.com/a.png"}},
        ),
        (
            InteractiveHeader.of_image(media_id="media-1"),
            {"type": "image", "image": {"id": "media-1"}},
        ),
        (
            InteractiveHeader.of_video(url="https://example.com/a.mp4"),
            {"type": "video", "video": {"link": "https://example.com/a.mp4"}},
        ),
        (
            InteractiveHeader.of_document(media_id="doc-1", filename="menu.pdf"),
            {"type": "document", "document": {"id": "doc-1", "filename": "menu.pdf"}},
        ),
    ],
)
async def test_whatsapp_maps_interactive_header_to_wire(
    header: InteractiveHeader, wire: dict[str, Any]
) -> None:
    messenger, client = _wa()
    result = await messenger.send_button_message(BUTTONS, WA_DM, "Body", header=header)
    assert result.success
    assert client.posted[0]["interactive"]["header"] == wire


async def test_whatsapp_list_takes_a_text_header_and_untitled_single_section() -> None:
    messenger, client = _wa()
    result = await messenger.send_list_message(
        SECTIONS, WA_DM, "Body", "Open", header="Menu", footer="Foot"
    )
    assert result.success
    interactive = client.posted[0]["interactive"]
    assert interactive["header"] == {"type": "text", "text": "Menu"}
    assert interactive["footer"] == {"text": "Foot"}
    assert interactive["action"]["sections"] == [{"rows": [{"id": "a", "title": "A"}]}]


async def test_whatsapp_rejects_over_limit_body_before_io() -> None:
    messenger, client = _wa()
    with pytest.raises(ValueError, match="640"):
        await messenger.send_button_message(BUTTONS, WA_DM, "b" * 641)
    assert client.posted == []


async def test_whatsapp_document_caption_reaches_the_payload() -> None:
    payload = WhatsAppMediaPayloadBuilder().create_document_message(
        "doc-1", PHONE, filename="menu.pdf", caption="Today's menu"
    )
    assert payload["document"] == {
        "id": "doc-1",
        "caption": "Today's menu",
        "filename": "menu.pdf",
    }
    messenger, client = _wa()
    result = await messenger.send_document(
        "https://example.com/menu.pdf", WA_DM, filename="menu.pdf", caption="Menu"
    )
    assert result.success
    assert client.posted[0]["document"]["caption"] == "Menu"


# ── Instagram emulates instead of rejecting ─────────────────────────────


async def test_instagram_splits_long_text_on_word_boundaries() -> None:
    messenger, client, sent = _ig()
    words = " ".join(["palabra"] * 300)  # 2399 bytes
    async with client:
        result = await messenger.send_text(
            words, IG_DM, reply_to_message_id="m0", disable_preview=True
        )
    assert result.success and result.message_id == "mid.3"
    texts = [body["message"]["text"] for body in sent]
    assert len(texts) == 3
    assert all(len(t.encode()) <= 1000 for t in texts)
    assert all(not t.startswith(" ") and not t.endswith(" ") for t in texts)
    assert " ".join(texts) == words
    assert sent[0]["reply_to"] == {"mid": "m0"}
    assert all("reply_to" not in body for body in sent[1:])


async def test_instagram_splits_multibyte_text_by_bytes() -> None:
    messenger, client, sent = _ig()
    async with client:
        assert (await messenger.send_text("🌎" * 251, IG_DM)).success
    texts = [body["message"]["text"] for body in sent]
    assert [len(t) for t in texts] == [250, 1]


async def test_instagram_private_reply_cannot_be_split() -> None:
    messenger, client, sent = _ig()
    reply = PrivateReply(comment_ref=CommentRef(inbox_ref=IG_REF, comment_id="c1"))
    async with client:
        with pytest.raises(ValueError, match="UTF-8 bytes"):
            await messenger.send_text("x" * 1001, reply)
    assert sent == []


@pytest.mark.parametrize(
    ("header", "attachment"),
    [
        (
            InteractiveHeader.of_image(media_id="att-9"),
            {"type": "image", "payload": {"attachment_id": "att-9"}},
        ),
        (
            InteractiveHeader.of_video(url="https://example.com/a.mp4"),
            {"type": "video", "payload": {"url": "https://example.com/a.mp4"}},
        ),
        (
            InteractiveHeader.of_document(media_id="att-7", filename="menu.pdf"),
            {"type": "file", "payload": {"attachment_id": "att-7"}},
        ),
    ],
)
async def test_instagram_sends_media_header_first_then_full_body_buttons(
    header: InteractiveHeader, attachment: dict[str, Any]
) -> None:
    messenger, client, sent = _ig()
    body = "b" * 600  # longer than a generic card title (80)
    async with client:
        result = await messenger.send_button_message(
            BUTTONS, IG_DM, body, header=header, reply_to_message_id="m0"
        )
    assert result.success and result.message_id == "mid.2"
    assert sent[0]["message"]["attachment"] == attachment
    assert sent[0]["reply_to"] == {"mid": "m0"}
    template = sent[1]["message"]["attachment"]["payload"]
    assert template["template_type"] == "button" and template["text"] == body
    assert "reply_to" not in sent[1]


async def test_instagram_moves_header_out_when_folded_text_is_over_640() -> None:
    messenger, client, sent = _ig()
    body = "b" * 640
    async with client:
        result = await messenger.send_button_message(
            BUTTONS, IG_DM, body, header=InteractiveHeader.of_text("Head")
        )
    assert result.success
    assert sent[0]["message"] == {"text": "Head"}
    assert sent[1]["message"]["attachment"]["payload"]["text"] == body

    messenger, client, sent = _ig()
    async with client:
        result = await messenger.send_button_message(
            BUTTONS, IG_DM, body, header=InteractiveHeader.of_text("Head"), footer="F"
        )
    assert result.success
    assert sent[0]["message"] == {"text": f"Head\n\n{body}"}
    assert sent[1]["message"]["attachment"]["payload"]["text"] == "F"


async def test_instagram_list_splits_folded_text_and_keeps_quick_replies_last() -> None:
    messenger, client, sent = _ig()
    body = "é" * 1000  # 2000 bytes, within the 1000-character neutral limit
    async with client:
        result = await messenger.send_list_message(
            SECTIONS, IG_DM, body, "Open", header="Menu"
        )
    assert result.success
    assert all(len(b["message"]["text"].encode()) <= 1000 for b in sent)
    assert "quick_replies" not in sent[0]["message"]
    assert sent[-1]["message"]["quick_replies"] == [
        {"content_type": "text", "title": "A", "payload": "a"}
    ]


async def test_instagram_long_caption_follow_up_is_split() -> None:
    messenger, client, sent = _ig()
    caption = " ".join(["caption"] * 200)  # 1599 bytes
    async with client:
        result = await messenger.send_image(
            "https://example.com/a.png", IG_DM, caption=caption
        )
    assert result.success and result.message_id == "mid.1"
    assert "attachment" in sent[0]["message"]
    assert [len(b["message"]["text"].encode()) <= 1000 for b in sent[1:]] == [
        True,
        True,
    ]
