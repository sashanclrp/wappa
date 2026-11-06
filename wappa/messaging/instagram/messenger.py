"""Inbox-bound Instagram Messenger (Unified Login, Graph v26.0).

Native wire formats (``POST /{ig-account-id}/messages``):

- text: ``{"recipient": {"id"}, "message": {"text"}}`` (≤ 1000 UTF-8 bytes)
- private reply: ``{"recipient": {"comment_id"}, "message": {"text"}}``
- media: ``message.attachment = {"type": image|audio|video|file,
  "payload": {"url"}}`` or ``{"attachment_id"}`` after upload
Contract mappings (ADR-0016: one Messenger method per action):

- ``send_button_message`` → ``template_type = button`` with ``postback``
  buttons (text ≤ 640, 1–3), or a one-element ``generic`` card for an image
  header
- ``send_list_message`` → ``message.quick_replies[]`` (≤ 13, title ≤ 20)
- ``send_cta_message`` → ``template_type = button`` with one ``web_url``
- ``send_carousel`` → intro text, then ``template_type = generic`` (2–10)
- ``mark_as_read`` → ``sender_action`` ``mark_seen`` then ``typing_on``
- media by https URL, by ``IMediaLibrary.upload`` attachment_id, or a ``Path``
  (uploaded first)
- ``send_location`` / ``send_contact`` → text (maps link / contact card);
  ``send_sticker`` → image
- ``send_location_request`` / ``send_contact_request`` → not available
  (WhatsApp-only core actions; a text prompt would not return the data)
- reply: top-level ``reply_to: {"mid"}``

Known local constraints are rejected before I/O; provider refusals and
unknown outcomes are returned, never retried.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, cast

import httpx
from pydantic import SecretStr

from wappa.domain.contacts import ContactCard
from wappa.domain.inbox.identity import InboxRef
from wappa.domain.interactive import (
    ButtonHeader,
    CardButton,
    ListSection,
    MessageCard,
    ReplyButton,
    UrlButton,
)
from wappa.domain.interfaces.conversation_capabilities import (
    IAttachmentMediaReader,
    ICommentControls,
    IConversationContentReader,
)
from wappa.domain.interfaces.history_reader import IConversationHistoryReader
from wappa.domain.interfaces.media_library import IMediaLibrary, MediaFamily
from wappa.domain.interfaces.messaging_interface import IMessenger
from wappa.domain.interfaces.sent_message_registry import ISentMessageRegistry
from wappa.domain.media_renditions import MediaRenditions, pick_rendition
from wappa.domain.messaging_targets import (
    DirectMessage,
    MessageTarget,
    PrivateReply,
    UnsupportedOperationError,
    require_direct_message,
)
from wappa.domain.results import MessageResult, OperationOutcome
from wappa.schemas.core.types import PlatformType

from .content import InstagramCommentControls, InstagramContentReader
from .graph import GraphResponse, InstagramGraphClient
from .history import InstagramHistoryReader
from .media import (
    MEDIA_RULES,
    InstagramAttachmentReader,
    validate_media_url,
)
from .media_library import InstagramMediaLibrary

TEXT_MAX_BYTES = 1000
QUICK_REPLY_MAX = 13
QUICK_REPLY_TITLE_MAX = 20
BUTTON_TEXT_MAX = 640
BUTTON_TITLE_MAX = 20
BUTTONS_MAX = 3
CARD_TEXT_MAX = 80
CAROUSEL_MIN = 2
CAROUSEL_MAX = 10
PAYLOAD_MAX = 1000
COMMENT_REPLY_MAX = 2200


def _check_text(text: str, *, what: str = "Instagram text") -> str:
    if not text or not text.strip():
        raise ValueError(f"{what} must not be empty")
    size = len(text.encode("utf-8"))
    if size > TEXT_MAX_BYTES:
        raise ValueError(f"{what} is {size} UTF-8 bytes; limit is {TEXT_MAX_BYTES}")
    return text


def _check_len(value: str, limit: int, what: str) -> str:
    if len(value) > limit:
        raise ValueError(f"{what} is {len(value)} characters; limit is {limit}")
    return value


def _fold(*parts: str | None) -> str:
    """Join header/body/footer for Platforms without separate slots."""
    return "\n\n".join(p.strip() for p in parts if p and p.strip())


def _reply(button: ReplyButton) -> dict[str, Any]:
    _check_len(button.title, BUTTON_TITLE_MAX, "Instagram button title")
    _check_len(button.id, PAYLOAD_MAX, "Instagram button id")
    return {"type": "postback", "title": button.title, "payload": button.id}


def _url_button(button: UrlButton) -> dict[str, Any]:
    _check_len(button.title, BUTTON_TITLE_MAX, "Instagram button title")
    return {"type": "web_url", "title": button.title, "url": str(button.url)}


def _card_button(button: CardButton) -> dict[str, Any]:
    return _url_button(button) if isinstance(button, UrlButton) else _reply(button)


def _header_image_url(header: ButtonHeader) -> str:
    if header.image_url is None:
        raise UnsupportedOperationError(
            "Instagram image headers need image_url; Platform media IDs from "
            "another Platform do not exist on Instagram"
        )
    return validate_media_url(str(header.image_url))


def _check_carousel(cards: Sequence[MessageCard]) -> None:
    if not CAROUSEL_MIN <= len(cards) <= CAROUSEL_MAX:
        raise ValueError(
            f"Carousels need {CAROUSEL_MIN}–{CAROUSEL_MAX} cards; for one card use "
            "send_button_message with an image header"
        )


def _card(card: MessageCard) -> dict[str, Any]:
    _check_len(card.title, CARD_TEXT_MAX, "Instagram card title")
    element: dict[str, Any] = {"title": card.title}
    if card.subtitle:
        element["subtitle"] = _check_len(
            card.subtitle, CARD_TEXT_MAX, "Instagram card subtitle"
        )
    if card.image_url:
        element["image_url"] = str(card.image_url)
    if card.default_url:
        element["default_action"] = {"type": "web_url", "url": str(card.default_url)}
    if card.buttons:
        if len(card.buttons) > BUTTONS_MAX:
            raise ValueError(f"Instagram cards allow at most {BUTTONS_MAX} buttons")
        element["buttons"] = [_card_button(b) for b in card.buttons]
    if len(element) == 1:
        raise ValueError(
            "Instagram cards need a subtitle, image, default URL or button"
        )
    return element


class InstagramMessenger(IMessenger):
    """One professional account; lifecycle-owned HTTP and no automatic retries."""

    _OPERATIONS = frozenset(
        {
            "send_text",
            "send_text:private_reply",
            "send_image",
            "send_audio",
            "send_video",
            "send_document",
            "send_button_message",
            "send_list_message",
            "send_cta_message",
            "send_carousel",
            "mark_as_read",
            "send_sticker",
            "send_location",
            "send_contact",
        }
    )

    def __init__(
        self,
        *,
        inbox_ref: InboxRef,
        access_token: SecretStr,
        session_provider: Callable[[], httpx.AsyncClient],
        graph_api_version: str,
        graph_base_url: str,
        media_download_client_provider: Callable[[], httpx.AsyncClient] | None = None,
        sent_registry: ISentMessageRegistry | None = None,
    ) -> None:
        if inbox_ref.platform is not PlatformType.INSTAGRAM:
            raise ValueError("InstagramMessenger requires an Instagram Inbox")
        self._inbox_ref = inbox_ref
        # Instagram echoes Wappa's own sends; recording them lets the Inbound
        # Runtime drop those echoes (ADR-0018).
        self._sent_registry = sent_registry
        self._graph = InstagramGraphClient(
            inbox_ref=inbox_ref,
            access_token=access_token,
            session_provider=session_provider,
            graph_api_version=graph_api_version,
            graph_base_url=graph_base_url,
        )
        self._attachments = InstagramAttachmentReader(
            media_download_client_provider or session_provider
        )
        self._media = InstagramMediaLibrary(self._graph, self._attachments)
        # Instagram-only actions (ADR-0016 exceptions), capability-gated.
        self._capabilities: dict[type, object] = {
            ICommentControls: InstagramCommentControls(self._graph),
            IConversationContentReader: InstagramContentReader(self._graph),
            IAttachmentMediaReader: self._attachments,
            IMediaLibrary: self._media,
            IConversationHistoryReader: InstagramHistoryReader(self._graph),
        }

    # ── identity / discovery ────────────────────────────────────────────

    @property
    def platform(self) -> PlatformType:
        return PlatformType.INSTAGRAM

    @property
    def inbox_id(self) -> str:
        return self._inbox_ref.inbox_id

    @property
    def inbox_ref(self) -> InboxRef:
        return self._inbox_ref

    @property
    def supported_operations(self) -> frozenset[str]:
        return self._OPERATIONS

    def capability[C](self, kind: Callable[..., C]) -> C | None:
        wanted = cast(type, kind)
        found = self._capabilities.get(wanted)
        if found is None:
            # Allow asking for the concrete Instagram class as well.
            found = next(
                (c for c in self._capabilities.values() if isinstance(c, wanted)),
                None,
            )
        return cast(C | None, found)

    # ── transport ───────────────────────────────────────────────────────

    def _result(
        self, response: GraphResponse, recipient: str, operation: str
    ) -> MessageResult:
        message_id = response.body.get("message_id") if response.ok else None
        if response.ok and isinstance(message_id, str) and message_id:
            native_recipient = response.body.get("recipient_id")
            return MessageResult(
                success=True,
                platform=self.platform,
                inbox_id=self.inbox_id,
                recipient=native_recipient
                if isinstance(native_recipient, str) and native_recipient
                else recipient,
                message_id=message_id,
                platform_response=response.body,
            )
        if response.ok:
            # 2xx without a message ID: we cannot prove what happened.
            return MessageResult(
                success=False,
                platform=self.platform,
                inbox_id=self.inbox_id,
                recipient=recipient,
                error=f"{operation} outcome is unknown (no message_id); "
                "do not automatically resend",
                error_code="INDETERMINATE",
            )
        return MessageResult(
            success=False,
            platform=self.platform,
            inbox_id=self.inbox_id,
            recipient=recipient,
            error=response.error,
            error_code=response.error_code,
        )

    async def _send(
        self,
        target: MessageTarget,
        message: dict[str, Any],
        *,
        operation: str,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        if isinstance(target, PrivateReply):
            if reply_to_message_id:
                raise UnsupportedOperationError(
                    "A PrivateReply cannot also reply to a DM message"
                )
            comment_id = target.resolve(self._inbox_ref)
            recipient: dict[str, str] = {"comment_id": comment_id}
            address = target.address
        else:
            address = target.resolve(self._inbox_ref)
            recipient = {"id": address}
        body: dict[str, Any] = {"recipient": recipient, "message": message}
        if reply_to_message_id:
            body["reply_to"] = {"mid": reply_to_message_id}
        response = await self._graph.request(
            "POST", f"{self.inbox_id}/messages", json=body, operation=operation
        )
        result = self._result(response, address, operation)
        if result.success and result.message_id and self._sent_registry is not None:
            await self._sent_registry.record(self._inbox_ref, result.message_id)
        return result

    # ── text ────────────────────────────────────────────────────────────

    async def send_text(
        self,
        text: str,
        target: MessageTarget,
        reply_to_message_id: str | None = None,
        disable_preview: bool = False,
    ) -> MessageResult:
        if disable_preview:
            raise UnsupportedOperationError(
                "Instagram preview suppression is not implemented"
            )
        if not isinstance(target, DirectMessage | PrivateReply):
            raise TypeError("send_text requires a DirectMessage or PrivateReply")
        # Validate target scope before content so wrong-Inbox fails first.
        target.resolve(self._inbox_ref)
        return await self._send(
            target,
            {"text": _check_text(text)},
            operation="Instagram private reply"
            if isinstance(target, PrivateReply)
            else "Instagram text send",
            reply_to_message_id=reply_to_message_id,
        )

    # ── media ───────────────────────────────────────────────────────────

    async def _send_media(
        self,
        family: str,
        source: str | Path,
        target: DirectMessage,
        reply_to_message_id: str | None,
    ) -> MessageResult:
        direct = require_direct_message(target, f"Instagram send_{family}")
        direct.resolve(self._inbox_ref)
        rule_type = {"document": "file"}.get(family, family)
        payload: dict[str, Any]
        if isinstance(source, Path):
            uploaded = await self._media.upload(source, MediaFamily(family))
            if not uploaded.success or not uploaded.media_id:
                return MessageResult(
                    success=False,
                    platform=self.platform,
                    inbox_id=self.inbox_id,
                    recipient=direct.recipient_id,
                    error=uploaded.error,
                    error_code=uploaded.error_code or "INDETERMINATE",
                )
            payload = {"attachment_id": uploaded.media_id}
        elif isinstance(source, str) and "://" in source:
            payload = {"url": validate_media_url(source)}
        elif isinstance(source, str) and source.strip():
            # A reusable attachment_id from IMediaLibrary.upload.
            payload = {"attachment_id": source}
        else:
            raise TypeError(
                "media source must be an https URL, an uploaded media_id or a Path"
            )
        return await self._send(
            direct,
            {"attachment": {"type": rule_type, "payload": payload}},
            operation=f"Instagram {family} send",
            reply_to_message_id=reply_to_message_id,
        )

    async def _media_with_caption(
        self,
        family: str,
        source: str | Path,
        target: DirectMessage,
        caption: str | None,
        reply_to_message_id: str | None,
    ) -> MessageResult:
        """Instagram attachments carry no caption: send it as a follow-up text.

        The media result returns unless the caption was refused, in which case
        that refusal returns (the media was already delivered; nothing retries).
        """
        result = await self._send_media(family, source, target, reply_to_message_id)
        if caption and caption.strip() and result.success:
            follow_up = await self.send_text(caption, target)
            if not follow_up.success:
                return follow_up
        return result

    async def send_image(
        self,
        image_source: str | Path,
        target: DirectMessage,
        caption: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        return await self._media_with_caption(
            "image", image_source, target, caption, reply_to_message_id
        )

    async def send_video(
        self,
        video_source: str | Path,
        target: DirectMessage,
        caption: str | None = None,
        reply_to_message_id: str | None = None,
        transcript: str | None = None,
    ) -> MessageResult:
        _ = transcript  # Host metadata, never shown to the User (as on WhatsApp)
        return await self._media_with_caption(
            "video", video_source, target, caption, reply_to_message_id
        )

    async def send_audio(
        self,
        audio_source: MediaRenditions,
        target: DirectMessage,
        reply_to_message_id: str | None = None,
        transcript: str | None = None,
        is_voice: bool = False,
    ) -> MessageResult:
        """Instagram shows every audio attachment as a voice message.

        ``is_voice`` therefore changes nothing here; the rendition is picked
        from Instagram's audio formats (no OGG), so ``[note.ogg, note.m4a]``
        serves a WhatsApp voice note and Instagram from one call.
        """
        _ = transcript  # Host metadata, never shown to the User (as on WhatsApp)
        _ = is_voice
        source = pick_rendition(
            audio_source, MEDIA_RULES["audio"].extensions, what="Instagram audio"
        )
        return await self._send_media("audio", source, target, reply_to_message_id)

    async def send_document(
        self,
        document_source: str | Path,
        target: DirectMessage,
        filename: str | None = None,
        caption: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        # Instagram shows the uploaded/source file name; ``filename`` is
        # WhatsApp display presentation with no Instagram slot.
        _ = filename
        return await self._media_with_caption(
            "document", document_source, target, caption, reply_to_message_id
        )

    # ── specialized sends, adapted (ADR-0016) ──────────────────────────

    async def send_sticker(
        self,
        sticker_source: MediaRenditions,
        target: DirectMessage,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        """Instagram has no custom stickers: the sticker is sent as an image.

        Instagram images are png/jpeg/gif while WhatsApp stickers are WebP:
        pass both renditions (``[sticker.webp, sticker.png]``) and each
        Platform picks the one it accepts.
        """
        source = pick_rendition(
            sticker_source,
            MEDIA_RULES["image"].extensions,
            what="Instagram sticker (sent as an image)",
        )
        return await self._send_media("image", source, target, reply_to_message_id)

    async def send_location(
        self,
        latitude: float,
        longitude: float,
        target: DirectMessage,
        name: str | None = None,
        address: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        """Instagram has no location message: name, address and a maps link as text."""
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            raise ValueError("latitude/longitude out of range")
        link = f"https://www.google.com/maps/search/?api=1&query={latitude},{longitude}"
        text = "\n".join(p for p in (name, address, f"📍 {link}") if p)
        return await self.send_text(
            text, target, reply_to_message_id=reply_to_message_id
        )

    async def send_contact(
        self,
        contact: ContactCard,
        target: DirectMessage,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        """Instagram has no contact message: the contact card is sent as text.

        ``contact`` is the same typed ``ContactCard`` WhatsApp sends natively.
        """
        card = contact
        lines = [f"👤 {card.name.formatted_name}"]
        if card.org and (card.org.company or card.org.title):
            lines.append(" · ".join(p for p in (card.org.title, card.org.company) if p))
        lines += [f"📞 {p.phone}" for p in card.phones]
        lines += [f"✉️ {e.email}" for e in card.emails or []]
        lines += [f"🔗 {u.url}" for u in card.urls or []]
        return await self.send_text(
            "\n".join(lines), target, reply_to_message_id=reply_to_message_id
        )

    # ── interactive (WhatsApp-shaped contract, ADR-0016) ────────────────

    def _direct(self, target: DirectMessage, operation: str) -> DirectMessage:
        direct = require_direct_message(target, f"Instagram {operation}")
        direct.resolve(self._inbox_ref)
        return direct

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
        _check_len(text, BUTTON_TEXT_MAX, "Instagram button text")
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
        header: ButtonHeader | None = None,
        footer: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        """Reply buttons → Instagram postback buttons.

        A tap returns as an ``InboundMessageWebhook`` whose selection is the
        button ``id``, exactly like a WhatsApp ``button_reply``. A text header
        and the footer fold into the text. An image header (``image_url``)
        makes it a generic card: image, ``body`` as title (≤ 80), ``footer`` as
        subtitle. An ``image_media_id`` header has no Instagram equivalent.
        """
        direct = self._direct(target, "send_button_message")
        converted = [_reply(b) for b in buttons]
        if header is not None and header.kind == "image":
            if not 1 <= len(converted) <= BUTTONS_MAX:
                raise ValueError(f"Instagram buttons: 1–{BUTTONS_MAX} allowed")
            element: dict[str, Any] = {
                "title": _check_len(body, CARD_TEXT_MAX, "Instagram card title"),
                "image_url": _header_image_url(header),
                "buttons": converted,
            }
            if footer:
                element["subtitle"] = _check_len(
                    footer, CARD_TEXT_MAX, "Instagram card subtitle"
                )
            return await self._send(
                direct,
                {
                    "attachment": {
                        "type": "template",
                        "payload": {"template_type": "generic", "elements": [element]},
                    }
                },
                operation="Instagram button card send",
                reply_to_message_id=reply_to_message_id,
            )
        text = _fold(header.text if header else None, body, footer)
        return await self._button_template(
            direct,
            text,
            converted,
            "Instagram Button Message send",
            reply_to_message_id,
        )

    async def send_list_message(
        self,
        sections: list[ListSection],
        target: DirectMessage,
        body: str,
        button_text: str,
        header: ButtonHeader | None = None,
        footer: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        """List rows → Instagram quick replies (Instagram has no list UI).

        Every row becomes one quick reply (≤ 13, title ≤ 20). A tap returns as
        an ``InboundMessageWebhook`` whose selection is the row ``id``, like a
        WhatsApp ``list_reply``. Section titles, row descriptions and
        ``button_text`` are presentation Instagram cannot show; a text header
        and the footer fold into the text. Image headers are rejected.
        """
        direct = self._direct(target, "send_list_message")
        if header is not None and header.text is None:
            raise UnsupportedOperationError(
                "Instagram list messages accept only a text header"
            )
        rows = [row for section in sections for row in section.rows]
        if not 1 <= len(rows) <= QUICK_REPLY_MAX:
            raise ValueError(
                f"Instagram list (quick replies) allows 1–{QUICK_REPLY_MAX} rows; "
                f"got {len(rows)}"
            )
        options = [
            {
                "content_type": "text",
                "title": _check_len(
                    row.title, QUICK_REPLY_TITLE_MAX, "Instagram list row title"
                ),
                "payload": _check_len(row.id, PAYLOAD_MAX, "Instagram list row id"),
            }
            for row in rows
        ]
        _ = button_text  # WhatsApp list-opener label; no Instagram equivalent
        return await self._send(
            direct,
            {
                "text": _check_text(
                    _fold(header.text if header else None, body, footer)
                ),
                "quick_replies": options,
            },
            operation="Instagram list (quick replies) send",
            reply_to_message_id=reply_to_message_id,
        )

    async def send_cta_message(
        self,
        button_text: str,
        button_url: str,
        target: DirectMessage,
        body: str,
        header: str | None = None,
        footer: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        """One URL button → Instagram ``web_url`` button; header/footer fold into text."""
        direct = self._direct(target, "send_cta_message")
        button = _url_button(UrlButton(title=button_text, url=button_url))
        return await self._button_template(
            direct,
            _fold(header, body, footer),
            [button],
            "Instagram CTA send",
            reply_to_message_id,
        )

    async def send_carousel(
        self,
        cards: Sequence[MessageCard],
        target: DirectMessage,
        body: str,
    ) -> MessageResult:
        """``body`` as a text message, then the cards as a generic template.

        Instagram carousels carry no intro text, so ``body`` is sent first; if
        it is not accepted, the carousel is not sent and that result returns.
        """
        direct = self._direct(target, "send_carousel")
        _check_carousel(cards)
        elements = [_card(c) for c in cards]
        intro = await self.send_text(body, direct)
        if not intro.success:
            return intro
        template = {"template_type": "generic", "elements": elements}
        return await self._send(
            direct,
            {"attachment": {"type": "template", "payload": template}},
            operation="Instagram carousel send",
        )

    # ── acknowledge (seen + typing are private sender actions) ──────────

    async def _sender_action(self, target: DirectMessage, action: str) -> GraphResponse:
        recipient = target.resolve(self._inbox_ref)
        return await self._graph.request(
            "POST",
            f"{self.inbox_id}/messages",
            json={"recipient": {"id": recipient}, "sender_action": action},
            operation=f"Instagram {action}",
        )

    async def mark_as_read(
        self,
        message_id: str,
        target: DirectMessage,
        *,
        typing: bool = False,
    ) -> MessageResult:
        """``mark_seen`` on the thread, then ``typing_on`` when ``typing``.

        Instagram has no per-message read, so ``target`` names the thread and
        ``message_id`` is echoed in the result. Typing is attempted only after
        the seen action was accepted.
        """
        direct = self._direct(target, "mark_as_read")
        seen = await self._sender_action(direct, "mark_seen")
        typed = (
            await self._sender_action(direct, "typing_on")
            if typing and seen.outcome is OperationOutcome.ACCEPTED
            else None
        )
        failed = next(
            (
                r
                for r in (seen, typed)
                if r is not None and r.outcome is not OperationOutcome.ACCEPTED
            ),
            None,
        )
        error_code = None
        if failed is not None:
            error_code = failed.error_code or (
                "INDETERMINATE"
                if failed.outcome is OperationOutcome.INDETERMINATE
                else None
            )
        return MessageResult(
            success=failed is None,
            platform=self.platform,
            inbox_id=self.inbox_id,
            message_id=message_id,
            recipient=direct.recipient_id,
            error=failed.error if failed else None,
            error_code=error_code,
            platform_response={
                "mark_seen": seen.outcome.value,
                "typing_on": typed.outcome.value if typed else None,
            },
        )
