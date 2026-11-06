"""Media sends: image, video, audio and voice note, document, sticker."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from wappa.domain.interactive import check_caption
from wappa.domain.media_renditions import MediaRenditions, pick_rendition
from wappa.domain.messaging_targets import DirectMessage
from wappa.domain.results import MessageResult
from wappa.messaging.whatsapp.media.rules import (
    WHATSAPP_AUDIO_SUFFIXES,
    WHATSAPP_STICKER_SUFFIXES,
    WHATSAPP_VOICE_SUFFIXES,
    check_media_source,
)
from wappa.messaging.whatsapp.messenger.media_wire import _MediaWireMixin
from wappa.messaging.whatsapp.models.media_models import MediaType


class _MediaMixin(_MediaWireMixin):
    async def send_image(
        self,
        image_source: str | Path,
        target: DirectMessage,
        caption: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        check_caption(caption)
        check_media_source(image_source, "image")
        media_cache: dict[str, Any] = {}  # upload once across fallback attempts
        return await self._deliver(
            target,
            lambda recipient: self._send_media(
                image_source,
                MediaType.IMAGE,
                recipient,
                media_cache=media_cache,
                caption=caption,
                reply_to_message_id=reply_to_message_id,
            ),
        )

    async def send_video(
        self,
        video_source: str | Path,
        target: DirectMessage,
        caption: str | None = None,
        reply_to_message_id: str | None = None,
        transcript: str | None = None,
    ) -> MessageResult:
        check_caption(caption)
        check_media_source(video_source, "video")
        media_cache: dict[str, Any] = {}  # upload once across fallback attempts
        return await self._deliver(
            target,
            lambda recipient: self._send_media(
                video_source,
                MediaType.VIDEO,
                recipient,
                media_cache=media_cache,
                caption=caption,
                reply_to_message_id=reply_to_message_id,
                transcript=transcript,
            ),
        )

    async def send_audio(
        self,
        audio_source: MediaRenditions,
        target: DirectMessage,
        reply_to_message_id: str | None = None,
        transcript: str | None = None,
        is_voice: bool = False,
    ) -> MessageResult:
        # A voice note (waveform) needs OGG/Opus mono; audio has no caption.
        audio_source = pick_rendition(
            audio_source,
            WHATSAPP_VOICE_SUFFIXES if is_voice else WHATSAPP_AUDIO_SUFFIXES,
            what="WhatsApp voice note" if is_voice else "WhatsApp audio",
        )
        check_media_source(audio_source, "voice" if is_voice else "audio")
        if is_voice:
            await self._check_media_id_mime(
                audio_source, "audio/ogg", what="voice note", fix="OGG/Opus"
            )
        media_cache: dict[str, Any] = {}  # upload once across fallback attempts
        return await self._deliver(
            target,
            lambda recipient: self._send_media(
                audio_source,
                MediaType.AUDIO,
                recipient,
                media_cache=media_cache,
                reply_to_message_id=reply_to_message_id,
                transcript=transcript,
                is_voice=is_voice,
            ),
        )

    async def _check_media_id_mime(
        self, source: str | Path, expected: str, *, what: str, fix: str
    ) -> None:
        """Refuse a send by Media ID whose stored file is not ``expected``.

        A Media ID has no suffix, so ``pick_rendition`` passes it through. Live
        (2026-11-06): MP3, M4A and AAC sent as voice notes arrived with no
        waveform, and a PNG sticker failed with 131053 after acceptance. Ask
        Meta for the ID's MIME type and refuse a mismatch before sending. A
        failed lookup passes the send through, leaving the verdict to Meta.
        """
        if isinstance(source, Path) or source.startswith(("http://", "https://")):
            return
        info = await self.media_transport.get_media_info(source)
        mime = (info.mime_type or "").split(";", 1)[0].strip().lower()
        if info.success and mime and mime != expected:
            raise ValueError(
                f"WhatsApp {what} accepts {fix} ({expected}); Media ID "
                f"{source} is {mime}"
            )

    async def send_document(
        self,
        document_source: str | Path,
        target: DirectMessage,
        filename: str | None = None,
        caption: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        check_caption(caption)
        check_media_source(document_source, "document")
        media_cache: dict[str, Any] = {}  # upload once across fallback attempts
        return await self._deliver(
            target,
            lambda recipient: self._send_media(
                document_source,
                MediaType.DOCUMENT,
                recipient,
                media_cache=media_cache,
                caption=caption,
                filename=filename,
                reply_to_message_id=reply_to_message_id,
            ),
        )

    async def send_sticker(
        self,
        sticker_source: MediaRenditions,
        target: DirectMessage,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        # WhatsApp stickers must be WebP. Meta accepts a PNG link with 200 and
        # only fails later (status 131053), so pick or reject up front.
        sticker_source = pick_rendition(
            sticker_source, WHATSAPP_STICKER_SUFFIXES, what="WhatsApp sticker"
        )
        check_media_source(sticker_source, "sticker")
        await self._check_media_id_mime(
            sticker_source, "image/webp", what="sticker", fix="WebP"
        )
        media_cache: dict[str, Any] = {}  # upload once across fallback attempts
        return await self._deliver(
            target,
            lambda recipient: self._send_media(
                sticker_source,
                MediaType.STICKER,
                recipient,
                media_cache=media_cache,
                reply_to_message_id=reply_to_message_id,
            ),
        )
