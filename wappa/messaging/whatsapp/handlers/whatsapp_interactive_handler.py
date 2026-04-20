"""WhatsApp interactive message handler (buttons, lists, CTA URL)."""

from typing import Any

from wappa.core.logging.logger import get_logger
from wappa.messaging.whatsapp.client.whatsapp_client import WhatsAppClient
from wappa.messaging.whatsapp.models.basic_models import MessageResult
from wappa.messaging.whatsapp.models.interactive_models import (
    HeaderType,
    InteractiveHeader,
    ListSection,
    ReplyButton,
    validate_buttons_menu_limits,
    validate_header_constraints,
)
from wappa.messaging.whatsapp.utils.error_helpers import handle_whatsapp_error
from wappa.schemas.core.recipient import apply_recipient_to_payload
from wappa.schemas.core.types import PlatformType

_VALID_HEADER_TYPES = {
    HeaderType.TEXT,
    HeaderType.IMAGE,
    HeaderType.VIDEO,
    HeaderType.DOCUMENT,
}


class WhatsAppInteractiveHandler:
    """WhatsApp interactive messaging via composition in WhatsAppMessenger."""

    def __init__(self, client: WhatsAppClient, tenant_id: str):
        self.client = client
        self._tenant_id = tenant_id
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
            tenant_id=self._tenant_id,
            api_response=None,
        )

    def _check_validations(
        self, validations: list[tuple[bool, str, str]], recipient: str
    ) -> MessageResult | None:
        # Each tuple is (failed_condition, error_message, error_code).
        for condition, error, code in validations:
            if condition:
                return self._validation_error(error, code, recipient)
        return None

    def _validate_media_header(
        self, header: InteractiveHeader, recipient: str
    ) -> MessageResult | None:
        match header.type:
            case HeaderType.IMAGE:
                media_field, media_name = header.image, "Image"
            case HeaderType.VIDEO:
                media_field, media_name = header.video, "Video"
            case HeaderType.DOCUMENT:
                media_field, media_name = header.document, "Document"
            case _:
                return None

        if not media_field or (
            not media_field.get("id") and not media_field.get("link")
        ):
            return self._validation_error(
                f"{media_name} header must include either 'id' or 'link'",
                "INVALID_MEDIA_HEADER",
                recipient,
            )
        return None

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
        return MessageResult.from_response_payload(
            response,
            tenant_id=self._tenant_id,
            fallback_recipient=recipient,
        )

    def _build_header_dict(self, header: InteractiveHeader) -> dict[str, Any]:
        header_dict: dict[str, Any] = {"type": header.type.value}
        match header.type:
            case HeaderType.TEXT:
                header_dict["text"] = header.text
            case HeaderType.IMAGE if header.image:
                header_dict["image"] = header.image
            case HeaderType.VIDEO if header.video:
                header_dict["video"] = header.video
            case HeaderType.DOCUMENT if header.document:
                header_dict["document"] = header.document
        return header_dict

    @property
    def platform(self) -> PlatformType:
        return PlatformType.WHATSAPP

    @property
    def tenant_id(self) -> str:
        return self._tenant_id

    async def send_buttons_menu(
        self,
        recipient: str,
        body: str,
        buttons: list[ReplyButton],
        header: InteractiveHeader | None = None,
        footer_text: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        try:
            validate_buttons_menu_limits(buttons)
            if header:
                validate_header_constraints(header, footer_text)

            basic_validations: list[tuple[bool, str, str]] = [
                (
                    len(body) > 1024,
                    "Body text cannot exceed 1024 characters",
                    "BODY_TOO_LONG",
                ),
                (
                    footer_text is not None and len(footer_text) > 60,
                    "Footer text cannot exceed 60 characters",
                    "FOOTER_TOO_LONG",
                ),
            ]
            if error := self._check_validations(basic_validations, recipient):
                return error

            if header:
                header_validations: list[tuple[bool, str, str]] = [
                    (
                        header.type not in _VALID_HEADER_TYPES,
                        f"Header type must be one of {[t.value for t in _VALID_HEADER_TYPES]}",
                        "INVALID_HEADER_TYPE",
                    ),
                    (
                        header.type == HeaderType.TEXT and not header.text,
                        "Text header must include 'text' field",
                        "INVALID_TEXT_HEADER",
                    ),
                ]
                if error := self._check_validations(header_validations, recipient):
                    return error
                if error := self._validate_media_header(header, recipient):
                    return error

            formatted_buttons = []
            for button in buttons:
                button_validations: list[tuple[bool, str, str]] = [
                    (
                        len(button.title) > 20,
                        f"Button title '{button.title}' exceeds 20 characters",
                        "BUTTON_TITLE_TOO_LONG",
                    ),
                    (
                        len(button.id) > 256,
                        f"Button ID '{button.id}' exceeds 256 characters",
                        "BUTTON_ID_TOO_LONG",
                    ),
                ]
                if error := self._check_validations(button_validations, recipient):
                    return error
                formatted_buttons.append(
                    {"type": "reply", "reply": {"id": button.id, "title": button.title}}
                )

            interactive_data: dict[str, Any] = {
                "type": "button",
                "body": {"text": body},
                "action": {"buttons": formatted_buttons},
            }
            payload = self._build_interactive_payload(
                recipient=recipient,
                interactive_data=interactive_data,
                reply_to_message_id=reply_to_message_id,
            )
            if header:
                payload["interactive"]["header"] = self._build_header_dict(header)
            if footer_text:
                payload["interactive"]["footer"] = {"text": footer_text}

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
                tenant_id=self._tenant_id,
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
        try:
            # Emit explicit error log for oversized button_text before validation short-circuits.
            if len(button_text) > 20:
                self.logger.error(
                    f"WhatsApp List Button Text Validation Failed: '{button_text}' "
                    f"({len(button_text)} chars) exceeds 20 character limit. "
                    f"Please shorten the button text in your configuration."
                )

            basic_validations: list[tuple[bool, str, str]] = [
                (
                    len(body) > 4096,
                    "Body text cannot exceed 4096 characters",
                    "BODY_TOO_LONG",
                ),
                (
                    len(button_text) > 20,
                    f"Button text '{button_text}' ({len(button_text)} chars) exceeds 20 character limit",
                    "BUTTON_TEXT_TOO_LONG",
                ),
                (
                    len(sections) > 10,
                    "Maximum of 10 sections allowed",
                    "TOO_MANY_SECTIONS",
                ),
                (
                    header is not None and len(header) > 60,
                    "Header text cannot exceed 60 characters",
                    "HEADER_TOO_LONG",
                ),
                (
                    footer_text is not None and len(footer_text) > 60,
                    "Footer text cannot exceed 60 characters",
                    "FOOTER_TOO_LONG",
                ),
            ]
            if error := self._check_validations(basic_validations, recipient):
                return error

            formatted_sections = []
            all_row_ids: list[str] = []

            for section in sections:
                section_validations: list[tuple[bool, str, str]] = [
                    (
                        len(section.title) > 24,
                        f"Section title '{section.title}' exceeds 24 characters",
                        "SECTION_TITLE_TOO_LONG",
                    ),
                    (
                        len(section.rows) > 10,
                        f"Section '{section.title}' has more than 10 rows",
                        "TOO_MANY_ROWS",
                    ),
                ]
                if error := self._check_validations(section_validations, recipient):
                    return error

                formatted_rows = []
                for row in section.rows:
                    row_validations: list[tuple[bool, str, str]] = [
                        (
                            len(row.id) > 200,
                            f"Row ID '{row.id}' exceeds 200 characters",
                            "ROW_ID_TOO_LONG",
                        ),
                        (
                            len(row.title) > 24,
                            f"Row title '{row.title}' exceeds 24 characters",
                            "ROW_TITLE_TOO_LONG",
                        ),
                        (
                            row.description is not None and len(row.description) > 72,
                            f"Row description for '{row.title}' exceeds 72 characters",
                            "ROW_DESCRIPTION_TOO_LONG",
                        ),
                        (
                            row.id in all_row_ids,
                            f"Row ID '{row.id}' is not unique",
                            "DUPLICATE_ROW_ID",
                        ),
                    ]
                    if error := self._check_validations(row_validations, recipient):
                        return error

                    all_row_ids.append(row.id)
                    formatted_row = {"id": row.id, "title": row.title}
                    if row.description:
                        formatted_row["description"] = row.description
                    formatted_rows.append(formatted_row)

                formatted_sections.append(
                    {"title": section.title, "rows": formatted_rows}
                )

            interactive_data = {
                "type": "list",
                "body": {"text": body},
                "action": {"button": button_text, "sections": formatted_sections},
            }
            payload = self._build_interactive_payload(
                recipient=recipient,
                interactive_data=interactive_data,
                reply_to_message_id=reply_to_message_id,
            )
            if header:
                payload["interactive"]["header"] = {"type": "text", "text": header}
            if footer_text:
                payload["interactive"]["footer"] = {"text": footer_text}

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
                tenant_id=self._tenant_id,
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
        header_text: str | None = None,
        footer_text: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        try:
            validations: list[tuple[bool, str, str]] = [
                (
                    not all([body, button_text, button_url]),
                    "body, button_text, and button_url are required parameters",
                    "MISSING_REQUIRED_PARAMS",
                ),
                (
                    not button_url.startswith(("http://", "https://")),
                    "button_url must start with http:// or https://",
                    "INVALID_URL_FORMAT",
                ),
            ]
            if error := self._check_validations(validations, recipient):
                return error

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
            if header_text:
                payload["interactive"]["header"] = {"type": "text", "text": header_text}
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
                tenant_id=self._tenant_id,
                logger=self.logger,
            )
