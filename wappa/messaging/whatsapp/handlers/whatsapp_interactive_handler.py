"""
WhatsApp interactive message handler implementation.

Provides interactive messaging functionality for WhatsApp Business API:
- Button messages (quick reply buttons, max 3)
- List messages (sectioned lists, max 10 sections with 10 rows each)
- Call-to-action messages (URL buttons)

This handler is used by WhatsAppMessenger via composition pattern to implement
the interactive methods of the IMessenger interface.

Based on existing whatsapp_latest/services/interactive_message.py functionality
with SOLID architecture improvements.
"""

from wappa.core.logging.logger import get_logger
from wappa.messaging.whatsapp.client.whatsapp_client import WhatsAppClient
from wappa.messaging.whatsapp.models.basic_models import MessageResult
from wappa.messaging.whatsapp.models.interactive_models import (
    HeaderType,
    InteractiveHeader,
    ReplyButton,
    validate_buttons_menu_limits,
    validate_header_constraints,
)
from wappa.messaging.whatsapp.utils.error_helpers import handle_whatsapp_error
from wappa.schemas.core.types import PlatformType


class WhatsAppInteractiveHandler:
    """
    WhatsApp-specific implementation for interactive messaging operations.

    Provides methods for sending interactive messages via WhatsApp Business API:
    - send_buttons_menu: Quick reply button messages
    - send_list_menu: Sectioned list messages
    - send_cta_button: Call-to-action URL button messages

    Used by WhatsAppMessenger via composition to implement IMessenger interactive methods.
    Follows the same patterns as WhatsAppMediaHandler for consistency.
    """

    def __init__(self, client: WhatsAppClient, tenant_id: str):
        """Initialize interactive handler with WhatsApp client.

        Args:
            client: Configured WhatsApp client for API operations
            tenant_id: Tenant identifier (phone_number_id in WhatsApp context)
        """
        self.client = client
        self._tenant_id = tenant_id
        self.logger = get_logger(__name__)

    def _validation_error(
        self, error: str, error_code: str, recipient: str
    ) -> MessageResult:
        """Create a validation error MessageResult.

        Args:
            error: Human-readable error message
            error_code: Machine-readable error code
            recipient: Phone number of the intended recipient

        Returns:
            MessageResult with success=False and error details
        """
        return MessageResult(
            success=False,
            error=error,
            error_code=error_code,
            recipient=recipient,
            platform=PlatformType.WHATSAPP,
            tenant_id=self._tenant_id,
        )

    def _check_validations(
        self, validations: list[tuple[bool, str, str]], recipient: str
    ) -> MessageResult | None:
        """Check a list of validation rules and return first error if any.

        Args:
            validations: List of tuples (condition, error_message, error_code)
                         where condition=True means validation failed
            recipient: Phone number for error result

        Returns:
            MessageResult if validation failed, None if all validations pass
        """
        for condition, error, code in validations:
            if condition:
                return self._validation_error(error, code, recipient)
        return None

    def _validate_media_header(
        self, header: InteractiveHeader, recipient: str
    ) -> MessageResult | None:
        """Validate media header has required id or link field.

        Args:
            header: The interactive header to validate
            recipient: Phone number for error result

        Returns:
            MessageResult if validation failed, None if valid
        """
        media_field_map = {
            HeaderType.IMAGE: header.image,
            HeaderType.VIDEO: header.video,
            HeaderType.DOCUMENT: header.document,
        }
        media_names = {
            HeaderType.IMAGE: "Image",
            HeaderType.VIDEO: "Video",
            HeaderType.DOCUMENT: "Document",
        }

        media_field = media_field_map.get(header.type)
        media_name = media_names.get(header.type)

        if media_name and (
            not media_field
            or (not media_field.get("id") and not media_field.get("link"))
        ):
            return self._validation_error(
                f"{media_name} header must include either 'id' or 'link'",
                "INVALID_MEDIA_HEADER",
                recipient,
            )
        return None

    @property
    def platform(self) -> PlatformType:
        """Get the platform this handler operates on."""
        return PlatformType.WHATSAPP

    @property
    def tenant_id(self) -> str:
        """Get the tenant ID this handler serves."""
        return self._tenant_id

    async def send_buttons_menu(
        self,
        to: str,
        body: str,
        buttons: list[ReplyButton],
        header: InteractiveHeader | None = None,
        footer_text: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        """
        Send an interactive button menu message via WhatsApp.

        Based on existing WhatsAppServiceInteractive.send_buttons_menu() with
        improved error handling, logging, and result structure.

        Args:
            to: Recipient's phone number
            body: Main message text (max 1024 chars)
            buttons: List of ReplyButton models (max 3 buttons)
            header: Optional InteractiveHeader model with type and content
            footer_text: Footer text (max 60 chars)
            reply_to_message_id: Optional message ID to reply to

        Returns:
            MessageResult with operation status and metadata

        Raises:
            ValueError: If any input parameters are invalid
        """
        try:
            # Validate using utility functions
            validate_buttons_menu_limits(buttons)
            if header:
                validate_header_constraints(header, footer_text)

            # Basic field validations
            valid_header_types = {
                HeaderType.TEXT,
                HeaderType.IMAGE,
                HeaderType.VIDEO,
                HeaderType.DOCUMENT,
            }
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
            if error := self._check_validations(basic_validations, to):
                return error

            # Header validations
            if header:
                header_validations: list[tuple[bool, str, str]] = [
                    (
                        header.type not in valid_header_types,
                        f"Header type must be one of {[t.value for t in valid_header_types]}",
                        "INVALID_HEADER_TYPE",
                    ),
                    (
                        header.type == HeaderType.TEXT and not header.text,
                        "Text header must include 'text' field",
                        "INVALID_TEXT_HEADER",
                    ),
                ]
                if error := self._check_validations(header_validations, to):
                    return error

                if error := self._validate_media_header(header, to):
                    return error

            # Construct button objects with validation
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
                if error := self._check_validations(button_validations, to):
                    return error

                formatted_buttons.append(
                    {"type": "reply", "reply": {"id": button.id, "title": button.title}}
                )

            # Construct payload
            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": to,
                "type": "interactive",
                "interactive": {
                    "type": "button",
                    "body": {"text": body},
                    "action": {"buttons": formatted_buttons},
                },
            }

            # Add reply context if specified
            if reply_to_message_id:
                payload["context"] = {"message_id": reply_to_message_id}

            # Add header if specified
            if header:
                # Convert InteractiveHeader model to dict format for API
                header_dict = {
                    "type": header.type.value  # Convert enum to string
                }

                # Add type-specific content
                if header.type == HeaderType.TEXT:
                    header_dict["text"] = header.text
                elif header.type == HeaderType.IMAGE and header.image:
                    header_dict["image"] = header.image
                elif header.type == HeaderType.VIDEO and header.video:
                    header_dict["video"] = header.video
                elif header.type == HeaderType.DOCUMENT and header.document:
                    header_dict["document"] = header.document

                payload["interactive"]["header"] = header_dict

            # Add footer if specified
            if footer_text:
                payload["interactive"]["footer"] = {"text": footer_text}

            self.logger.debug(
                f"Sending interactive button menu to {to} with {len(buttons)} buttons"
            )

            # Send using WhatsApp client
            response = await self.client.post_request(payload)

            message_id = response.get("messages", [{}])[0].get("id")
            self.logger.info(
                f"Interactive button menu sent successfully to {to}, id: {message_id}"
            )

            return MessageResult(
                success=True,
                message_id=message_id,
                recipient=to,
                platform=PlatformType.WHATSAPP,
                tenant_id=self._tenant_id,
            )

        except Exception as e:
            return handle_whatsapp_error(
                error=e,
                operation="send interactive button menu",
                recipient=to,
                tenant_id=self._tenant_id,
                logger=self.logger,
            )

    async def send_list_menu(
        self,
        to: str,
        body: str,
        button_text: str,
        sections: list[dict],
        header: str | None = None,
        footer_text: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        """
        Send an interactive list menu message via WhatsApp.

        Based on existing WhatsAppServiceInteractive.send_list_menu() with
        improved error handling, logging, and result structure.

        Args:
            to: Recipient's phone number
            body: Main message text (max 4096 chars)
            button_text: Text for the button that opens the list (max 20 chars)
            sections: List of section objects with format:
                {
                    "title": "Section Title", # max 24 chars
                    "rows": [
                        {
                            "id": "unique_id", # max 200 chars
                            "title": "Row Title", # max 24 chars
                            "description": "Optional description" # max 72 chars
                        },
                        ...
                    ]
                }
            header: Header text (max 60 chars)
            footer_text: Footer text (max 60 chars)
            reply_to_message_id: Optional message ID to reply to

        Returns:
            MessageResult with operation status and metadata
        """
        try:
            # Log validation error for button text (helpful for debugging config issues)
            if len(button_text) > 20:
                self.logger.error(
                    f"WhatsApp List Button Text Validation Failed: '{button_text}' "
                    f"({len(button_text)} chars) exceeds 20 character limit. "
                    f"Please shorten the button text in your configuration."
                )

            # Basic field validations
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
            if error := self._check_validations(basic_validations, to):
                return error

            # Validate and format sections
            formatted_sections = []
            all_row_ids: list[str] = []

            for section in sections:
                section_validations: list[tuple[bool, str, str]] = [
                    (
                        len(section["title"]) > 24,
                        f"Section title '{section['title']}' exceeds 24 characters",
                        "SECTION_TITLE_TOO_LONG",
                    ),
                    (
                        len(section["rows"]) > 10,
                        f"Section '{section['title']}' has more than 10 rows",
                        "TOO_MANY_ROWS",
                    ),
                ]
                if error := self._check_validations(section_validations, to):
                    return error

                formatted_rows = []
                for row in section["rows"]:
                    row_validations: list[tuple[bool, str, str]] = [
                        (
                            len(row["id"]) > 200,
                            f"Row ID '{row['id']}' exceeds 200 characters",
                            "ROW_ID_TOO_LONG",
                        ),
                        (
                            len(row["title"]) > 24,
                            f"Row title '{row['title']}' exceeds 24 characters",
                            "ROW_TITLE_TOO_LONG",
                        ),
                        (
                            "description" in row and len(row["description"]) > 72,
                            f"Row description for '{row['title']}' exceeds 72 characters",
                            "ROW_DESCRIPTION_TOO_LONG",
                        ),
                        (
                            row["id"] in all_row_ids,
                            f"Row ID '{row['id']}' is not unique",
                            "DUPLICATE_ROW_ID",
                        ),
                    ]
                    if error := self._check_validations(row_validations, to):
                        return error

                    all_row_ids.append(row["id"])

                    formatted_row = {"id": row["id"], "title": row["title"]}
                    if "description" in row:
                        formatted_row["description"] = row["description"]
                    formatted_rows.append(formatted_row)

                formatted_sections.append(
                    {"title": section["title"], "rows": formatted_rows}
                )

            # Construct payload
            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": to,
                "type": "interactive",
                "interactive": {
                    "type": "list",
                    "body": {"text": body},
                    "action": {"button": button_text, "sections": formatted_sections},
                },
            }

            # Add reply context if specified
            if reply_to_message_id:
                payload["context"] = {"message_id": reply_to_message_id}

            # Add header if specified
            if header:
                payload["interactive"]["header"] = {"type": "text", "text": header}

            # Add footer if specified
            if footer_text:
                payload["interactive"]["footer"] = {"text": footer_text}

            self.logger.debug(
                f"Sending list menu message to {to} with {len(sections)} sections"
            )

            # Send using WhatsApp client
            response = await self.client.post_request(payload)

            message_id = response.get("messages", [{}])[0].get("id")
            self.logger.info(
                f"List menu message sent successfully to {to}, id: {message_id}"
            )

            return MessageResult(
                success=True,
                message_id=message_id,
                recipient=to,
                platform=PlatformType.WHATSAPP,
                tenant_id=self._tenant_id,
            )

        except Exception as e:
            return handle_whatsapp_error(
                error=e,
                operation="send list menu",
                recipient=to,
                tenant_id=self._tenant_id,
                logger=self.logger,
                extra_context=f"button_text: '{button_text}', sections_count: {len(sections)}, body_length: {len(body)}",
                include_traceback=True,
            )

    async def send_cta_button(
        self,
        to: str,
        body: str,
        button_text: str,
        button_url: str,
        header_text: str | None = None,
        footer_text: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        """
        Send an interactive Call-to-Action URL button message via WhatsApp.

        Based on existing WhatsAppServiceInteractive.send_cta_button() with
        improved error handling, logging, and result structure.

        Args:
            to: Recipient's phone number
            body: Required. Message body text
            button_text: Required. Text to display on the button
            button_url: Required. URL to load when button is tapped
            header_text: Text to display in the header
            footer_text: Text to display in the footer
            reply_to_message_id: Optional message ID to reply to

        Returns:
            MessageResult with operation status and metadata
        """
        try:
            # Validate parameters
            validations: list[tuple[bool, str, str]] = [
                (
                    not all([body, button_text, button_url]),
                    "body, button_text, and button_url are required parameters",
                    "MISSING_REQUIRED_PARAMS",
                ),
                (
                    not (
                        button_url.startswith("http://")
                        or button_url.startswith("https://")
                    ),
                    "button_url must start with http:// or https://",
                    "INVALID_URL_FORMAT",
                ),
            ]
            if error := self._check_validations(validations, to):
                return error

            # Construct payload
            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": to,
                "type": "interactive",
                "interactive": {
                    "type": "cta_url",
                    "body": {"text": body},
                    "action": {
                        "name": "cta_url",
                        "parameters": {"display_text": button_text, "url": button_url},
                    },
                },
            }

            # Add reply context if specified
            if reply_to_message_id:
                payload["context"] = {"message_id": reply_to_message_id}

            # Add optional header if provided
            if header_text:
                payload["interactive"]["header"] = {"type": "text", "text": header_text}

            # Add optional footer if provided
            if footer_text:
                payload["interactive"]["footer"] = {"text": footer_text}

            self.logger.debug(
                f"Sending CTA button message to {to} with URL: {button_url}"
            )

            # Send using WhatsApp client
            response = await self.client.post_request(payload)

            message_id = response.get("messages", [{}])[0].get("id")
            self.logger.info(
                f"CTA button message sent successfully to {to}, id: {message_id}"
            )

            return MessageResult(
                success=True,
                message_id=message_id,
                recipient=to,
                platform=PlatformType.WHATSAPP,
                tenant_id=self._tenant_id,
            )

        except Exception as e:
            return handle_whatsapp_error(
                error=e,
                operation="send CTA button message",
                recipient=to,
                tenant_id=self._tenant_id,
                logger=self.logger,
            )
