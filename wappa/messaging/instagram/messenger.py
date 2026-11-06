"""Inbox-bound Instagram Messenger (Unified Login, Graph v26.0).

Native wire formats (``POST /{ig-account-id}/messages``):

- text: ``{"recipient": {"id"}, "message": {"text"}}`` (≤ 1000 UTF-8 bytes)
- private reply: ``{"recipient": {"comment_id"}, "message": {"text"}}``
- media: ``message.attachment = {"type": image|audio|video|file,
  "payload": {"url"}}`` or ``{"attachment_id"}`` after upload
Contract mappings (ADR-0025: one Messenger method per action):

- ``send_text`` → text over 1000 UTF-8 bytes is split into several messages,
  on a word boundary when possible
- ``send_button_message`` → ``template_type = button`` with ``postback``
  buttons (text ≤ 640, 1–3); a media header is sent first as its own
  attachment
- ``send_list_message`` → ``message.quick_replies[]`` on the (last) text;
  section titles and row descriptions fold into the text as a numbered menu
- ``send_cta_message`` → ``template_type = button`` with one ``web_url``; a
  media header is sent first as its own attachment
- ``send_carousel`` → intro text, then ``template_type = generic`` (2–10); a
  video card shows its poster image and opens the video on tap
- ``mark_as_read`` → ``sender_action`` ``mark_seen`` then ``typing_on``
- ``resolve_platform_user_profile`` → ``GET /{igsid}?fields=name,username,
  profile_pic`` merged over the webhook evidence; a failure returns the
  evidence with the failure outcome
- media by http(s) URL, by ``IMediaLibrary.upload`` attachment_id, or a
  ``Path`` (uploaded first, under ``filename`` for a document); a document,
  audio or video URL whose format Instagram does not take is sent as a text
  with the file name and the link
- ``send_location`` / ``send_contact`` → text (maps link / one block per card);
  ``send_sticker`` → image
- ``IUserDataRequests`` (location / phone-number requests) → not provided
  (``self.whatsapp`` is ``None`` here; a text prompt would not return the data)
- reply: top-level ``reply_to: {"mid"}``

Known local constraints are rejected before I/O; provider refusals and
unknown outcomes are returned, never retried.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import unquote, urlsplit

import httpx
from pydantic import SecretStr

from wappa.domain.contacts import ContactCard, contact_cards
from wappa.domain.inbox.identity import InboxRef
from wappa.domain.interactive import (
    CardButton,
    InteractiveHeader,
    ListSection,
    MessageCard,
    ReplyButton,
    UrlButton,
    check_button_message,
    check_caption,
    check_carousel,
    check_cta_message,
    check_list_message,
    check_text,
)
from wappa.domain.interfaces.conversation_capabilities import (
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
from wappa.domain.user_profile import PlatformUserProfile
from wappa.messaging.meta.graph import GraphResponse
from wappa.schemas.core.types import PlatformType
from wappa.webhooks.core.webhook_interfaces.base_components import UserBase

from .client import InstagramClient
from .content import InstagramCommentControls, InstagramContentReader, read_failure
from .history import InstagramHistoryReader
from .media import (
    MEDIA_ADAPTATION_DRAFT,
    MEDIA_RULES,
    InstagramAttachmentReader,
    url_format_accepted,
    validate_media_url,
)
from .media_library import InstagramMediaLibrary

TEXT_MAX_BYTES = 1000
BUTTON_TEXT_MAX = 640
BUTTONS_MAX = 3
PROFILE_FIELDS = "name,username,profile_pic"
# Interactive titles, IDs, card texts and counts need no check here: the
# neutral values already enforce the minimum across Platforms
# (wappa.domain.interactive).


def _check_text(text: str, *, what: str = "Instagram text") -> str:
    if not text or not text.strip():
        raise ValueError(f"{what} must not be empty")
    size = len(text.encode("utf-8"))
    if size > TEXT_MAX_BYTES:
        raise ValueError(f"{what} is {size} UTF-8 bytes; limit is {TEXT_MAX_BYTES}")
    return text


PARTS_KEY = "wappa_parts"


class _Parts:
    """Fold the messages of one emulated send into one ``MessageResult``.

    An emulation (split text, media header then buttons, caption follow-up,
    carousel intro) is one Host call, so it returns one result: success only
    when every part was accepted, the final part's ``message_id``, and every
    part's ID under ``platform_response["wappa_parts"]``. On a refusal the
    failed result says how many parts were already delivered, so a Host never
    resends the whole message blindly. Nested emulations are flattened.
    """

    def __init__(self) -> None:
        self.ids: list[str] = []

    def add(self, result: MessageResult) -> bool:
        if not result.success:
            return False
        nested = (result.platform_response or {}).get(PARTS_KEY)
        if nested:
            self.ids.extend(nested["message_ids"])
        elif result.message_id:
            self.ids.append(result.message_id)
        return True

    def result(
        self, last: MessageResult, *, primary: MessageResult | None = None
    ) -> MessageResult:
        """``last`` is the final part's result, or the first refused one.

        On success the returned ``message_id`` is ``primary``'s when given
        (the media of a media-plus-caption send), else ``last``'s (the
        interactive message a User taps).
        """
        if last.success and primary is not None:
            last = last.model_copy(update={"message_id": primary.message_id})
        delivered = len(self.ids)
        response = dict(last.platform_response or {})
        response[PARTS_KEY] = {"message_ids": list(self.ids), "delivered": delivered}
        update: dict[str, Any] = {"platform_response": response}
        if not last.success and delivered:
            update["error"] = (
                f"{last.error or 'part refused'} "
                f"({delivered} earlier part(s) already delivered)"
            )
        return last.model_copy(update=update)


def _split_text(text: str, limit: int = TEXT_MAX_BYTES) -> list[str]:
    """Split ``text`` into chunks of at most ``limit`` UTF-8 bytes.

    Cuts on the last newline or space that fits, and mid-word only when a
    single word is longer than the limit.
    """
    if len(text.encode("utf-8")) <= limit:
        return [text]
    chunks: list[str] = []
    rest = text.strip()
    while len(rest.encode("utf-8")) > limit:
        cut = len(rest.encode("utf-8")[:limit].decode("utf-8", "ignore"))
        space = max(rest.rfind("\n", 0, cut + 1), rest.rfind(" ", 0, cut + 1))
        if space > 0:
            cut = space
        chunks.append(rest[:cut].rstrip())
        rest = rest[cut:].lstrip()
    if rest:
        chunks.append(rest)
    return chunks


def _check_len(value: str, limit: int, what: str) -> str:
    if len(value) > limit:
        raise ValueError(f"{what} is {len(value)} characters; limit is {limit}")
    return value


def _fold(*parts: str | None) -> str:
    """Join header/body/footer for Platforms without separate slots."""
    return "\n\n".join(p.strip() for p in parts if p and p.strip())


def _reply(button: ReplyButton) -> dict[str, Any]:
    return {"type": "postback", "title": button.title, "payload": button.id}


def _url_button(button: UrlButton) -> dict[str, Any]:
    return {"type": "web_url", "title": button.title, "url": str(button.url)}


def _card_button(button: CardButton) -> dict[str, Any]:
    return _url_button(button) if isinstance(button, UrlButton) else _reply(button)


def _button_texts(
    header: str | None, body: str, footer: str | None
) -> tuple[str | None, str]:
    """Plan (lead text, button template text) so the template fits 640 chars.

    Header, body and footer fold into the template text when they fit;
    otherwise the header, then the body too, go first as a plain text message.
    The neutral limits (body ≤ 640, footer ≤ 60) make the last case fit.
    """
    full = _fold(header, body, footer)
    if len(full) <= BUTTON_TEXT_MAX:
        return None, full
    tail = _fold(body, footer)
    if len(tail) <= BUTTON_TEXT_MAX:
        return header, tail
    return _fold(header, body), footer or ""


def _card(card: MessageCard) -> dict[str, Any]:
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
            "pass poster_url, or enable media adaptation"
        )
    else:
        element["image_url"] = str(card.header.poster_url)
        default_url = default_url or card.header.url
    if default_url:
        element["default_action"] = {"type": "web_url", "url": str(default_url)}
    element["buttons"] = [_card_button(b) for b in card.buttons]
    return element


def _list_menu(sections: Sequence[ListSection]) -> str | None:
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


# A media family whose URL may point at a format Instagram does not take; the
# file is then shared as a link (images and stickers keep their own rules).
_LINK_ICONS = {"document": "📄", "audio": "🎵", "video": "🎬"}


def _media_link(family: str, url: str, filename: str | None) -> str:
    """The text that shares a file Instagram cannot attach: its name and link."""
    name = filename or unquote(PurePosixPath(urlsplit(url).path).name) or url
    return f"{_LINK_ICONS[family]} {name}\n{url}"


def _contact_text(card: ContactCard) -> str:
    lines = [f"👤 {card.name.formatted_name}"]
    if card.org and (card.org.company or card.org.title):
        lines.append(" · ".join(p for p in (card.org.title, card.org.company) if p))
    lines += [f"📞 {p.phone}" for p in card.phones or []]
    lines += [f"✉️ {e.email}" for e in card.emails or []]
    lines += [f"🔗 {u.url}" for u in card.urls or []]
    return "\n".join(lines)


class InstagramMessengerAdapter(IMessenger):
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
            "resolve_platform_user_profile",
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
            raise ValueError("InstagramMessengerAdapter requires an Instagram Inbox")
        self._inbox_ref = inbox_ref
        # Instagram echoes Wappa's own sends; recording them lets the Inbound
        # Runtime drop those echoes (ADR-0023).
        self._sent_registry = sent_registry
        self._graph = InstagramClient(
            inbox_ref=inbox_ref,
            access_token=access_token,
            session_provider=session_provider,
            graph_api_version=graph_api_version,
            graph_base_url=graph_base_url,
        )
        self._media = InstagramMediaLibrary(
            self._graph,
            InstagramAttachmentReader(
                media_download_client_provider or session_provider
            ),
        )
        # Instagram-only actions (ADR-0025 exceptions), capability-gated.
        self._capabilities = {
            ICommentControls: InstagramCommentControls(self._graph),
            IConversationContentReader: InstagramContentReader(self._graph),
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
            retry_after=response.retry_after,
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
            "POST", self._graph.messages_path, json=body, operation=operation
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
        """Text over 1000 UTF-8 bytes goes out as several messages.

        The shared ``TEXT_MAX`` (WhatsApp's 4096 characters) is checked first.
        ``disable_preview`` is ignored: Instagram has no preview switch. A
        ``PrivateReply`` is one message per comment, so it cannot be split and
        an over-limit private reply raises ``ValueError``. For a split text
        the reply context goes on the first message, and the last result
        returns unless one is refused; that refusal returns and later chunks
        are not sent (nothing retries).
        """
        _ = disable_preview
        if not isinstance(target, DirectMessage | PrivateReply):
            raise TypeError("send_text requires a DirectMessage or PrivateReply")
        # Validate target scope before content so wrong-Inbox fails first.
        target.resolve(self._inbox_ref)
        check_text(text)
        if isinstance(target, PrivateReply):
            return await self._send(
                target,
                {"text": _check_text(text)},
                operation="Instagram private reply",
                reply_to_message_id=reply_to_message_id,
            )
        return await self._send_texts(text, target, reply_to_message_id)

    async def _send_texts(
        self,
        text: str,
        direct: DirectMessage,
        reply_to_message_id: str | None,
        last: dict[str, Any] | None = None,
        operation: str = "Instagram text send",
    ) -> MessageResult:
        """Send ``text`` in ≤ 1000-byte chunks; ``last`` extends the final one.

        ``last`` carries extra message fields (quick replies) on the final
        chunk. Several chunks return one result listing every part (``_Parts``);
        the first refusal stops the send.
        """
        if not text or not text.strip():
            raise ValueError("Instagram text must not be empty")
        chunks = _split_text(text)
        if len(chunks) == 1 and not last:
            return await self._send(
                direct,
                {"text": chunks[0]},
                operation=operation,
                reply_to_message_id=reply_to_message_id,
            )
        parts = _Parts()
        result: MessageResult | None = None
        for index, chunk in enumerate(chunks):
            final = index == len(chunks) - 1
            message: dict[str, Any] = {"text": chunk}
            if final and last:
                message.update(last)
            result = await self._send(
                direct,
                message,
                operation=operation if final else "Instagram text send",
                reply_to_message_id=reply_to_message_id if index == 0 else None,
            )
            if not parts.add(result):
                break
        assert result is not None
        return parts.result(result)

    # ── media ───────────────────────────────────────────────────────────

    async def _send_media(
        self,
        family: str,
        source: str | Path,
        target: DirectMessage,
        reply_to_message_id: str | None,
        *,
        filename: str | None = None,
    ) -> MessageResult:
        """One attachment, or a text with the file's name and link.

        A document, audio or video URL whose extension Instagram does not take
        (WhatsApp's ``.docx``, ``.mp3``, ``.3gp`` …) is sent as a text naming
        the file (``filename``, else the URL's last path segment) with its
        link. A ``Path`` uploads under ``filename``; one in a format Instagram
        does not take raises ``ValueError`` before any call.
        """
        direct = require_direct_message(target, f"Instagram send_{family}")
        direct.resolve(self._inbox_ref)
        rule_type = {"document": "file"}.get(family, family)
        payload: dict[str, Any]
        if isinstance(source, Path):
            uploaded = await self._media.upload(
                source, MediaFamily(family), filename=filename
            )
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
            url = validate_media_url(source)
            if family in _LINK_ICONS and not url_format_accepted(url, family):
                return await self._send_texts(
                    _media_link(family, url, filename),
                    direct,
                    reply_to_message_id,
                    operation=f"Instagram {family} link send",
                )
            payload = {"url": url}
        elif isinstance(source, str) and source.strip():
            # A reusable attachment_id from IMediaLibrary.upload.
            payload = {"attachment_id": source}
        else:
            raise TypeError(
                "media source must be an http(s) URL, an uploaded media_id or a Path"
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
        *,
        filename: str | None = None,
    ) -> MessageResult:
        """Instagram attachments carry no caption: send it as a follow-up text.

        One result: the media's ``message_id``, every part under
        ``platform_response["wappa_parts"]``; a refused caption returns a failed
        result saying the media was already delivered (nothing retries).
        """
        check_caption(caption)
        result = await self._send_media(
            family, source, target, reply_to_message_id, filename=filename
        )
        if not (caption and caption.strip()):
            return result
        parts = _Parts()
        if not parts.add(result):
            return result
        follow_up = await self.send_text(caption, target)
        parts.add(follow_up)
        return parts.result(follow_up, primary=result)

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
        serves a WhatsApp voice note and Instagram from one call. When no
        rendition fits, a URL rendition (WhatsApp's ``.mp3``, ``.amr``, ``.ogg``)
        is shared as a text with its name and link; local files only raise
        ``ValueError``.
        """
        _ = transcript  # Host metadata, never shown to the User (as on WhatsApp)
        _ = is_voice
        try:
            source = pick_rendition(
                audio_source, MEDIA_RULES["audio"].extensions, what="Instagram audio"
            )
        except ValueError as exc:
            sources = (
                [audio_source]
                if isinstance(audio_source, str | Path)
                else list(audio_source)
            )
            url = next((s for s in sources if isinstance(s, str) and "://" in s), None)
            if url is None:
                raise ValueError(
                    f"{exc} (format conversion is the Media Adaptation backlog "
                    f"draft, {MEDIA_ADAPTATION_DRAFT})"
                ) from exc
            source = url
        return await self._send_media("audio", source, target, reply_to_message_id)

    async def send_document(
        self,
        document_source: str | Path,
        target: DirectMessage,
        filename: str | None = None,
        caption: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        """A ``Path`` uploads under ``filename``; a URL Instagram cannot attach
        (anything but PDF) is shared as a text with ``filename`` and the link.

        An accepted URL or an attachment_id has no name slot on Instagram, so
        ``filename`` shows only on WhatsApp there.
        """
        return await self._media_with_caption(
            "document",
            document_source,
            target,
            caption,
            reply_to_message_id,
            filename=filename,
        )

    # ── specialized sends, adapted (ADR-0025) ──────────────────────────

    async def send_sticker(
        self,
        sticker_source: MediaRenditions,
        target: DirectMessage,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        """Instagram has no custom stickers: the sticker is sent as an image.

        A static WebP sticker shows as an image; an animated one would show
        only its first frame. Pass renditions (``[sticker.webp, sticker.gif]``)
        and Instagram takes a png/jpeg/gif one when given (a GIF animates),
        else the WebP; WhatsApp takes the WebP.
        """
        what = "Instagram sticker (sent as an image)"
        images = MEDIA_RULES["image"].extensions
        try:
            source = pick_rendition(sticker_source, images - {".webp"}, what=what)
        except ValueError:
            source = pick_rendition(sticker_source, images, what=what)
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
        contacts: ContactCard | Sequence[ContactCard],
        target: DirectMessage,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        """Instagram has no contact message: each card is sent as a text block.

        ``contacts`` are the same typed ``ContactCard`` values WhatsApp sends
        natively. The blocks are separated by a blank line, and text over 1000
        UTF-8 bytes is split into several messages as ``send_text`` does.
        """
        blocks = [_contact_text(card) for card in contact_cards(contacts)]
        return await self.send_text(
            "\n\n".join(blocks), target, reply_to_message_id=reply_to_message_id
        )

    # ── interactive (WhatsApp-shaped contract, ADR-0025) ────────────────

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
            [_reply(b) for b in buttons],
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
                return parts.result(media)
            reply_to_message_id = None
        lead, text = _button_texts(text_header, body, footer)
        if lead:
            intro = await self._send_texts(lead, direct, reply_to_message_id)
            if not parts.add(intro):
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
            _fold(header, body, _list_menu(sections), footer),
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
            [_url_button(button)],
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
        elements = [_card(c) for c in cards]
        parts = _Parts()
        intro = await self._send_texts(body, direct, reply_to_message_id)
        if not parts.add(intro):
            return parts.result(intro)
        template = {"template_type": "generic", "elements": elements}
        final = await self._send(
            direct,
            {"attachment": {"type": "template", "payload": template}},
            operation="Instagram carousel send",
        )
        parts.add(final)
        return parts.result(final)

    # ── acknowledge (seen + typing are private sender actions) ──────────

    async def _sender_action(self, target: DirectMessage, action: str) -> GraphResponse:
        recipient = target.resolve(self._inbox_ref)
        return await self._graph.request(
            "POST",
            self._graph.messages_path,
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
            retry_after=failed.retry_after if failed else None,
            platform_response={
                "mark_seen": seen.outcome.value,
                "typing_on": typed.outcome.value if typed else None,
            },
        )

    # ── User profile (read-only, Host-called) ───────────────────────────

    async def resolve_platform_user_profile(
        self, user: UserBase
    ) -> PlatformUserProfile:
        """Graph profile lookup by IGSID, merged over the webhook evidence.

        Never raises for Platform failures: a refused or unknown lookup
        returns the evidence with ``not_found`` / ``access_denied`` /
        ``rejected`` / ``unavailable``.
        """
        if not user.platform_user_id:
            raise ValueError(
                "Instagram profiles resolve from Instagram evidence "
                "(UserBase.platform_user_id)"
            )
        evidence = PlatformUserProfile.from_evidence(self.platform, user)
        response = await self._graph.request(
            "GET",
            user.platform_user_id,
            params={"fields": PROFILE_FIELDS},
            operation="Instagram user profile read",
        )
        if not response.ok:
            return evidence.model_copy(
                update={"outcome": read_failure(response).outcome}
            )
        body = response.body

        def text(key: str) -> str | None:
            value = body.get(key)
            return value if isinstance(value, str) and value.strip() else None

        return evidence.model_copy(
            update={
                "profile_name": text("name") or evidence.profile_name,
                "username": text("username") or evidence.username,
                "picture_url": text("profile_pic"),
                "raw": body,
            }
        )
