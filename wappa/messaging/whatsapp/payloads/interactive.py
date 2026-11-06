"""Cloud API payloads for interactive messages (buttons, lists, CTA URL, carousel, contact request).

Pure builders (no I/O). The neutral ``InteractiveHeader`` and ``MediaRef`` map
1:1 onto the Cloud API objects (``id`` before ``link``). The shared limits are
checked earlier by the neutral values and the ``check_*`` functions.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from wappa.domain.interactive import (
    InteractiveHeader,
    ListSection,
    MediaRef,
    MessageCard,
    ReplyButton,
    UrlButton,
)
from wappa.schemas.core.recipient import apply_recipient_to_payload


def wa_media_object(ref: MediaRef) -> dict[str, Any]:
    """Cloud API media object: the uploaded ``id`` when set, else the ``link``."""
    if ref.media_id is not None:
        return {"id": ref.media_id}
    return {"link": str(ref.url)}


def wa_header(header: InteractiveHeader) -> dict[str, Any]:
    """``InteractiveHeader`` maps 1:1 onto the Cloud API header object."""
    if header.kind == "text":
        return {"type": "text", "text": header.text}
    assert header.media is not None  # guaranteed by InteractiveHeader
    media = wa_media_object(header.media)
    if header.filename is not None:
        media["filename"] = header.filename
    return {"type": header.kind, header.kind: media}


def interactive_envelope(
    interactive_data: dict[str, Any], reply_to_message_id: str | None = None
) -> dict[str, Any]:
    """The ``interactive`` message around ``interactive_data``, before the recipient."""
    payload: dict[str, Any] = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "type": "interactive",
        "interactive": interactive_data,
    }
    if reply_to_message_id:
        payload["context"] = {"message_id": reply_to_message_id}
    return payload


def build_interactive_payload(
    recipient: str,
    interactive_data: dict[str, Any],
    reply_to_message_id: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "type": "interactive",
        "interactive": interactive_data,
    }
    apply_recipient_to_payload(payload, recipient)
    if reply_to_message_id:
        payload["context"] = {"message_id": reply_to_message_id}
    return payload


def buttons_interactive(
    body: str,
    buttons: list[ReplyButton],
    header: InteractiveHeader | None,
    footer_text: str | None,
) -> dict[str, Any]:
    interactive_data: dict[str, Any] = {
        "type": "button",
        "body": {"text": body},
        "action": {
            "buttons": [
                {"type": "reply", "reply": {"id": b.id, "title": b.title}}
                for b in buttons
            ]
        },
    }
    if header:
        interactive_data["header"] = wa_header(header)
    if footer_text:
        interactive_data["footer"] = {"text": footer_text}
    return interactive_data


def list_interactive(
    body: str,
    button_text: str,
    sections: list[ListSection],
    header: str | None,
    footer_text: str | None,
) -> dict[str, Any]:
    formatted_sections: list[dict[str, Any]] = []
    for section in sections:
        rows: list[dict[str, Any]] = []
        for row in section.rows:
            formatted_row = {"id": row.id, "title": row.title}
            if row.description:
                formatted_row["description"] = row.description
            rows.append(formatted_row)
        formatted: dict[str, Any] = {"rows": rows}
        if section.title is not None:
            formatted["title"] = section.title
        formatted_sections.append(formatted)

    interactive_data: dict[str, Any] = {
        "type": "list",
        "body": {"text": body},
        "action": {"button": button_text, "sections": formatted_sections},
    }
    if header:
        interactive_data["header"] = {"type": "text", "text": header}
    if footer_text:
        interactive_data["footer"] = {"text": footer_text}
    return interactive_data


def cta_interactive(body: str, button_text: str, button_url: str) -> dict[str, Any]:
    return {
        "type": "cta_url",
        "body": {"text": body},
        "action": {
            "name": "cta_url",
            "parameters": {"display_text": button_text, "url": button_url},
        },
    }


def contact_request_interactive(body: str) -> dict[str, Any]:
    return {
        "type": "request_contact_info",
        "body": {"text": body},
        "action": {"name": "request_contact_info"},
    }


def carousel_interactive(cards: Sequence[MessageCard], body: str) -> dict[str, Any]:
    return {
        "type": "carousel",
        "body": {"text": body},
        "action": {"cards": wa_cards(cards)},
    }


def wa_cards(cards: Sequence[MessageCard]) -> list[dict[str, Any]]:
    """Card count, text, header and button rules are checked by the neutral values."""
    out: list[dict[str, Any]] = []
    for index, card in enumerate(cards):
        text = "\n".join(p for p in (card.title, card.subtitle) if p)
        url_buttons = [b for b in card.buttons if isinstance(b, UrlButton)]
        replies = [b for b in card.buttons if isinstance(b, ReplyButton)]
        element: dict[str, Any] = {
            "card_index": index,
            # Meta requires type on every card and documents "cta_url" for
            # quick-reply cards too; omitting it is a 400 (code 100).
            "type": "cta_url",
            "header": {
                "type": card.header.kind,
                # Card headers take a public link only (no Media ID).
                card.header.kind: {"link": str(card.header.url)},
            },
            "body": {"text": text},
        }
        if url_buttons:
            element["action"] = {
                "name": "cta_url",
                "parameters": {
                    "display_text": url_buttons[0].title,
                    "url": str(url_buttons[0].url),
                },
            }
        else:
            element["action"] = {
                "buttons": [
                    {
                        "type": "quick_reply",
                        "quick_reply": {"id": b.id, "title": b.title},
                    }
                    for b in replies
                ]
            }
        out.append(element)
    return out
