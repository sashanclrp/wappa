"""ButtonHeader is one neutral header for button and list messages (H-02)."""

from typing import Any

import pytest
from pydantic import ValidationError

from wappa.domain.interactive import ButtonHeader, ListRow, ListSection, ReplyButton
from wappa.messaging.whatsapp.handlers.whatsapp_interactive_handler import (
    WhatsAppInteractiveHandler,
)

RECIPIENT = "573001112233"
SECTIONS = [ListSection(title="Menu", rows=[ListRow(id="a", title="A")])]


class _Client:
    def __init__(self) -> None:
        self.posted: list[dict[str, Any]] = []

    async def post_request(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.posted.append(payload)
        return {
            "contacts": [{"input": RECIPIENT, "wa_id": RECIPIENT}],
            "messages": [{"id": "wamid.ok"}],
        }


def _handler() -> tuple[WhatsAppInteractiveHandler, _Client]:
    client = _Client()
    return WhatsAppInteractiveHandler(client, "pnid"), client  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "fields",
    [
        {},
        {"text": "Hi", "image_url": "https://example.com/a.png"},
        {"image_url": "https://example.com/a.png", "image_media_id": "m1"},
        {"text": "   "},
    ],
)
def test_button_header_needs_exactly_one_kind(fields: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        ButtonHeader(**fields)  # type: ignore[arg-type]


def test_list_section_rejects_duplicate_row_ids() -> None:
    with pytest.raises(ValidationError, match="unique"):
        ListSection(title="s", rows=[ListRow(id="a", title="A")] * 2)


@pytest.mark.parametrize(
    ("header", "wire"),
    [
        (ButtonHeader(text="Pick one"), {"type": "text", "text": "Pick one"}),
        (
            ButtonHeader(image_url="https://example.com/a.png"),
            {"type": "image", "image": {"link": "https://example.com/a.png"}},
        ),
        (
            ButtonHeader(image_media_id="media-1"),
            {"type": "image", "image": {"id": "media-1"}},
        ),
    ],
)
async def test_whatsapp_maps_button_header_to_wire(
    header: ButtonHeader, wire: dict[str, Any]
) -> None:
    handler, client = _handler()
    result = await handler.send_buttons_menu(
        RECIPIENT, "Body", [ReplyButton(id="y", title="Yes")], header=header
    )
    assert result.success
    assert client.posted[0]["interactive"]["header"] == wire


async def test_whatsapp_list_accepts_text_header_only() -> None:
    handler, client = _handler()
    ok = await handler.send_list_menu(
        RECIPIENT, "Body", "Open", SECTIONS, header=ButtonHeader(text="Menu")
    )
    assert ok.success
    assert client.posted[0]["interactive"]["header"] == {"type": "text", "text": "Menu"}

    rejected = await handler.send_list_menu(
        RECIPIENT,
        "Body",
        "Open",
        SECTIONS,
        header=ButtonHeader(image_url="https://example.com/a.png"),
    )
    assert not rejected.success
    assert rejected.error_code == "INVALID_HEADER_TYPE"
    assert len(client.posted) == 1


async def test_whatsapp_rejects_long_text_header_before_io() -> None:
    handler, client = _handler()
    result = await handler.send_buttons_menu(
        RECIPIENT,
        "Body",
        [ReplyButton(id="y", title="Yes")],
        header=ButtonHeader(text="x" * 61),
    )
    assert not result.success
    assert result.error_code == "HEADER_TOO_LONG"
    assert client.posted == []
