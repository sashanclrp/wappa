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
            # Validate input parameters using utility functions
            if len(body) > 1024:
                return MessageResult(
                    success=False,
                    error="Body text cannot exceed 1024 characters",
                    error_code="BODY_TOO_LONG",
                    recipient=to,
                    platform=PlatformType.WHATSAPP,
                    tenant_id=self._tenant_id,
                )

            validate_buttons_menu_limits(buttons)
            if header:
                validate_header_constraints(header, footer_text)

            # Validate footer length
            if footer_text and len(footer_text) > 60:
                return MessageResult(
                    success=False,
                    error="Footer text cannot exceed 60 characters",
                    error_code="FOOTER_TOO_LONG",
                    recipient=to,
                    platform=PlatformType.WHATSAPP,
                    tenant_id=self._tenant_id,
                )

            # Validate header if provided - adapted for InteractiveHeader model
            if header:
                valid_header_types = {
                    HeaderType.TEXT,
                    HeaderType.IMAGE,
                    HeaderType.VIDEO,
                    HeaderType.DOCUMENT,
                }
                if header.type not in valid_header_types:
                    return MessageResult(
                        success=False,
                        error=f"Header type must be one of {[t.value for t in valid_header_types]}",
                        error_code="INVALID_HEADER_TYPE",
                        recipient=to,
                        platform=PlatformType.WHATSAPP,
                        tenant_id=self._tenant_id,
                    )

                # Validate text header
                if header.type == HeaderType.TEXT and not header.text:
                    return MessageResult(
                        success=False,
                        error="Text header must include 'text' field",
                        error_code="INVALID_TEXT_HEADER",
                        recipient=to,
                        platform=PlatformType.WHATSAPP,
                        tenant_id=self._tenant_id,
                    )

                # Validate media headers
                if header.type == HeaderType.IMAGE:
                    if not header.image or (
                        not header.image.get("id") and not header.image.get("link")
                    ):
                        return MessageResult(
                            success=False,
                            error="Image header must include either 'id' or 'link'",
                            error_code="INVALID_MEDIA_HEADER",
                            recipient=to,
                            platform=PlatformType.WHATSAPP,
                            tenant_id=self._tenant_id,
                        )
                elif header.type == HeaderType.VIDEO:
                    if not header.video or (
                        not header.video.get("id") and not header.video.get("link")
                    ):
                        return MessageResult(
                            success=False,
                            error="Video header must include either 'id' or 'link'",
                            error_code="INVALID_MEDIA_HEADER",
                            recipient=to,
                            platform=PlatformType.WHATSAPP,
                            tenant_id=self._tenant_id,
                        )
                elif header.type == HeaderType.DOCUMENT:
                    if not header.document or (
                        not header.document.get("id")
                        and not header.document.get("link")
                    ):
                        return MessageResult(
                            success=False,
                            error="Document header must include either 'id' or 'link'",
                            error_code="INVALID_MEDIA_HEADER",
                            recipient=to,
                            platform=PlatformType.WHATSAPP,
                            tenant_id=self._tenant_id,
                        )

            # Construct button objects with individual validation
            formatted_buttons = []
            for button in buttons:
                if len(button.title) > 20:
                    return MessageResult(
                        success=False,
                        error=f"Button title '{button.title}' exceeds 20 characters",
                        error_code="BUTTON_TITLE_TOO_LONG",
                        recipient=to,
                        platform=PlatformType.WHATSAPP,
                        tenant_id=self._tenant_id,
                    )
                if len(button.id) > 256:
                    return MessageResult(
                        success=False,
                        error=f"Button ID '{button.id}' exceeds 256 characters",
                        error_code="BUTTON_ID_TOO_LONG",
                        recipient=to,
                        platform=PlatformType.WHATSAPP,
                        tenant_id=self._tenant_id,
                    )

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
            # Check for authentication errors
            if "401" in str(e) or "Unauthorized" in str(e):
                self.logger.error(
                    "🚨 CRITICAL: WhatsApp Authentication Failed - Cannot Send Interactive Messages! 🚨"
                )
                self.logger.error(
                    f"🚨 Check WhatsApp access token for tenant {self._tenant_id}"
                )

            self.logger.error(
                f"Failed to send interactive button menu to {to}: {str(e)}"
            )
            return MessageResult(
                success=False,
                error=str(e),
                recipient=to,
                platform=PlatformType.WHATSAPP,
                tenant_id=self._tenant_id,
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
            # Validate input parameters
            if len(body) > 4096:
                return MessageResult(
                    success=False,
                    error="Body text cannot exceed 4096 characters",
                    error_code="BODY_TOO_LONG",
                    recipient=to,
                    platform=PlatformType.WHATSAPP,
                    tenant_id=self._tenant_id,
                )

            if len(button_text) > 20:
                self.logger.error(
                    f"⚠️ WhatsApp List Button Text Validation Failed: '{button_text}' "
                    f"({len(button_text)} chars) exceeds 20 character limit. "
                    f"Please shorten the button text in your configuration."
                )
                return MessageResult(
                    success=False,
                    error=f"Button text '{button_text}' ({len(button_text)} chars) exceeds 20 character limit",
                    error_code="BUTTON_TEXT_TOO_LONG",
                    recipient=to,
                    platform=PlatformType.WHATSAPP,
                    tenant_id=self._tenant_id,
                )

            if len(sections) > 10:
                return MessageResult(
                    success=False,
                    error="Maximum of 10 sections allowed",
                    error_code="TOO_MANY_SECTIONS",
                    recipient=to,
                    platform=PlatformType.WHATSAPP,
                    tenant_id=self._tenant_id,
                )

            if header and len(header) > 60:
                return MessageResult(
                    success=False,
                    error="Header text cannot exceed 60 characters",
                    error_code="HEADER_TOO_LONG",
                    recipient=to,
                    platform=PlatformType.WHATSAPP,
                    tenant_id=self._tenant_id,
                )

            if footer_text and len(footer_text) > 60:
                return MessageResult(
                    success=False,
                    error="Footer text cannot exceed 60 characters",
                    error_code="FOOTER_TOO_LONG",
                    recipient=to,
                    platform=PlatformType.WHATSAPP,
                    tenant_id=self._tenant_id,
                )

            # Validate and format sections
            formatted_sections = []
            all_row_ids = []

            for section in sections:
                if len(section["title"]) > 24:
                    return MessageResult(
                        success=False,
                        error=f"Section title '{section['title']}' exceeds 24 characters",
                        error_code="SECTION_TITLE_TOO_LONG",
                        recipient=to,
                        platform=PlatformType.WHATSAPP,
                        tenant_id=self._tenant_id,
                    )

                if len(section["rows"]) > 10:
                    return MessageResult(
                        success=False,
                        error=f"Section '{section['title']}' has more than 10 rows",
                        error_code="TOO_MANY_ROWS",
                        recipient=to,
                        platform=PlatformType.WHATSAPP,
                        tenant_id=self._tenant_id,
                    )

                formatted_rows = []
                for row in section["rows"]:
                    if len(row["id"]) > 200:
                        return MessageResult(
                            success=False,
                            error=f"Row ID '{row['id']}' exceeds 200 characters",
                            error_code="ROW_ID_TOO_LONG",
                            recipient=to,
                            platform=PlatformType.WHATSAPP,
                            tenant_id=self._tenant_id,
                        )
                    if len(row["title"]) > 24:
                        return MessageResult(
                            success=False,
                            error=f"Row title '{row['title']}' exceeds 24 characters",
                            error_code="ROW_TITLE_TOO_LONG",
                            recipient=to,
                            platform=PlatformType.WHATSAPP,
                            tenant_id=self._tenant_id,
                        )
                    if "description" in row and len(row["description"]) > 72:
                        return MessageResult(
                            success=False,
                            error=f"Row description for '{row['title']}' exceeds 72 characters",
                            error_code="ROW_DESCRIPTION_TOO_LONG",
                            recipient=to,
                            platform=PlatformType.WHATSAPP,
                            tenant_id=self._tenant_id,
                        )

                    # Check for duplicate row IDs
                    if row["id"] in all_row_ids:
                        return MessageResult(
                            success=False,
                            error=f"Row ID '{row['id']}' is not unique",
                            error_code="DUPLICATE_ROW_ID",
                            recipient=to,
                            platform=PlatformType.WHATSAPP,
                            tenant_id=self._tenant_id,
                        )
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
            # Check for authentication errors
            if "401" in str(e) or "Unauthorized" in str(e):
                self.logger.error(
                    "🚨 CRITICAL: WhatsApp Authentication Failed - Cannot Send List Messages! 🚨"
                )
                self.logger.error(
                    f"🚨 Check WhatsApp access token for tenant {self._tenant_id}"
                )

            self.logger.error(
                f"❌ Failed to send list menu to {to}: {str(e)} - "
                f"button_text: '{button_text}', sections_count: {len(sections)}, "
                f"body_length: {len(body)}",
                exc_info=True,
            )
            return MessageResult(
                success=False,
                error=str(e),
                recipient=to,
                platform=PlatformType.WHATSAPP,
                tenant_id=self._tenant_id,
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
            # Validate required parameters
            if not all([body, button_text, button_url]):
                return MessageResult(
                    success=False,
                    error="body, button_text, and button_url are required parameters",
                    error_code="MISSING_REQUIRED_PARAMS",
                    recipient=to,
                    platform=PlatformType.WHATSAPP,
                    tenant_id=self._tenant_id,
                )

            # Validate URL format
            if not (
                button_url.startswith("http://") or button_url.startswith("https://")
            ):
                return MessageResult(
                    success=False,
                    error="button_url must start with http:// or https://",
                    error_code="INVALID_URL_FORMAT",
                    recipient=to,
                    platform=PlatformType.WHATSAPP,
                    tenant_id=self._tenant_id,
                )

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
            # Check for authentication errors
            if "401" in str(e) or "Unauthorized" in str(e):
                self.logger.error(
                    "🚨 CRITICAL: WhatsApp Authentication Failed - Cannot Send CTA Messages! 🚨"
                )
                self.logger.error(
                    f"🚨 Check WhatsApp access token for tenant {self._tenant_id}"
                )

            self.logger.error(f"Failed to send CTA button message to {to}: {str(e)}")
            return MessageResult(
                success=False,
                error=str(e),
                recipient=to,
                platform=PlatformType.WHATSAPP,
                tenant_id=self._tenant_id,
            )
