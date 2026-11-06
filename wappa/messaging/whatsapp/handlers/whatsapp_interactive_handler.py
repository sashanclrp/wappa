"""WhatsApp interactive message handler (buttons, lists, CTA URL)."""

from typing import Any

from wappa.core.logging.logger import get_logger
from wappa.domain.interactive import (
    InteractiveHeader,
    ListSection,
    MediaRef,
    ReplyButton,
)
from wappa.domain.results import MessageResult
from wappa.messaging.whatsapp.client.whatsapp_client import WhatsAppClient
from wappa.messaging.whatsapp.models.basic_models import message_result_from_payload
from wappa.messaging.whatsapp.utils.error_helpers import handle_whatsapp_error
from wappa.schemas.core.recipient import apply_recipient_to_payload
from wappa.schemas.core.types import PlatformType


def wa_media_object(ref: MediaRef) -> dict[str, Any]:
    """Cloud API media object: the uploaded ``id`` when set, else the ``link``."""
    if ref.media_id is not None:
        return {"id": ref.media_id}
    return {"link": str(ref.url)}


def wa_header(header: InteractiveHeader) -> dict[str, Any]:
    """``InteractiveHeader`` maps 1:1 onto the Cloud API header object."""
    if header.kind == "text":
        return {"type": "text", "text": header.text}
    assert header.media is not None  # guaranteed by InteractiveHeader
    media = wa_media_object(header.media)
    if header.filename is not None:
        media["filename"] = header.filename
    return {"type": header.kind, header.kind: media}


