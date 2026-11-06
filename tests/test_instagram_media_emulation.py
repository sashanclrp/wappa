"""Instagram emulates the media and lists WhatsApp accepts (ADR-0028 rule 4).

- a document URL in a format Instagram does not attach is shared as a text
  with the file name and the link; an audio or video URL Instagram cannot
  play is refused before any call, as on WhatsApp;
- http URLs pass through (Meta documents no scheme rule);
- uploads honour ``filename`` and ``mime_type`` and go out with an ASCII name;
- a local file in an unattachable format is still a ``ValueError`` telling the
  Host to convert it (Wappa does not convert media);
- list section titles and row descriptions fold into the text as a menu.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr

from wappa.domain.inbox import InboxRef
from wappa.domain.interactive import ListRow, ListSection
from wappa.domain.interfaces.media_library import MediaFamily
from wappa.domain.messaging_targets import DeliveryAddresses, DirectMessage
from wappa.messaging.instagram.media import ascii_name
from wappa.messaging.instagram.messenger import PARTS_KEY, InstagramMessengerAdapter
from wappa.schemas.core.types import PlatformType

IG_REF = InboxRef(platform=PlatformType.INSTAGRAM, inbox_id="17890001")
DM = DirectMessage(inbox_ref=IG_REF, addresses=DeliveryAddresses.of("u1"))


class _Graph:
    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.path.endswith("/message_attachments"):
            return httpx.Response(200, json={"attachment_id": "att-1"})
        return httpx.Response(
            200, json={"recipient_id": "u1", "message_id": f"mid.{len(self.requests)}"}
        )

    def messages(self) -> list[dict]:
        return [
            json.loads(r.content)["message"]
            for r in self.requests
            if r.url.path.endswith("/messages")
        ]


def _messenger(graph: _Graph) -> InstagramMessengerAdapter:
    http = httpx.AsyncClient(transport=httpx.MockTransport(graph))
    return InstagramMessengerAdapter(
        inbox_ref=IG_REF,
        access_token=SecretStr("tkn"),
        session_provider=lambda: http,
        graph_api_version="v26.0",
        graph_base_url="https://graph.facebook.com",
    )


async def test_an_unattachable_document_url_is_shared_as_a_named_link() -> None:
    graph = _Graph()
    url = "https://example.com/files/q3%20report.docx"
    result = await _messenger(graph).send_document(
        url, DM, filename="Q3 report.docx", caption="Numbers inside"
    )
    assert result.success
    assert graph.messages() == [
        {"text": f"📄 Q3 report.docx\n{url}"},
        {"text": "Numbers inside"},
    ]
    # One result: the link's message ID, both parts listed.
    assert result.message_id == "mid.1"
    assert result.platform_response[PARTS_KEY] == {
        "message_ids": ["mid.1", "mid.2"],
        "delivered": 2,
    }


@pytest.mark.parametrize(
    ("method", "url"),
    [
        ("send_video", "https://example.com/clip.3gp"),
        ("send_video", "https://example.com/clip.mov"),
        ("send_audio", "https://example.com/a%C3%B1o.mp3"),
        ("send_audio", "https://example.com/note.amr"),
    ],
)
async def test_unplayable_audio_and_video_urls_are_refused_before_io(
    method: str, url: str
) -> None:
    """Live 2026-11-06: such links reached the User as raw link text (audio)
    or an empty placeholder (MOV); like WhatsApp, Wappa refuses them."""
    graph = _Graph()
    with pytest.raises(ValueError, match="does not convert media"):
        await getattr(_messenger(graph), method)(url, DM)
    assert graph.requests == []


async def test_attachable_and_extensionless_urls_stay_attachments() -> None:
    graph = _Graph()
    messenger = _messenger(graph)
    await messenger.send_document("https://example.com/a.pdf", DM)
    await messenger.send_video("https://example.com/stream", DM)
    await messenger.send_image("http://plain.example/a.png", DM)  # http passes
    assert [m["attachment"] for m in graph.messages()] == [
        {"type": "file", "payload": {"url": "https://example.com/a.pdf"}},
        {"type": "video", "payload": {"url": "https://example.com/stream"}},
        {"type": "image", "payload": {"url": "http://plain.example/a.png"}},
    ]


async def test_a_local_file_in_an_unattachable_format_is_rejected_before_io(
    tmp_path: Path,
) -> None:
    doc = tmp_path / "plan.docx"
    doc.write_bytes(b"PK")
    graph = _Graph()
    with pytest.raises(ValueError, match="Wappa does not convert media"):
        await _messenger(graph).send_document(doc, DM)
    assert graph.requests == []


async def test_upload_honours_filename_and_mime_type_with_an_ascii_name(
    tmp_path: Path,
) -> None:
    source = tmp_path / "scan.bin.pdf"
    source.write_bytes(b"%PDF-1.4")
    graph = _Graph()
    library = _messenger(graph)._media
    result = await library.upload(
        source, MediaFamily.DOCUMENT, filename="Reseña año.pdf", mime_type="x/pdf"
    )
    assert result.success and result.media_id == "att-1"
    body = graph.requests[0].content
    assert b'filename="Resena ano.pdf"' in body
    assert b"Content-Type: x/pdf" in body


async def test_a_filename_without_suffix_keeps_the_files_suffix(
    tmp_path: Path,
) -> None:
    source = tmp_path / "Café.pdf"
    source.write_bytes(b"%PDF-1.4")
    graph = _Graph()
    library = _messenger(graph)._media
    await library.upload(source, MediaFamily.DOCUMENT)
    await library.upload(source, MediaFamily.DOCUMENT, filename="Invoice")
    assert b'filename="Cafe.pdf"' in graph.requests[0].content
    assert b"Content-Type: application/pdf" in graph.requests[0].content
    assert b'filename="Invoice.pdf"' in graph.requests[1].content


async def test_bytes_with_a_bare_filename_take_the_suffix_of_their_mime_type() -> None:
    graph = _Graph()
    library = _messenger(graph)._media
    result = await library.upload(
        b"%PDF-1.4",
        MediaFamily.DOCUMENT,
        filename="report",
        mime_type="application/pdf",
    )
    assert result.success
    assert b'filename="report.pdf"' in graph.requests[0].content
    assert b"Content-Type: application/pdf" in graph.requests[0].content


async def test_send_document_uploads_a_path_under_its_filename(
    tmp_path: Path,
) -> None:
    source = tmp_path / "tmp123.pdf"
    source.write_bytes(b"%PDF-1.4")
    graph = _Graph()
    result = await _messenger(graph).send_document(source, DM, filename="Offer.pdf")
    assert result.success
    assert b'filename="Offer.pdf"' in graph.requests[0].content
    assert graph.messages() == [
        {"attachment": {"type": "file", "payload": {"attachment_id": "att-1"}}}
    ]


def test_ascii_name_keeps_the_extension() -> None:
    assert ascii_name("Reseña.pdf") == "Resena.pdf"
    assert ascii_name("报告.pdf") == "file.pdf"
    assert ascii_name("b?*.png") == "b_.png"


async def test_a_list_folds_section_titles_and_row_descriptions_into_a_menu() -> None:
    graph = _Graph()
    sections = [
        ListSection(
            title="Pizza",
            rows=[
                ListRow(id="p1", title="Margherita", description="Tomato, basil"),
                ListRow(id="p2", title="Pepperoni"),
            ],
        ),
        ListSection(title="Drinks", rows=[ListRow(id="d1", title="Water")]),
    ]
    result = await _messenger(graph).send_list_message(
        sections, DM, "What would you like?", "Menu", footer="Tap one"
    )
    assert result.success
    [message] = graph.messages()
    assert message["text"] == (
        "What would you like?\n\n"
        "Pizza\n1. Margherita — Tomato, basil\n2. Pepperoni\n\n"
        "Drinks\n3. Water\n\n"
        "Tap one"
    )
    assert [q["payload"] for q in message["quick_replies"]] == ["p1", "p2", "d1"]


async def test_a_list_without_titles_or_descriptions_keeps_its_body() -> None:
    graph = _Graph()
    await _messenger(graph).send_list_message(
        [ListSection(rows=[ListRow(id="a", title="A")])], DM, "Pick", "Open"
    )
    assert graph.messages()[0]["text"] == "Pick"
