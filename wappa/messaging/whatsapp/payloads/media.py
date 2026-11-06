"""Cloud API payloads for media messages, plus the media limits.

Pure builders (no I/O): ``WhatsAppMessengerAdapter`` builds its media sends
here and the WhatsApp limits route reads the limits.
"""

from __future__ import annotations

from typing import Any

from wappa.schemas.core.recipient import apply_recipient_to_payload


class WhatsAppMediaPayloadBuilder:
    """Media message Cloud API payloads, plus media limits."""

    def _build_media_payload(
        self,
        media_type: str,
        media_reference: str,
        recipient: str,
        reply_to_message_id: str | None = None,
        is_url: bool = False,
        caption: str | None = None,
        filename: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "type": media_type,
        }
        apply_recipient_to_payload(payload, recipient)

        media_obj: dict[str, Any] = (
            {"link": media_reference} if is_url else {"id": media_reference}
        )
        if caption:
            media_obj["caption"] = caption
        if filename:
            media_obj["filename"] = filename
        payload[media_type] = media_obj

        if reply_to_message_id:
            payload["context"] = {"message_id": reply_to_message_id}

        return payload

    def create_image_message(
        self,
        media_reference: str,
        recipient: str,
        caption: str | None = None,
        reply_to_message_id: str | None = None,
        is_url: bool = False,
    ) -> dict[str, Any]:
        return self._build_media_payload(
            "image",
            media_reference,
            recipient,
            reply_to_message_id,
            is_url,
            caption=caption,
        )

    def create_video_message(
        self,
        media_reference: str,
        recipient: str,
        caption: str | None = None,
        reply_to_message_id: str | None = None,
        is_url: bool = False,
    ) -> dict[str, Any]:
        return self._build_media_payload(
            "video",
            media_reference,
            recipient,
            reply_to_message_id,
            is_url,
            caption=caption,
        )

    def create_audio_message(
        self,
        media_reference: str,
        recipient: str,
        reply_to_message_id: str | None = None,
        is_url: bool = False,
    ) -> dict[str, Any]:
        return self._build_media_payload(
            "audio", media_reference, recipient, reply_to_message_id, is_url
        )

    def create_document_message(
        self,
        media_reference: str,
        recipient: str,
        filename: str | None = None,
        reply_to_message_id: str | None = None,
        is_url: bool = False,
        caption: str | None = None,
    ) -> dict[str, Any]:
        return self._build_media_payload(
            "document",
            media_reference,
            recipient,
            reply_to_message_id,
            is_url,
            caption=caption,
            filename=filename,
        )

    def create_sticker_message(
        self,
        media_reference: str,
        recipient: str,
        reply_to_message_id: str | None = None,
        is_url: bool = False,
    ) -> dict[str, Any]:
        return self._build_media_payload(
            "sticker", media_reference, recipient, reply_to_message_id, is_url
        )

    def get_media_limits(self) -> dict[str, Any]:
        return {
            "max_caption_length": 1024,
            "max_filename_length": 255,
            "supported_media_types": {
                "image": ["image/jpeg", "image/png"],
                "video": ["video/mp4", "video/3gpp"],
                "audio": [
                    "audio/aac",
                    "audio/amr",
                    "audio/mpeg",
                    "audio/mp4",
                    "audio/ogg",
                ],
                "document": [
                    "text/plain",
                    "application/pdf",
                    "application/vnd.ms-powerpoint",
                    "application/msword",
                    "application/vnd.ms-excel",
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ],
                "sticker": ["image/webp"],
            },
            "max_file_sizes": {
                "image": 5 * 1024 * 1024,
                "video": 16 * 1024 * 1024,
                "audio": 16 * 1024 * 1024,
                "document": 100 * 1024 * 1024,
                "sticker": 500 * 1024,
            },
            "caption_support": {
                "image": True,
                "video": True,
                "audio": False,
                "document": True,
                "sticker": False,
            },
            "filename_support": {
                "document": True,
                "image": False,
                "video": False,
                "audio": False,
                "sticker": False,
            },
        }
