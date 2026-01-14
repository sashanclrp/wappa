"""
Messaging interface for platform-agnostic communication.

This interface defines the contract for messaging operations that can be
implemented across different messaging platforms (WhatsApp, Telegram, Teams, etc.).

Implements messaging operations:
- Basic messaging (send_text, mark_as_read)
- Media messaging (send_image, send_video, send_audio, send_document, send_sticker)
- Interactive messaging (send_button_message, send_list_message, send_cta_message)
- Template messaging (send_text_template, send_media_template, send_location_template)

Implements specialized messaging:
- Specialized messaging (send_contact, send_location, send_location_request)
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

from wappa.schemas.core.types import PlatformType

if TYPE_CHECKING:
    from wappa.messaging.whatsapp.models.basic_models import MessageResult


class IMessenger(ABC):
    """
    Messaging interface for platform-agnostic communication.

    Provides messaging operations:
    - Basic messaging: send_text, mark_as_read
    - Media messaging: send_image, send_video, send_audio, send_document, send_sticker
    - Interactive messaging: send_button_message, send_list_message, send_cta_message
    - Template messaging: send_text_template, send_media_template, send_location_template

    Specialized messaging:
    - Specialized messaging: send_contact, send_location, send_location_request

    Key Design Decisions:
    - tenant_id property provides the platform-specific tenant identifier
    - All methods return MessageResult for consistent response handling
    - Supports typing indicator in mark_as_read as specifically requested
    - Media methods support both URLs and file paths for flexibility
    """

    @property
    @abstractmethod
    def platform(self) -> PlatformType:
        """Get the platform this messenger handles.

        Returns:
            PlatformType enum value (e.g., WHATSAPP, TELEGRAM, TEAMS)
        """
        pass

    @property
    @abstractmethod
    def tenant_id(self) -> str:
        """Get the tenant ID this messenger serves.

        Note: In WhatsApp context, this is the phone_number_id.
        Different platforms may use different tenant identifiers.

        Returns:
            Platform-specific tenant identifier
        """
        pass

    @abstractmethod
    async def send_text(
        self,
        text: str,
        recipient: str,
        reply_to_message_id: str | None = None,
        disable_preview: bool = False,
    ) -> "MessageResult":
        """Send a text message.

        Args:
            text: Text content of the message (1-4096 characters)
            recipient: Recipient identifier (phone number, user ID, etc.)
            reply_to_message_id: Optional message ID to reply to (creates thread)
            disable_preview: Whether to disable URL preview for links

        Returns:
            MessageResult with operation status and metadata

        Raises:
            Platform-specific exceptions for API failures
        """
        pass

    @abstractmethod
    async def mark_as_read(
        self, message_id: str, typing: bool = False
    ) -> "MessageResult":
        """Mark a message as read, optionally with typing indicator.

        Key requirement: Support for typing indicator boolean parameter.
        When typing=True, shows typing indicator to the sender.

        Args:
            message_id: Platform-specific message identifier to mark as read
            typing: Whether to show typing indicator when marking as read

        Returns:
            MessageResult with operation status and metadata

        Raises:
            Platform-specific exceptions for API failures
        """
        pass

    # Media Messaging Methods
    @abstractmethod
    async def send_image(
        self,
        image_source: str | Path,
        recipient: str,
        caption: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> "MessageResult":
        """Send an image message.

        Supports JPEG and PNG images up to 5MB.
        Images must be 8-bit, RGB or RGBA (WhatsApp Cloud API 2025).

        Args:
            image_source: Image URL or file path
            recipient: Recipient identifier
            caption: Optional caption for the image (max 1024 characters)
            reply_to_message_id: Optional message ID to reply to

        Returns:
            MessageResult with operation status and metadata

        Raises:
            Platform-specific exceptions for API failures
        """
        pass

    @abstractmethod
    async def send_video(
        self,
        video_source: str | Path,
        recipient: str,
        caption: str | None = None,
        reply_to_message_id: str | None = None,
        transcript: str | None = None,
    ) -> "MessageResult":
        """Send a video message.

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

        Raises:
            Platform-specific exceptions for API failures
        """
        pass

    @abstractmethod
    async def send_audio(
        self,
        audio_source: str | Path,
        recipient: str,
        reply_to_message_id: str | None = None,
        transcript: str | None = None,
    ) -> "MessageResult":
        """Send an audio message.

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

        Raises:
            Platform-specific exceptions for API failures
        """
        pass

    @abstractmethod
    async def send_document(
        self,
        document_source: str | Path,
        recipient: str,
        filename: str | None = None,
        caption: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> "MessageResult":
        """Send a document message.

        Supports TXT, PDF, DOC, DOCX, XLS, XLSX, PPT, PPTX up to 100MB.

        Args:
            document_source: Document URL or file path
            recipient: Recipient identifier
            filename: Optional filename for the document
            caption: Optional caption for the document (max 1024 characters)
            reply_to_message_id: Optional message ID to reply to

        Returns:
            MessageResult with operation status and metadata

        Raises:
            Platform-specific exceptions for API failures
        """
        pass

    @abstractmethod
    async def send_sticker(
        self,
        sticker_source: str | Path,
        recipient: str,
        reply_to_message_id: str | None = None,
    ) -> "MessageResult":
        """Send a sticker message.

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

        Raises:
            Platform-specific exceptions for API failures
        """
        pass

    # Interactive Messaging Methods
    @abstractmethod
    async def send_button_message(
        self,
        buttons: list[dict[str, str]],
        recipient: str,
        body: str,
        header: dict | None = None,
        footer: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> "MessageResult":
        """Send an interactive button message.

        Supports up to 3 quick reply buttons with optional header and footer.
        Based on WhatsApp Cloud API 2025 interactive button specifications.

        Args:
            buttons: List of button objects with 'id' and 'title' keys (max 3 buttons)
            recipient: Recipient identifier
            body: Main message text (max 1024 characters)
            header: Optional header content with type and content
            footer: Optional footer text (max 60 characters)
            reply_to_message_id: Optional message ID to reply to

        Returns:
            MessageResult with operation status and metadata

        Raises:
            Platform-specific exceptions for API failures
        """
        pass

    @abstractmethod
    async def send_list_message(
        self,
        sections: list[dict],
        recipient: str,
        body: str,
        button_text: str,
        header: str | None = None,
        footer: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> "MessageResult":
        """Send an interactive list message.

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

        Raises:
            Platform-specific exceptions for API failures
        """
        pass

    @abstractmethod
    async def send_cta_message(
        self,
        button_text: str,
        button_url: str,
        recipient: str,
        body: str,
        header: str | None = None,
        footer: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> "MessageResult":
        """Send an interactive call-to-action URL button message.

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

        Raises:
            Platform-specific exceptions for API failures
        """
        pass

    # Template Messaging Methods
    @abstractmethod
    async def send_text_template(
        self,
        template_name: str,
        recipient: str,
        body_parameters: list[dict] | None = None,
        language_code: str = "es",
    ) -> "MessageResult":
        """Send a text-only template message.

        Supports WhatsApp Business templates with parameter substitution.
        Templates must be pre-approved by WhatsApp for use.

        Args:
            template_name: Name of the approved WhatsApp template
            recipient: Recipient identifier
            body_parameters: List of parameter objects for text replacement
            language_code: BCP-47 language code for template (default: "es")

        Returns:
            MessageResult with operation status and metadata

        Raises:
            Platform-specific exceptions for API failures
        """
        pass

    @abstractmethod
    async def send_media_template(
        self,
        template_name: str,
        recipient: str,
        media_type: str,
        media_id: str | None = None,
        media_url: str | None = None,
        body_parameters: list[dict] | None = None,
        language_code: str = "es",
    ) -> "MessageResult":
        """Send a template message with media header.

        Supports templates with image, video, or document headers.
        Either media_id (uploaded media) or media_url (external media) must be provided.

        Args:
            template_name: Name of the approved WhatsApp template
            recipient: Recipient identifier
            media_type: Type of media header ("image", "video", "document")
            media_id: ID of pre-uploaded media (exclusive with media_url)
            media_url: URL of external media (exclusive with media_id)
            body_parameters: List of parameter objects for text replacement
            language_code: BCP-47 language code for template (default: "es")

        Returns:
            MessageResult with operation status and metadata

        Raises:
            Platform-specific exceptions for API failures
        """
        pass

    @abstractmethod
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
    ) -> "MessageResult":
        """Send a template message with location header.

        Supports templates with geographic location headers showing a map preview.
        Coordinates must be valid latitude (-90 to 90) and longitude (-180 to 180).

        Args:
            template_name: Name of the approved WhatsApp template
            recipient: Recipient identifier
            latitude: Location latitude as string (e.g., "37.483307")
            longitude: Location longitude as string (e.g., "-122.148981")
            name: Name/title of the location
            address: Physical address of the location
            body_parameters: List of parameter objects for text replacement
            language_code: BCP-47 language code for template (default: "es")

        Returns:
            MessageResult with operation status and metadata

        Raises:
            Platform-specific exceptions for API failures
        """
        pass

    # Specialized Messaging Methods
    @abstractmethod
    async def send_contact(
        self, contact: dict, recipient: str, reply_to_message_id: str | None = None
    ) -> "MessageResult":
        """Send a contact card message.

        Shares contact information including name, phone numbers, emails, and addresses.
        Contact cards are automatically added to the recipient's address book.

        Args:
            contact: Contact information dictionary with required 'name' and 'phones' fields
            recipient: Recipient identifier
            reply_to_message_id: Optional message ID to reply to

        Returns:
            MessageResult with operation status and metadata

        Raises:
            Platform-specific exceptions for API failures
        """
        pass

    @abstractmethod
    async def send_location(
        self,
        latitude: float,
        longitude: float,
        recipient: str,
        name: str | None = None,
        address: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> "MessageResult":
        """Send a location message.

        Shares geographic coordinates with optional location name and address.
        Recipients see a map preview with the shared location.

        Args:
            latitude: Location latitude in decimal degrees (-90 to 90)
            longitude: Location longitude in decimal degrees (-180 to 180)
            recipient: Recipient identifier
            name: Optional location name (e.g., "Coffee Shop")
            address: Optional street address
            reply_to_message_id: Optional message ID to reply to

        Returns:
            MessageResult with operation status and metadata

        Raises:
            Platform-specific exceptions for API failures
        """
        pass

    @abstractmethod
    async def send_location_request(
        self, body: str, recipient: str, reply_to_message_id: str | None = None
    ) -> "MessageResult":
        """Send a location request message.

        Sends an interactive message that prompts the recipient to share their location.
        Recipients see a "Send Location" button that allows easy location sharing.

        Args:
            body: Request message text (max 1024 characters)
            recipient: Recipient identifier
            reply_to_message_id: Optional message ID to reply to

        Returns:
            MessageResult with operation status and metadata

        Raises:
            Platform-specific exceptions for API failures
        """
        pass
