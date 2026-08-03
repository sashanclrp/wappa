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
    def validate_message(self, message_payload: dict[str, Any]) -> bool: ...

    @abstractmethod
    def get_message_limits(self) -> dict[str, Any]: ...


class WhatsAppMessageFactory(MessageFactory):
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
