# Platform-specific media message payload factory.

from abc import ABC, abstractmethod
from typing import Any

from wappa.schemas.core.recipient import apply_recipient_to_payload
from wappa.schemas.core.types import PlatformType


class MediaFactory(ABC):
    @property
    @abstractmethod
    def platform(self) -> PlatformType: ...

    @abstractmethod
    def create_image_message(
        self,
        media_reference: str,
        recipient: str,
        caption: str | None = None,
        reply_to_message_id: str | None = None,
        is_url: bool = False,
    ) -> dict[str, Any]: ...

    @abstractmethod
    def create_video_message(
        self,
        media_reference: str,
        recipient: str,
        caption: str | None = None,
        reply_to_message_id: str | None = None,
        is_url: bool = False,
    ) -> dict[str, Any]: ...

    @abstractmethod
    def create_audio_message(
        self,
        media_reference: str,
        recipient: str,
        reply_to_message_id: str | None = None,
        is_url: bool = False,
    ) -> dict[str, Any]: ...

    @abstractmethod
    def create_document_message(
        self,
        media_reference: str,
        recipient: str,
        filename: str | None = None,
        reply_to_message_id: str | None = None,
        is_url: bool = False,
    ) -> dict[str, Any]: ...

    @abstractmethod
    def create_sticker_message(
        self,
        media_reference: str,
        recipient: str,
        reply_to_message_id: str | None = None,
        is_url: bool = False,
    ) -> dict[str, Any]: ...

    @abstractmethod
    def validate_media_message(self, message_payload: dict[str, Any]) -> bool: ...

    @abstractmethod
    def get_media_limits(self) -> dict[str, Any]: ...


class WhatsAppMediaFactory(MediaFactory):
    _VALID_MEDIA_TYPES = {"image", "video", "audio", "document", "sticker"}
    _NO_CAPTION_TYPES = {"audio", "sticker"}

    @property
    def platform(self) -> PlatformType:
        return PlatformType.WHATSAPP

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
    ) -> dict[str, Any]:
        return self._build_media_payload(
            "document",
            media_reference,
            recipient,
            reply_to_message_id,
            is_url,
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
