"""Resolve a media source to a Cloud API media object and send it."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from wappa.domain.results import MessageResult
from wappa.messaging.whatsapp.errors import handle_whatsapp_error
from wappa.messaging.whatsapp.messenger.delivery import _DeliveryMixin
from wappa.messaging.whatsapp.models.basic_models import message_result_from_payload
from wappa.messaging.whatsapp.models.media_models import MediaType


class _MediaWireMixin(_DeliveryMixin):
    async def _resolve_media_object(
        self,
        media_source: str | Path,
        media_type: MediaType,
        recipient: str,
    ) -> tuple[dict[str, Any] | None, MessageResult | None]:
        # Returns (media_obj, None) on success or (None, error_result) on failure.
        if isinstance(media_source, str) and (
            media_source.startswith("http://") or media_source.startswith("https://")
        ):
            self.logger.debug(f"Using media URL for {media_type.value}: {media_source}")
            return {"link": media_source}, None

        # Heuristic: short string without slashes is treated as an existing media ID.
        if (
            isinstance(media_source, str)
            and len(media_source) < 100
            and "/" not in media_source
        ):
            self.logger.debug(
                f"Using existing media ID for {media_type.value}: {media_source}"
            )
            return {"id": media_source}, None

        media_path = Path(media_source)
        if not media_path.exists():
            return None, self._error_result(
                f"Media file not found: {media_path}",
                "FILE_NOT_FOUND",
                recipient=recipient,
            )

        self.logger.debug(
            f"Uploading media file for {media_type.value}: {media_path.name}"
        )
        upload_result = await self.media_transport.upload_media(media_path)
        if not upload_result.success:
            return None, self._error_result(
                f"Failed to upload media: {upload_result.error}",
                upload_result.error_code or "MEDIA_UPLOAD_FAILED",
                recipient=recipient,
            )
        if not upload_result.media_id:
            return None, self._error_result(
                "Failed to upload media: missing media ID",
                "MEDIA_ID_MISSING",
                recipient=recipient,
            )

        self.logger.debug(
            f"Using uploaded media ID for {media_type.value}: {upload_result.media_id}"
        )
        return {"id": upload_result.media_id}, None

    async def _send_media(
        self,
        media_source: str | Path,
        media_type: MediaType,
        recipient: str,
        caption: str | None = None,
        filename: str | None = None,
        reply_to_message_id: str | None = None,
        transcript: str | None = None,  # noqa: ARG002 - internal metadata, not sent to WhatsApp
        is_voice: bool = False,
        media_cache: dict[str, Any] | None = None,
    ) -> MessageResult:
        try:
            if media_cache is not None and "media_obj" in media_cache:
                media_obj = media_cache["media_obj"]
            else:
                media_obj, error = await self._resolve_media_object(
                    media_source, media_type, recipient
                )
                if error is not None:
                    return error
                assert media_obj is not None
                if media_cache is not None:
                    media_cache["media_obj"] = media_obj

            # Unpack the resolved media into (reference, is_url) for the factory.
            is_url = "link" in media_obj
            media_reference = media_obj["link"] if is_url else media_obj["id"]

            match media_type:
                case MediaType.IMAGE:
                    payload = self._media_payloads.create_image_message(
                        media_reference=media_reference,
                        recipient=recipient,
                        caption=caption,
                        reply_to_message_id=reply_to_message_id,
                        is_url=is_url,
                    )
                case MediaType.VIDEO:
                    payload = self._media_payloads.create_video_message(
                        media_reference=media_reference,
                        recipient=recipient,
                        caption=caption,
                        reply_to_message_id=reply_to_message_id,
                        is_url=is_url,
                    )
                case MediaType.AUDIO:
                    payload = self._media_payloads.create_audio_message(
                        media_reference=media_reference,
                        recipient=recipient,
                        reply_to_message_id=reply_to_message_id,
                        is_url=is_url,
                    )
                case MediaType.DOCUMENT:
                    payload = self._media_payloads.create_document_message(
                        media_reference=media_reference,
                        recipient=recipient,
                        filename=filename,
                        caption=caption,
                        reply_to_message_id=reply_to_message_id,
                        is_url=is_url,
                    )
                case MediaType.STICKER:
                    payload = self._media_payloads.create_sticker_message(
                        media_reference=media_reference,
                        recipient=recipient,
                        reply_to_message_id=reply_to_message_id,
                        is_url=is_url,
                    )
                case _:
                    return self._error_result(
                        f"Unsupported media type: {media_type}",
                        "INVALID_MEDIA_TYPE",
                        recipient=recipient,
                    )

            # Voice-note flag is WhatsApp-specific and not part of the factory contract.
            if media_type is MediaType.AUDIO and is_voice:
                payload[media_type.value]["voice"] = True

            self.logger.debug(f"Sending {media_type.value} message")
            response = await self.client.post_request(payload)
            result = message_result_from_payload(
                response,
                inbox_id=self._inbox_id,
                fallback_recipient=recipient,
            )
            self.logger.info(
                f"{media_type.value.title()} message sent successfully, id: {result.message_id}"
            )
            return result

        except Exception as e:
            return handle_whatsapp_error(
                error=e,
                operation=f"send {media_type.value}",
                recipient=recipient,
                inbox_id=self._inbox_id,
                logger=self.logger,
            )
