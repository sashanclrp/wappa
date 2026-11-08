"""Media sends: image, video, audio, document and sticker, with caption follow-up."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from wappa.domain.interactive import check_caption
from wappa.domain.interfaces.media_library import MediaFamily
from wappa.domain.media_renditions import MediaRenditions, pick_rendition
from wappa.domain.message_parts import with_message_parts
from wappa.domain.messaging_targets import DirectMessage, require_direct_message
from wappa.domain.results import MessageResult

from ..media.rules import (
    CONVERT_HINT,
    MEDIA_RULES,
    check_media_url,
    url_format_accepted,
    validate_media_url,
)
from ..payloads.specialized import document_link
from ._base import _InstagramBase
from .delivery import _part, _Parts


class _MediaMixin(_InstagramBase):
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

        A document URL whose extension Instagram does not take (WhatsApp's
        ``.docx``, ``.xlsx`` …) is sent as a text naming the file
        (``filename``, else the URL's last path segment) with its link. An
        audio or video URL Instagram cannot play (``.mp3``, ``.mov``, ``.3gp``
        …) raises ``ValueError`` before any call, as on WhatsApp. A ``Path``
        uploads under ``filename``; one in a format Instagram does not take
        raises ``ValueError`` before any call.
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
                failure = MessageResult(
                    success=False,
                    platform=self.platform,
                    inbox_id=self.inbox_id,
                    recipient=direct.recipient_id,
                    recipient_platform_id=direct.recipient_id,
                    error=uploaded.error,
                    error_code=uploaded.error_code or "INDETERMINATE",
                    error_evidence=uploaded.error_evidence,
                    retry_after=uploaded.retry_after,
                )
                return with_message_parts(
                    failure, [_part({"attachment": {"type": rule_type}})]
                )
            payload = {"attachment_id": uploaded.media_id}
        elif isinstance(source, str) and "://" in source:
            url = validate_media_url(source)
            if family in ("audio", "video"):
                check_media_url(url, family)
            elif family == "document" and not url_format_accepted(url, family):
                return await self._send_texts(
                    document_link(url, filename),
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
            parts.skip_text(caption, role="caption")
            return with_message_parts(result, parts.parts)
        follow_up = await self.send_text(caption, target)
        parts.add(follow_up, role="caption")
        return parts.result(follow_up, primary=result)

    async def send_image(
        self,
        image_source: str | Path,
        target: DirectMessage,
        caption: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        """``reply_to_message_id`` is temporarily ignored on Instagram; result evidence records the dropped quote."""
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
        """``reply_to_message_id`` is temporarily ignored on Instagram; result evidence records the dropped quote."""
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
        rendition fits (WhatsApp's ``.mp3``, ``.amr``, ``.ogg``), ``ValueError``
        is raised before any call, as on WhatsApp.

        ``reply_to_message_id`` is temporarily ignored on Instagram; result evidence records the dropped quote.
        """
        _ = transcript  # Host metadata, never shown to the User (as on WhatsApp)
        _ = is_voice
        try:
            source = pick_rendition(
                audio_source, MEDIA_RULES["audio"].extensions, what="Instagram audio"
            )
        except ValueError as exc:
            raise ValueError(
                f"{exc}; {CONVERT_HINT} (M4A AAC plays on both Platforms)"
            ) from exc
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

        ``reply_to_message_id`` is temporarily ignored on Instagram; result evidence records the dropped quote.
        """
        return await self._media_with_caption(
            "document",
            document_source,
            target,
            caption,
            reply_to_message_id,
            filename=filename,
        )

    async def send_sticker(
        self,
        sticker_source: MediaRenditions,
        target: DirectMessage,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        """Instagram has no custom stickers: the sticker is sent as an image.

        A static WebP sticker shows as an image when sent by URL (the upload
        endpoint fails on WebP); an animated one shows only its first frame.
        Pass renditions (``[sticker.webp, sticker.gif]``) and Instagram takes a
        png/jpeg/gif one when given (a GIF animates), else the WebP URL;
        WhatsApp takes the WebP.

        ``reply_to_message_id`` is temporarily ignored on Instagram; result evidence records the dropped quote.
        """
        what = "Instagram sticker (sent as an image)"
        images = MEDIA_RULES["image"].extensions
        try:
            source = pick_rendition(sticker_source, images - {".webp"}, what=what)
        except ValueError:
            source = pick_rendition(sticker_source, images, what=what)
        return await self._send_media("image", source, target, reply_to_message_id)
