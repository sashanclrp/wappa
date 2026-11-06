"""WhatsApp Cloud API payload builders for text, read status and media.

Private to the WhatsApp adapter: ``WhatsAppMessenger`` builds its send
payloads here and the WhatsApp limits routes read the limits. Interactive,
Template and specialized payloads are built in ``handlers/``.
"""

from typing import Any

from wappa.schemas.core.recipient import apply_recipient_to_payload


class WhatsAppMessagePayloadBuilder:
    """Text and read-status Cloud API payloads, plus text limits."""

    def create_text_message(
        self,
        text: str,
        recipient: str,
        reply_to_message_id: str | None = None,
        disable_preview: bool = False,
    ) -> dict[str, Any]:
        has_url = "http://" in text or "https://" in text
        payload: dict[str, Any] = {
            "messaging_product": "whatsapp",
            "type": "text",
            "text": {"body": text, "preview_url": has_url and not disable_preview},
        }
        apply_recipient_to_payload(payload, recipient)

        if reply_to_message_id:
            payload["context"] = {"message_id": reply_to_message_id}

        return payload

    def create_read_status_message(
        self, message_id: str, typing: bool = False
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": message_id,
        }
        if typing:
            payload["typing_indicator"] = {"type": "text"}
        return payload

    def validate_message(self, message_payload: dict[str, Any]) -> bool:
        try:
            if message_payload.get("messaging_product") != "whatsapp":
                return False
            if "to" not in message_payload and "recipient" not in message_payload:
                return False

            if message_payload.get("type") == "text":
                text = message_payload.get("text") or {}
                body = text.get("body")
                if not body or len(body) > 4096:
                    return False

            return not (
                message_payload.get("status") == "read"
                and "message_id" not in message_payload
            )
        except (KeyError, TypeError):
            return False

    def get_message_limits(self) -> dict[str, Any]:
        return {
            "max_text_length": 4096,
            "max_preview_url_text_length": 4096,
            "max_recipient_phone_length": 20,
        }


class WhatsAppMediaPayloadBuilder:
    """Media message Cloud API payloads, plus media limits."""

    _VALID_MEDIA_TYPES = {"image", "video", "audio", "document", "sticker"}
    _NO_CAPTION_TYPES = {"audio", "sticker"}

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

    def validate_media_message(self, message_payload: dict[str, Any]) -> bool:
        try:
            if message_payload.get("messaging_product") != "whatsapp":
                return False
            if "to" not in message_payload and "recipient" not in message_payload:
                return False

            message_type = message_payload.get("type")
            if message_type not in self._VALID_MEDIA_TYPES:
                return False
            if message_type not in message_payload:
                return False

            media_obj = message_payload[message_type]
            if "id" not in media_obj and "link" not in media_obj:
                return False

            caption = media_obj.get("caption")
            if caption is not None:
                if len(caption) > 1024:
                    return False
                if message_type in self._NO_CAPTION_TYPES:
                    return False

            return True
        except (KeyError, TypeError):
            return False

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
