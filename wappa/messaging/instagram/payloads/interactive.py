"""Wire shapes for buttons, list menus and carousel cards."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from wappa.domain.interactive import (
    CardButton,
    ListSection,
    MessageCard,
    ReplyButton,
    UrlButton,
)
from wappa.domain.messaging_targets import UnsupportedOperationError

from ..limits import BUTTON_TEXT_MAX
from .text import fold


def reply_button(button: ReplyButton) -> dict[str, Any]:
    return {"type": "postback", "title": button.title, "payload": button.id}


def url_button(button: UrlButton) -> dict[str, Any]:
    return {"type": "web_url", "title": button.title, "url": str(button.url)}


def card_button(button: CardButton) -> dict[str, Any]:
    return url_button(button) if isinstance(button, UrlButton) else reply_button(button)


def button_texts(
    header: str | None, body: str, footer: str | None
) -> tuple[str | None, str]:
    """Plan (lead text, button template text) so the template fits 640 chars.

    Header, body and footer fold into the template text when they fit;
    otherwise the header, then the body too, go first as a plain text message.
    The neutral limits (body ≤ 640, footer ≤ 60) make the last case fit.
    """
    full = fold(header, body, footer)
    if len(full) <= BUTTON_TEXT_MAX:
        return None, full
    tail = fold(body, footer)
    if len(tail) <= BUTTON_TEXT_MAX:
        return header, tail
    return fold(header, body), footer or ""


def card_element(card: MessageCard) -> dict[str, Any]:
    """One generic-template element.

    The element has one image slot: an image card shows ``url``; a video card
    shows ``poster_url`` and opens the video on tap unless the card has its
    own ``default_url``. A video without ``poster_url`` is rejected before any
    call: a card is one visual unit, so its media is never sent apart.
    """
    element: dict[str, Any] = {"title": card.title}
    if card.subtitle:
        element["subtitle"] = card.subtitle
    default_url = card.default_url
    if card.header.kind == "image":
        element["image_url"] = str(card.header.url)
    elif card.header.poster_url is None:
        raise UnsupportedOperationError(
            f"Instagram card {card.title!r}: a video card shows a still image; "
            "pass poster_url (a JPEG still of the video)"
        )
    else:
        element["image_url"] = str(card.header.poster_url)
        default_url = default_url or card.header.url
    if default_url:
        element["default_action"] = {"type": "web_url", "url": str(default_url)}
    element["buttons"] = [card_button(b) for b in card.buttons]
    return element


def list_menu(sections: Sequence[ListSection]) -> str | None:
    """Section titles and row descriptions as a numbered text menu.

    Quick replies show a row title only, so when a list carries more (a
    section title or a row description) the whole list is written out:
    ``"1. title — description"`` lines, numbered across sections, under their
    section titles. ``None`` when the quick replies already say everything.
    """
    if not any(
        section.title or any(row.description for row in section.rows)
        for section in sections
    ):
        return None
    blocks: list[str] = []
    number = 0
    for section in sections:
        lines = [section.title] if section.title else []
        for row in section.rows:
            number += 1
            line = f"{number}. {row.title}"
            lines.append(f"{line} — {row.description}" if row.description else line)
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)
