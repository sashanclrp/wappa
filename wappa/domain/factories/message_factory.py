# Platform-specific message payload factory.

from abc import ABC, abstractmethod
from typing import Any

from wappa.schemas.core.recipient import apply_recipient_to_payload
from wappa.schemas.core.types import PlatformType


class MessageFactory(ABC):
    @property
    @abstractmethod
    def platform(self) -> PlatformType: ...

    @abstractmethod
    def create_text_message(
        self,
        text: str,
        recipient: str,
        reply_to_message_id: str | None = None,
        disable_preview: bool = False,
    ) -> dict[str, Any]: ...

    @abstractmethod
    def create_read_status_message(
        self, message_id: str, typing: bool = False
    ) -> dict[str, Any]: ...

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
    def validate_message(self, message_payload: dict[str, Any]) -> bool: ...

    @abstractmethod
    def get_message_limits(self) -> dict[str, Any]: ...


class WhatsAppMessageFactory(MessageFactory):
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

    @property
    def platform(self) -> PlatformType:
        return PlatformType.WHATSAPP

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

            if (
                message_payload.get("status") == "read"
                and "message_id" not in message_payload
            ):
                return False

            return True
        except (KeyError, TypeError):
            return False

    def get_message_limits(self) -> dict[str, Any]:
        return {
            "max_text_length": 4096,
            "max_preview_url_text_length": 4096,
            "max_recipient_phone_length": 20,
        }
