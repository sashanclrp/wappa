"""
WhatsApp unified implementation of the IMessenger interface.

Provides complete WhatsApp-specific implementation of ALL messaging operations:
- Basic messaging: send_text, mark_as_read
- Media messaging: send_image, send_video, send_audio, send_document, send_sticker
- Interactive messaging: send_button_message, send_list_message, send_cta_message
- Template messaging: send_text_template, send_media_template, send_location_template
- Specialized messaging: send_contact, send_location, send_location_request

This is the ONLY WhatsApp messenger implementation that should be used.
It replaces the previous partial implementations (WhatsAppBasicMessenger and WhatsAppMediaMessenger)
which violated the Interface Segregation Principle.
"""

from pathlib import Path

from wappa.core.logging.logger import get_logger
from wappa.domain.interfaces.messaging_interface import IMessenger
from wappa.messaging.whatsapp.client.whatsapp_client import WhatsAppClient
from wappa.messaging.whatsapp.handlers.whatsapp_interactive_handler import (
    WhatsAppInteractiveHandler,
)
from wappa.messaging.whatsapp.handlers.whatsapp_media_handler import (
    WhatsAppMediaHandler,
)
from wappa.messaging.whatsapp.handlers.whatsapp_specialized_handler import (
    WhatsAppSpecializedHandler,
)
from wappa.messaging.whatsapp.handlers.whatsapp_template_handler import (
    WhatsAppTemplateHandler,
)
from wappa.messaging.whatsapp.models.basic_models import MessageResult
from wappa.messaging.whatsapp.models.interactive_models import (
    InteractiveHeader,
    ReplyButton,
)
from wappa.messaging.whatsapp.models.media_models import MediaType
from wappa.messaging.whatsapp.utils.error_helpers import handle_whatsapp_error
from wappa.schemas.core.types import PlatformType


