"""Cloud API payloads for text and read status, plus the text limits.

Pure builders (no I/O). ``WhatsAppMessengerAdapter`` builds its text and
read-receipt sends here and the WhatsApp limits route reads the limits.
"""

from __future__ import annotations

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

    def get_message_limits(self) -> dict[str, Any]:
        return {
            "max_text_length": 4096,
            "max_preview_url_text_length": 4096,
            "max_recipient_phone_length": 20,
        }