class WhatsAppInteractiveHandler:
    """WhatsApp interactive messaging via composition in WhatsAppMessenger."""

    def __init__(self, client: WhatsAppClient, inbox_id: str):
        self.client = client
        self._inbox_id = inbox_id
        self.logger = get_logger(__name__)

    def _validation_error(
        self, error: str, error_code: str, recipient: str
    ) -> MessageResult:
        return MessageResult(
            success=False,
            error=error,
            error_code=error_code,
            recipient=recipient,
            recipient_bsuid=None,
            recipient_phone=None,
            platform=PlatformType.WHATSAPP,
            inbox_id=self._inbox_id,
        )

    def _build_interactive_payload(
        self,
        recipient: str,
        interactive_data: dict[str, Any],
        reply_to_message_id: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "type": "interactive",
            "interactive": interactive_data,
        }
        apply_recipient_to_payload(payload, recipient)
        if reply_to_message_id:
            payload["context"] = {"message_id": reply_to_message_id}
        return payload

    async def _send_message_payload(
        self, payload: dict[str, Any], recipient: str
    ) -> MessageResult:
        response = await self.client.post_request(payload)
        return message_result_from_payload(
            response,
            inbox_id=self._inbox_id,
            fallback_recipient=recipient,
        )

    @property
    def platform(self) -> PlatformType:
        return PlatformType.WHATSAPP

    @property
    def inbox_id(self) -> str:
        return self._inbox_id

    async def send_buttons_menu(
        self,
        recipient: str,
        body: str,
        buttons: list[ReplyButton],
        header: InteractiveHeader | None = None,
        footer_text: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        """Limits are checked by the neutral values and ``check_button_message``."""
        try:
            interactive_data: dict[str, Any] = {
                "type": "button",
                "body": {"text": body},
                "action": {
                    "buttons": [
                        {"type": "reply", "reply": {"id": b.id, "title": b.title}}
                        for b in buttons
                    ]
                },
            }
            if header:
                interactive_data["header"] = wa_header(header)
            if footer_text:
                interactive_data["footer"] = {"text": footer_text}
            payload = self._build_interactive_payload(
                recipient=recipient,
                interactive_data=interactive_data,
                reply_to_message_id=reply_to_message_id,
            )

            self.logger.debug(
                f"Sending interactive button menu to {recipient} with {len(buttons)} buttons"
            )
            result = await self._send_message_payload(payload, recipient)
            self.logger.info(
                f"Interactive button menu sent successfully to {result.recipient}, "
                f"id: {result.message_id}"
            )
            return result

        except Exception as e:
            return handle_whatsapp_error(
                error=e,
                operation="send interactive button menu",
                recipient=recipient,
                inbox_id=self._inbox_id,
                logger=self.logger,
            )

    async def send_list_menu(
        self,
        recipient: str,
        body: str,
        button_text: str,
        sections: list[ListSection],
        header: str | None = None,
        footer_text: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        """Limits are checked by the neutral values and ``check_list_message``."""
        try:
            formatted_sections: list[dict[str, Any]] = []
            for section in sections:
                rows: list[dict[str, Any]] = []
                for row in section.rows:
                    formatted_row = {"id": row.id, "title": row.title}
                    if row.description:
                        formatted_row["description"] = row.description
                    rows.append(formatted_row)
                formatted: dict[str, Any] = {"rows": rows}
                if section.title is not None:
                    formatted["title"] = section.title
                formatted_sections.append(formatted)

            interactive_data: dict[str, Any] = {
                "type": "list",
                "body": {"text": body},
                "action": {"button": button_text, "sections": formatted_sections},
            }
            if header:
                interactive_data["header"] = {"type": "text", "text": header}
            if footer_text:
                interactive_data["footer"] = {"text": footer_text}
            payload = self._build_interactive_payload(
                recipient=recipient,
                interactive_data=interactive_data,
                reply_to_message_id=reply_to_message_id,
            )
            self.logger.debug(
                f"Sending list menu message to {recipient} with {len(sections)} sections"
            )
            result = await self._send_message_payload(payload, recipient)
            self.logger.info(
                f"List menu message sent successfully to {result.recipient}, "
                f"id: {result.message_id}"
            )
            return result

        except Exception as e:
            return handle_whatsapp_error(
                error=e,
                operation="send list menu",
                recipient=recipient,
                inbox_id=self._inbox_id,
                logger=self.logger,
                extra_context=f"button_text: '{button_text}', sections_count: {len(sections)}, body_length: {len(body)}",
                include_traceback=True,
            )

    async def send_cta_button(
        self,
        recipient: str,
        body: str,
        button_text: str,
        button_url: str,
        header: InteractiveHeader | None = None,
        footer_text: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        """Limits are checked by ``check_cta_message`` before this call."""
        try:
            interactive_data = {
                "type": "cta_url",
                "body": {"text": body},
                "action": {
                    "name": "cta_url",
                    "parameters": {"display_text": button_text, "url": button_url},
                },
            }
            payload = self._build_interactive_payload(
                recipient=recipient,
                interactive_data=interactive_data,
                reply_to_message_id=reply_to_message_id,
            )
            if header:
                payload["interactive"]["header"] = wa_header(header)
            if footer_text:
                payload["interactive"]["footer"] = {"text": footer_text}

            self.logger.debug(
                f"Sending CTA button message to {recipient} with URL: {button_url}"
            )
            result = await self._send_message_payload(payload, recipient)
            self.logger.info(
                f"CTA button message sent successfully to {result.recipient}, "
                f"id: {result.message_id}"
            )
            return result

        except Exception as e:
            return handle_whatsapp_error(
                error=e,
                operation="send CTA button message",
                recipient=recipient,
                inbox_id=self._inbox_id,
                logger=self.logger,
            )

    async def send_contact_request(
        self,
        recipient: str,
        body: str,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        """Ask a username-only user to share their phone number."""
        try:
            if not body or len(body) > 4096:
                return self._validation_error(
                    "Body text must contain 1 to 4096 characters",
                    "INVALID_BODY",
                    recipient,
                )

            payload = self._build_interactive_payload(
                recipient=recipient,
                interactive_data={
                    "type": "request_contact_info",
                    "body": {"text": body},
                    "action": {"name": "request_contact_info"},
                },
                reply_to_message_id=reply_to_message_id,
            )
            return await self._send_message_payload(payload, recipient)
        except Exception as e:
            return handle_whatsapp_error(
                error=e,
                operation="send contact information request",
                recipient=recipient,
                inbox_id=self._inbox_id,
                logger=self.logger,
            )