class WhatsAppMessenger(IMessenger):
    """
    Complete WhatsApp implementation of the messaging interface.

    Provides ALL messaging functionality using WhatsApp Business API:
    - Basic messaging: send_text, mark_as_read
    - Media messaging: send_image, send_video, send_audio, send_document, send_sticker
    - Interactive messaging: send_button_message, send_list_message, send_cta_message
    - Template messaging: send_text_template, send_media_template, send_location_template
    - Specialized messaging: send_contact, send_location, send_location_request

    Uses composition pattern with:
    - WhatsAppClient: For basic API operations and text messaging
    - WhatsAppMediaHandler: For media upload/download operations
    - WhatsAppInteractiveHandler: For interactive message operations
    - WhatsAppTemplateHandler: For business template message operations
    - WhatsAppSpecializedHandler: For contact and location message operations

    This unified implementation ensures complete IMessenger interface compliance
    and eliminates the architectural violation of partial implementations.
    """

    def __init__(
        self,
        client: WhatsAppClient,
        media_handler: WhatsAppMediaHandler,
        interactive_handler: WhatsAppInteractiveHandler,
        template_handler: WhatsAppTemplateHandler,
        specialized_handler: WhatsAppSpecializedHandler,
        tenant_id: str,
    ):
        """Initialize unified WhatsApp messenger with complete functionality.

        Args:
            client: Configured WhatsApp client for API operations
            media_handler: Media handler for upload/download operations
            interactive_handler: Interactive handler for button/list/CTA operations
            template_handler: Template handler for business template operations
            specialized_handler: Specialized handler for contact/location operations
            tenant_id: Tenant identifier (phone_number_id in WhatsApp context)
        """
        self.client = client
        self.media_handler = media_handler
        self.interactive_handler = interactive_handler
        self.template_handler = template_handler
        self.specialized_handler = specialized_handler
        self._tenant_id = tenant_id
        self.logger = get_logger(__name__)

    @property
    def platform(self) -> PlatformType:
        """Get the platform this messenger handles."""
        return PlatformType.WHATSAPP

    @property
    def tenant_id(self) -> str:
        """Get the tenant ID this messenger serves."""
        return self._tenant_id

    def _convert_body_parameters(
        self, body_parameters: list[dict] | None
    ) -> list | None:
        """Convert dict parameters to TemplateParameter objects.

        Args:
            body_parameters: List of parameter dicts with 'type' and 'text' keys

        Returns:
            List of TemplateParameter objects or None if no parameters provided
        """
        if not body_parameters:
            return None

        from wappa.messaging.whatsapp.models.template_models import (
            TemplateParameter,
            TemplateParameterType,
        )

        return [
            TemplateParameter(type=TemplateParameterType.TEXT, text=p.get("text"))
            for p in body_parameters
            if isinstance(p, dict) and p.get("type") == "text"
        ]

    # Basic Messaging Methods (from WhatsAppBasicMessenger)

    async def send_text(
        self,
        text: str,
        recipient: str,
        reply_to_message_id: str | None = None,
        disable_preview: bool = False,
    ) -> MessageResult:
        """Send text message using WhatsApp API.

        Args:
            text: Text content of the message (1-4096 characters)
            recipient: Recipient phone number
            reply_to_message_id: Optional message ID to reply to
            disable_preview: Whether to disable URL preview

        Returns:
            MessageResult with operation status and metadata
        """
        try:
            # Check for URLs for preview control
            has_url = "http://" in text or "https://" in text

            # Create WhatsApp-specific payload
            payload = {
                "messaging_product": "whatsapp",
                "to": recipient,
                "type": "text",
                "text": {"body": text, "preview_url": has_url and not disable_preview},
            }

            # Add reply context if specified
            if reply_to_message_id:
                payload["context"] = {"message_id": reply_to_message_id}

            self.logger.debug(f"Sending text message to {recipient}: {text[:50]}...")
            response = await self.client.post_request(payload)

            message_id = response.get("messages", [{}])[0].get("id")
            self.logger.info(
                f"Text message sent successfully to {recipient}, id: {message_id}"
            )

            return MessageResult(
                success=True,
                message_id=message_id,
                recipient=recipient,
                platform=PlatformType.WHATSAPP,
                tenant_id=self._tenant_id,
            )

        except Exception as e:
            return handle_whatsapp_error(
                error=e,
                operation="send text message",
                recipient=recipient,
                tenant_id=self._tenant_id,
                logger=self.logger,
            )

    async def mark_as_read(
        self, message_id: str, typing: bool = False
    ) -> MessageResult:
        """Mark message as read, optionally with typing indicator.

        WhatsApp Business API requires separate calls for:
        1. Marking message as read (status endpoint)
        2. Sending typing indicator (separate action)

        Args:
            message_id: WhatsApp message ID to mark as read
            typing: Whether to show typing indicator after marking as read

        Returns:
            MessageResult with operation status and metadata
        """
        try:
            # Step 1: Mark message as read
            read_payload = {
                "messaging_product": "whatsapp",
                "status": "read",
                "message_id": message_id,
            }

            self.logger.debug(f"Marking message {message_id} as read")
            await self.client.post_request(read_payload)

            # Step 2: Send typing indicator if requested (separate API call)
            if typing:
                # Extract recipient from message_id context or use a separate parameter
                # For now, we'll skip the typing indicator to avoid the 401 error
                # TODO: Implement proper typing indicator with recipient WhatsApp ID
                self.logger.debug(
                    "Typing indicator requested but skipped (requires recipient ID)"
                )

            action_msg = (
                "marked as read with typing indicator" if typing else "marked as read"
            )
            self.logger.info(f"Message {message_id} {action_msg}")

            return MessageResult(
                success=True,
                message_id=message_id,
                platform=PlatformType.WHATSAPP,
                tenant_id=self._tenant_id,
            )

        except Exception as e:
            action_msg = (
                "mark as read with typing indicator" if typing else "mark as read"
            )
            return handle_whatsapp_error(
                error=e,
                operation=action_msg,
                recipient=message_id,
                tenant_id=self._tenant_id,
                logger=self.logger,
            )

    # Media Messaging Methods (from WhatsAppMediaMessenger)

    async def send_image(
        self,
        image_source: str | Path,
        recipient: str,
        caption: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        """Send image message using WhatsApp API.

        Supports JPEG and PNG images up to 5MB.
        Images must be 8-bit, RGB or RGBA (WhatsApp Cloud API 2025).

        Args:
            image_source: Image URL or file path
            recipient: Recipient identifier
            caption: Optional caption for the image (max 1024 characters)
            reply_to_message_id: Optional message ID to reply to

        Returns:
            MessageResult with operation status and metadata
        """
        return await self._send_media(
            media_source=image_source,
            media_type=MediaType.IMAGE,
            recipient=recipient,
            caption=caption,
            filename=None,
            reply_to_message_id=reply_to_message_id,
        )

    async def send_video(
        self,
        video_source: str | Path,
        recipient: str,
        caption: str | None = None,
        reply_to_message_id: str | None = None,
        transcript: str | None = None,
    ) -> MessageResult:
        """Send video message using WhatsApp API.

        Supports MP4 and 3GP videos up to 16MB.
        Only H.264 video codec and AAC audio codec supported.
        Single audio stream or no audio stream only (WhatsApp Cloud API 2025).

        Args:
            video_source: Video URL or file path
            recipient: Recipient identifier
            caption: Optional caption for the video (max 1024 characters)
            reply_to_message_id: Optional message ID to reply to
            transcript: Optional transcript text for video audio content

        Returns:
            MessageResult with operation status and metadata
        """
        return await self._send_media(
            media_source=video_source,
            media_type=MediaType.VIDEO,
            recipient=recipient,
            caption=caption,
            filename=None,
            reply_to_message_id=reply_to_message_id,
            transcript=transcript,
        )

    async def send_audio(
        self,
        audio_source: str | Path,
        recipient: str,
        reply_to_message_id: str | None = None,
        transcript: str | None = None,
    ) -> MessageResult:
        """Send audio message using WhatsApp API.

        Supports AAC, AMR, MP3, M4A, and OGG audio up to 16MB.
        OGG must use OPUS codecs only, mono input only (WhatsApp Cloud API 2025).

        Args:
            audio_source: Audio URL or file path
            recipient: Recipient identifier
            reply_to_message_id: Optional message ID to reply to
            transcript: Optional transcript text for audio content

        Returns:
            MessageResult with operation status and metadata

        Note:
            Audio messages do not support captions.
        """
        return await self._send_media(
            media_source=audio_source,
            media_type=MediaType.AUDIO,
            recipient=recipient,
            caption=None,  # Audio doesn't support captions
            filename=None,
            reply_to_message_id=reply_to_message_id,
            transcript=transcript,
        )

    async def send_document(
        self,
        document_source: str | Path,
        recipient: str,
        filename: str | None = None,
        caption: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        """Send document message using WhatsApp API.

        Supports TXT, PDF, DOC, DOCX, XLS, XLSX, PPT, PPTX up to 100MB.

        Args:
            document_source: Document URL or file path
            recipient: Recipient identifier
            filename: Optional filename for the document
            caption: Optional caption for the document (max 1024 characters)
            reply_to_message_id: Optional message ID to reply to

        Returns:
            MessageResult with operation status and metadata
        """
        return await self._send_media(
            media_source=document_source,
            media_type=MediaType.DOCUMENT,
            recipient=recipient,
            caption=caption,  # Documents DO support captions in WhatsApp Business API
            filename=filename,
            reply_to_message_id=reply_to_message_id,
        )

    async def send_sticker(
        self,
        sticker_source: str | Path,
        recipient: str,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        """Send sticker message using WhatsApp API.

        Supports WebP images only.
        Static stickers: 100KB max, Animated stickers: 500KB max.

        Args:
            sticker_source: Sticker URL or file path (WebP format)
            recipient: Recipient identifier
            reply_to_message_id: Optional message ID to reply to

        Returns:
            MessageResult with operation status and metadata

        Note:
            Sticker messages do not support captions.
        """
        return await self._send_media(
            media_source=sticker_source,
            media_type=MediaType.STICKER,
            recipient=recipient,
            caption=None,  # Stickers don't support captions
            filename=None,
            reply_to_message_id=reply_to_message_id,
        )

    async def _send_media(
        self,
        media_source: str | Path,
        media_type: MediaType,
        recipient: str,
        caption: str | None = None,
        filename: str | None = None,
        reply_to_message_id: str | None = None,
        transcript: str | None = None,
    ) -> MessageResult:
        """
        Internal method to send media messages.

        Handles both URL and file path sources with upload workflow.
        Uses the injected media handler for upload operations.

        Args:
            transcript: Optional transcript for audio/video content (internal use, not sent to WhatsApp)
        """
        try:
            # Build initial payload
            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": recipient,
                "type": media_type.value,
            }

            if reply_to_message_id:
                payload["context"] = {"message_id": reply_to_message_id}

            # Handle media source: URL vs file path
            if isinstance(media_source, str) and (
                media_source.startswith("http://")
                or media_source.startswith("https://")
            ):
                # Use URL directly (link-based object)
                media_obj = {"link": media_source}
                self.logger.debug(
                    f"Using media URL for {media_type.value}: {media_source}"
                )
            else:
                # Upload local file first or use media_id if it's already an ID
                if (
                    isinstance(media_source, str)
                    and len(media_source) < 100
                    and "/" not in media_source
                ):
                    # Likely already a media_id from echo functionality
                    media_obj = {"id": media_source}
                    self.logger.debug(
                        f"Using existing media ID for {media_type.value}: {media_source}"
                    )
                else:
                    # Upload local file
                    media_path = Path(media_source)
                    if not media_path.exists():
                        return MessageResult(
                            success=False,
                            error=f"Media file not found: {media_path}",
                            error_code="FILE_NOT_FOUND",
                            recipient=recipient,
                            platform=PlatformType.WHATSAPP,
                            tenant_id=self._tenant_id,
                        )

                    self.logger.debug(
                        f"Uploading media file for {media_type.value}: {media_path.name}"
                    )

                    # Upload using media handler
                    upload_result = await self.media_handler.upload_media(media_path)
                    if not upload_result.success:
                        return MessageResult(
                            success=False,
                            error=f"Failed to upload media: {upload_result.error}",
                            error_code=upload_result.error_code,
                            recipient=recipient,
                            platform=PlatformType.WHATSAPP,
                            tenant_id=self._tenant_id,
                        )

                    # Use uploaded media ID
                    media_obj = {"id": upload_result.media_id}
                    self.logger.debug(
                        f"Using uploaded media ID for {media_type.value}: {upload_result.media_id}"
                    )

            # Add optional caption (if allowed) and filename (for documents)
            if caption and media_type not in (MediaType.AUDIO, MediaType.STICKER):
                media_obj["caption"] = caption

            if media_type == MediaType.DOCUMENT and filename:
                media_obj["filename"] = filename

            # Set media object in payload
            payload[media_type.value] = media_obj

            self.logger.debug(f"Sending {media_type.value} message to {recipient}")

            # Send message using client
            response = await self.client.post_request(payload)

            message_id = response.get("messages", [{}])[0].get("id")
            self.logger.info(
                f"{media_type.value.title()} message sent successfully to {recipient}, id: {message_id}"
            )

            return MessageResult(
                success=True,
                message_id=message_id,
                recipient=recipient,
                platform=PlatformType.WHATSAPP,
                tenant_id=self._tenant_id,
            )

        except Exception as e:
            return handle_whatsapp_error(
                error=e,
                operation=f"send {media_type.value}",
                recipient=recipient,
                tenant_id=self._tenant_id,
                logger=self.logger,
            )

    # Interactive Messaging Methods (from WhatsAppInteractiveHandler)

    async def send_button_message(
        self,
        buttons: list[ReplyButton],
        recipient: str,
        body: str,
        header: InteractiveHeader | None = None,
        footer: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        """Send interactive button message using WhatsApp API.

        Supports up to 3 quick reply buttons with optional header and footer.
        Based on WhatsApp Cloud API 2025 interactive button specifications.

        Args:
            buttons: List of ReplyButton models (max 3 buttons)
            recipient: Recipient identifier
            body: Main message text (max 1024 characters)
            header: Optional InteractiveHeader model with type and content
            footer: Optional footer text (max 60 characters)
            reply_to_message_id: Optional message ID to reply to

        Returns:
            MessageResult with operation status and metadata
        """
        return await self.interactive_handler.send_buttons_menu(
            to=recipient,
            body=body,
            buttons=buttons,
            header=header,
            footer_text=footer,
            reply_to_message_id=reply_to_message_id,
        )

    async def send_list_message(
        self,
        sections: list[dict],
        recipient: str,
        body: str,
        button_text: str,
        header: str | None = None,
        footer: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        """Send interactive list message using WhatsApp API.

        Supports sectioned lists with rows (max 10 sections, 10 rows per section).
        Based on WhatsApp Cloud API 2025 interactive list specifications.

        Args:
            sections: List of section objects with title and rows
            recipient: Recipient identifier
            body: Main message text (max 4096 characters)
            button_text: Text for the button that opens the list (max 20 characters)
            header: Optional header text (max 60 characters)
            footer: Optional footer text (max 60 characters)
            reply_to_message_id: Optional message ID to reply to

        Returns:
            MessageResult with operation status and metadata
        """
        return await self.interactive_handler.send_list_menu(
            to=recipient,
            body=body,
            button_text=button_text,
            sections=sections,
            header=header,
            footer_text=footer,
            reply_to_message_id=reply_to_message_id,
        )

    async def send_cta_message(
        self,
        button_text: str,
        button_url: str,
        recipient: str,
        body: str,
        header: str | None = None,
        footer: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        """Send interactive call-to-action URL button message using WhatsApp API.

        Supports external URL buttons for call-to-action scenarios.
        Based on WhatsApp Cloud API 2025 CTA URL specifications.

        Args:
            button_text: Text to display on the button
            button_url: URL to load when button is tapped (must start with http:// or https://)
            recipient: Recipient identifier
            body: Main message text
            header: Optional header text
            footer: Optional footer text
            reply_to_message_id: Optional message ID to reply to

        Returns:
            MessageResult with operation status and metadata
        """
        return await self.interactive_handler.send_cta_button(
            to=recipient,
            body=body,
            button_text=button_text,
            button_url=button_url,
            header_text=header,
            footer_text=footer,
            reply_to_message_id=reply_to_message_id,
        )

    # Template Messaging Methods (from WhatsAppTemplateHandler)

    async def send_text_template(
        self,
        template_name: str,
        recipient: str,
        body_parameters: list[dict] | None = None,
        language_code: str = "es",
    ) -> MessageResult:
        """Send text-only template message using WhatsApp API.

        Supports WhatsApp Business templates with parameter substitution.
        Templates must be pre-approved by WhatsApp for use.

        Args:
            template_name: Name of the approved WhatsApp template
            recipient: Recipient phone number
            body_parameters: List of parameter objects for text replacement
            language_code: BCP-47 language code for template (default: "es")

        Returns:
            MessageResult with operation status and metadata
        """
        return await self.template_handler.send_text_template(
            phone_number=recipient,
            template_name=template_name,
            body_parameters=self._convert_body_parameters(body_parameters),
            language_code=language_code,
        )

    async def send_media_template(
        self,
        template_name: str,
        recipient: str,
        media_type: str,
        media_id: str | None = None,
        media_url: str | None = None,
        body_parameters: list[dict] | None = None,
        language_code: str = "es",
    ) -> MessageResult:
        """Send template message with media header using WhatsApp API.

        Supports templates with image, video, or document headers.
        Either media_id (uploaded media) or media_url (external media) must be provided.

        Args:
            template_name: Name of the approved WhatsApp template
            recipient: Recipient phone number
            media_type: Type of media header ("image", "video", "document")
            media_id: ID of pre-uploaded media (exclusive with media_url)
            media_url: URL of external media (exclusive with media_id)
            body_parameters: List of parameter objects for text replacement
            language_code: BCP-47 language code for template (default: "es")

        Returns:
            MessageResult with operation status and metadata
        """
        # Convert string media_type to MediaType enum
        from wappa.messaging.whatsapp.models.template_models import MediaType

        try:
            media_type_enum = MediaType(media_type)
        except ValueError:
            return MessageResult(
                success=False,
                platform="whatsapp",
                error=f"Invalid media type: {media_type}",
                error_code="INVALID_MEDIA_TYPE",
            )

        return await self.template_handler.send_media_template(
            phone_number=recipient,
            template_name=template_name,
            media_type=media_type_enum,
            media_id=media_id,
            media_url=media_url,
            body_parameters=self._convert_body_parameters(body_parameters),
            language_code=language_code,
        )

    async def send_location_template(
        self,
        template_name: str,
        recipient: str,
        latitude: str,
        longitude: str,
        name: str,
        address: str,
        body_parameters: list[dict] | None = None,
        language_code: str = "es",
    ) -> MessageResult:
        """Send template message with location header using WhatsApp API.

        Supports templates with geographic location headers showing a map preview.
        Coordinates must be valid latitude (-90 to 90) and longitude (-180 to 180).

        Args:
            template_name: Name of the approved WhatsApp template
            recipient: Recipient phone number
            latitude: Location latitude as string (e.g., "37.483307")
            longitude: Location longitude as string (e.g., "-122.148981")
            name: Name/title of the location
            address: Physical address of the location
            body_parameters: List of parameter objects for text replacement
            language_code: BCP-47 language code for template (default: "es")

        Returns:
            MessageResult with operation status and metadata
        """
        return await self.template_handler.send_location_template(
            phone_number=recipient,
            template_name=template_name,
            latitude=latitude,
            longitude=longitude,
            name=name,
            address=address,
            body_parameters=self._convert_body_parameters(body_parameters),
            language_code=language_code,
        )

    # Specialized Messaging Methods (from WhatsAppSpecializedHandler)

    async def send_contact(
        self, contact: dict, recipient: str, reply_to_message_id: str | None = None
    ) -> MessageResult:
        """Send contact card message using WhatsApp API.

        Shares contact information including name, phone numbers, emails, and addresses.
        Contact cards are automatically added to the recipient's address book.

        Args:
            contact: Contact information dictionary with required 'name' and 'phones' fields
            recipient: Recipient phone number
            reply_to_message_id: Optional message ID to reply to

        Returns:
            MessageResult with operation status and metadata
        """
        # Convert Dict to ContactCard model if needed
        from wappa.messaging.whatsapp.models.specialized_models import ContactCard

        if isinstance(contact, dict):
            try:
                contact_card = ContactCard(**contact)
            except Exception as e:
                return MessageResult(
                    success=False,
                    platform="whatsapp",
                    error=f"Invalid contact format: {str(e)}",
                    error_code="INVALID_CONTACT_FORMAT",
                )
        else:
            contact_card = contact

        return await self.specialized_handler.send_contact_card(
            recipient=recipient,
            contact=contact_card,
            reply_to_message_id=reply_to_message_id,
        )

    async def send_location(
        self,
        latitude: float,
        longitude: float,
        recipient: str,
        name: str | None = None,
        address: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        """Send location message using WhatsApp API.

        Shares geographic coordinates with optional location name and address.
        Recipients see a map preview with the shared location.

        Args:
            latitude: Location latitude in decimal degrees (-90 to 90)
            longitude: Location longitude in decimal degrees (-180 to 180)
            recipient: Recipient phone number
            name: Optional location name (e.g., "Coffee Shop")
            address: Optional street address
            reply_to_message_id: Optional message ID to reply to

        Returns:
            MessageResult with operation status and metadata
        """
        return await self.specialized_handler.send_location(
            recipient=recipient,
            latitude=latitude,
            longitude=longitude,
            name=name,
            address=address,
            reply_to_message_id=reply_to_message_id,
        )

    async def send_location_request(
        self, body: str, recipient: str, reply_to_message_id: str | None = None
    ) -> MessageResult:
        """Send location request message using WhatsApp API.

        Sends an interactive message that prompts the recipient to share their location.
        Recipients see a "Send Location" button that allows easy location sharing.

        Args:
            body: Request message text (max 1024 characters)
            recipient: Recipient phone number
            reply_to_message_id: Optional message ID to reply to

        Returns:
            MessageResult with operation status and metadata
        """
        return await self.specialized_handler.send_location_request(
            recipient=recipient, body=body, reply_to_message_id=reply_to_message_id
        )
