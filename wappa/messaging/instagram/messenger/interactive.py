"""Interactive sends: reply buttons, list, CTA button and carousel."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from wappa.domain.interactive import (
    InteractiveHeader,
    ListSection,
    MessageCard,
    ReplyButton,
    UrlButton,
    check_button_message,
    check_carousel,
    check_cta_message,
    check_list_message,
)
from wappa.domain.messaging_targets import DirectMessage
from wappa.domain.results import MessageResult

from ..limits import BUTTON_TEXT_MAX, BUTTONS_MAX
from ..payloads.interactive import (
    button_texts,
    card_element,
    list_menu,
    reply_button,
    url_button,
)
from ..payloads.text import check_len, fold
from ._base import _InstagramBase
from .delivery import _Parts


class _InteractiveMixin(_InstagramBase):
    async def _button_template(
        self,
        direct: DirectMessage,
        text: str,
        buttons: list[dict[str, Any]],
        operation: str,
        reply_to_message_id: str | None,
    ) -> MessageResult:
        if not text.strip():
            raise ValueError("Instagram button text must not be empty")
        check_len(text, BUTTON_TEXT_MAX, "Instagram button text")
        if not 1 <= len(buttons) <= BUTTONS_MAX:
            raise ValueError(f"Instagram buttons: 1–{BUTTONS_MAX} allowed")
        template = {"template_type": "button", "text": text, "buttons": buttons}
        return await self._send(
            direct,
            {"attachment": {"type": "template", "payload": template}},
            operation=operation,
            reply_to_message_id=reply_to_message_id,
        )

    async def send_button_message(
        self,
        buttons: list[ReplyButton],
        target: DirectMessage,
        body: str,
        header: InteractiveHeader | None = None,
        footer: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        """Reply buttons → Instagram postback buttons (button template).

        A tap returns as an ``InboundMessageWebhook`` whose selection is the
        button ``id``, exactly like a WhatsApp ``button_reply``. A text header
        and the footer fold into the template text; when the folded text is
        over 640 characters the header (then the body) goes first as plain
        text. A media header (image, video or document; by URL or by an
        ``attachment_id`` from ``IMediaLibrary.upload``) is sent first as its
        own attachment (a document URL Instagram cannot attach is shared as a
        text naming ``filename`` with the link), then the buttons with the
        full body. The reply context goes on the first message. The buttons
        result returns unless an earlier message is refused; that refusal
        returns and the buttons are not sent.
        """
        check_button_message(buttons, body, footer)
        return await self._headed_button_template(
            self._direct(target, "send_button_message"),
            header,
            body,
            footer,
            [reply_button(b) for b in buttons],
            "Instagram Button Message send",
            reply_to_message_id,
        )

    async def _headed_button_template(
        self,
        direct: DirectMessage,
        header: InteractiveHeader | None,
        body: str,
        footer: str | None,
        buttons: list[dict[str, Any]],
        operation: str,
        reply_to_message_id: str | None,
    ) -> MessageResult:
        """A button template under a WhatsApp-shaped header.

        A media header goes first as its own attachment (``url`` preferred,
        else the ``attachment_id``); a text header and the footer fold into
        the template text, with any overflow sent first as plain text. The
        reply context goes on the first message; the first refusal returns
        and nothing after it is sent.
        """
        text_header = header.text if header and header.kind == "text" else None
        parts = _Parts()
        lead, text = button_texts(text_header, body, footer)
        button_message = {
            "attachment": {
                "type": "template",
                "payload": {
                    "template_type": "button",
                    "text": text,
                    "buttons": buttons,
                },
            }
        }
        if header is not None and header.media is not None:
            source = (
                str(header.media.url)
                if header.media.url is not None
                else str(header.media.media_id)
            )
            media = await self._send_media(
                header.kind,
                source,
                direct,
                reply_to_message_id,
                filename=header.filename,
            )
            if not parts.add(media):
                if lead:
                    parts.skip_text(lead)
                parts.skip(button_message)
                return parts.result(media)
            reply_to_message_id = None
        if lead:
            intro = await self._send_texts(lead, direct, reply_to_message_id)
            if not parts.add(intro):
                parts.skip(button_message)
                return parts.result(intro)
            reply_to_message_id = None
        final = await self._button_template(
            direct, text, buttons, operation, reply_to_message_id
        )
        if not parts.ids:
            return final
        parts.add(final)
        return parts.result(final)

    async def send_list_message(
        self,
        sections: list[ListSection],
        target: DirectMessage,
        body: str,
        button_text: str,
        header: str | None = None,
        footer: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        """List rows → Instagram quick replies (Instagram has no list UI).

        Every row becomes one quick reply. A tap returns as an
        ``InboundMessageWebhook`` whose selection is the row ``id``, like a
        WhatsApp ``list_reply``. Quick replies show row titles only, so when a
        section has a title or a row a description, the list is also written
        into the text as a numbered menu (``"1. title — description"`` under
        each section title) after the body. The header and footer fold into
        the text, and a text over 1000 UTF-8 bytes is split, with the quick
        replies on the last message and one result listing every part.
        ``button_text`` (WhatsApp's list-opener label) has no Instagram slot.
        """
        check_list_message(sections, body, button_text, header, footer)
        direct = self._direct(target, "send_list_message")
        options = [
            {"content_type": "text", "title": row.title, "payload": row.id}
            for section in sections
            for row in section.rows
        ]
        _ = button_text  # WhatsApp list-opener label; no Instagram equivalent
        return await self._send_texts(
            fold(header, body, list_menu(sections), footer),
            direct,
            reply_to_message_id,
            last={"quick_replies": options},
            operation="Instagram list (quick replies) send",
        )

    async def send_cta_message(
        self,
        button_text: str,
        button_url: str,
        target: DirectMessage,
        body: str,
        header: InteractiveHeader | None = None,
        footer: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        """One URL button → Instagram ``web_url`` button template.

        The header is emulated as for ``send_button_message``: a text header
        and the footer fold into the text, a media header is sent first.
        """
        check_cta_message(button_text, button_url, body, footer)
        button = UrlButton.model_validate({"title": button_text, "url": button_url})
        return await self._headed_button_template(
            self._direct(target, "send_cta_message"),
            header,
            body,
            footer,
            [url_button(button)],
            "Instagram CTA send",
            reply_to_message_id,
        )

    async def send_carousel(
        self,
        cards: Sequence[MessageCard],
        target: DirectMessage,
        body: str,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        """``body`` as a text message, then the cards as a generic template.

        Instagram carousels carry no intro text, so ``body`` is sent first,
        carrying the reply context; if it is not accepted, the carousel is not
        sent and that result returns. Every card is checked before any call.
        """
        check_carousel(cards, body)
        direct = self._direct(target, "send_carousel")
        elements = [card_element(c) for c in cards]
        parts = _Parts()
        template = {"template_type": "generic", "elements": elements}
        carousel_message = {"attachment": {"type": "template", "payload": template}}
        intro = await self._send_texts(body, direct, reply_to_message_id)
        if not parts.add(intro, role="carousel_intro"):
            parts.skip(carousel_message)
            return parts.result(intro)
        final = await self._send(
            direct,
            {"attachment": {"type": "template", "payload": template}},
            operation="Instagram carousel send",
        )
        parts.add(final)
        return parts.result(final)
