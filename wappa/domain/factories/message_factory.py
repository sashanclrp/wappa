"""
Message factory pattern for creating platform-specific message objects.

This factory creates properly formatted message objects that can be sent through
the IMessenger interface while maintaining platform compatibility and type safety.
"""

from abc import ABC, abstractmethod
from typing import Any

from wappa.schemas.core.types import PlatformType


class MessageFactory(ABC):
    """
    Abstract factory for creating platform-specific message objects.

    This factory creates properly formatted message objects that can be
    sent through the IMessenger interface while maintaining platform
    compatibility and type safety.

    Supports messaging operations:
    - Basic messages (create_text_message, create_read_status_message)
    - Media messages (create_image_message, create_video_message, etc.)

    Future implementations will add:
    - Interactive messages (create_button_message, create_list_message, etc.)
    - Specialized messages (create_contact_message, create_location_message, etc.)
    """

    @property
    @abstractmethod
    def platform(self) -> PlatformType:
        """Get the platform this factory creates messages for."""
        pass

    # Basic Messages
    @abstractmethod
    def create_text_message(
        self,
        text: str,
        recipient: str,
        reply_to_message_id: str | None = None,
        disable_preview: bool = False,
    ) -> dict[str, Any]:
        """Create a text message payload.

        Args:
            text: Text content of the message
            recipient: Recipient identifier
            reply_to_message_id: Optional message ID to reply to
            disable_preview: Whether to disable URL preview

        Returns:
            Platform-specific message payload
        """
        pass

    @abstractmethod
    def create_read_status_message(
        self, message_id: str, typing: bool = False
    ) -> dict[str, Any]:
        """Create a read status message payload.

        Args:
            message_id: Message ID to mark as read
            typing: Whether to show typing indicator

        Returns:
            Platform-specific read status payload
        """
        pass

    # Media Messages
    @abstractmethod
    def create_image_message(
        self,
        media_reference: str,
        recipient: str,
        caption: str | None = None,
        reply_to_message_id: str | None = None,
        is_url: bool = False,
    ) -> dict[str, Any]:
        """Create an image message payload.

        Args:
            media_reference: Media ID or URL
            recipient: Recipient identifier
            caption: Optional caption for the image
            reply_to_message_id: Optional message ID to reply to
            is_url: Whether media_reference is a URL (True) or media ID (False)

        Returns:
            Platform-specific image message payload
        """
        pass

    @abstractmethod
    def create_video_message(
        self,
        media_reference: str,
        recipient: str,
        caption: str | None = None,
        reply_to_message_id: str | None = None,
        is_url: bool = False,
    ) -> dict[str, Any]:
        """Create a video message payload.

        Args:
            media_reference: Media ID or URL
            recipient: Recipient identifier
            caption: Optional caption for the video
            reply_to_message_id: Optional message ID to reply to
            is_url: Whether media_reference is a URL (True) or media ID (False)

        Returns:
            Platform-specific video message payload
        """
        pass

    @abstractmethod
    def create_audio_message(
        self,
        media_reference: str,
        recipient: str,
        reply_to_message_id: str | None = None,
        is_url: bool = False,
    ) -> dict[str, Any]:
        """Create an audio message payload.

        Args:
            media_reference: Media ID or URL
            recipient: Recipient identifier
            reply_to_message_id: Optional message ID to reply to
            is_url: Whether media_reference is a URL (True) or media ID (False)

        Returns:
            Platform-specific audio message payload
        """
        pass

    @abstractmethod
    def create_document_message(
        self,
        media_reference: str,
        recipient: str,
        filename: str | None = None,
        reply_to_message_id: str | None = None,
        is_url: bool = False,
    ) -> dict[str, Any]:
        """Create a document message payload.

        Args:
            media_reference: Media ID or URL
            recipient: Recipient identifier
            filename: Optional filename for the document
            reply_to_message_id: Optional message ID to reply to
            is_url: Whether media_reference is a URL (True) or media ID (False)

        Returns:
            Platform-specific document message payload
        """
        pass

    @abstractmethod
    def create_sticker_message(
        self,
        media_reference: str,
        recipient: str,
        reply_to_message_id: str | None = None,
        is_url: bool = False,
    ) -> dict[str, Any]:
        """Create a sticker message payload.

        Args:
            media_reference: Media ID or URL
            recipient: Recipient identifier
            reply_to_message_id: Optional message ID to reply to
            is_url: Whether media_reference is a URL (True) or media ID (False)

        Returns:
            Platform-specific sticker message payload
        """
        pass

    # Validation
    @abstractmethod
    def validate_message(self, message_payload: dict[str, Any]) -> bool:
        """Validate message payload against platform constraints.

        Args:
            message_payload: Message payload to validate

        Returns:
            True if payload is valid, False otherwise
        """
        pass

    @abstractmethod
    def get_message_limits(self) -> dict[str, Any]:
        """Get platform-specific text message limits.

        Returns only text message limits. For other domain limits, use:
        - MediaFactory.get_media_limits() for media limits
        - Interactive endpoint for interactive message limits
        - Templates endpoint for template limits

        Returns:
            Dictionary containing text message limits (max lengths, etc.)
        """
        pass


class WhatsAppMessageFactory(MessageFactory):
    """WhatsApp implementation of the message factory."""

    @property
    def platform(self) -> PlatformType:
        """Get the platform this factory creates messages for."""
        return PlatformType.WHATSAPP

    def create_text_message(
        self,
        text: str,
        recipient: str,
        reply_to_message_id: str | None = None,
        disable_preview: bool = False,
    ) -> dict[str, Any]:
        """Create WhatsApp text message payload.

        Creates properly formatted WhatsApp Business API payload for text messages
        with support for URL preview control and reply context.
        """
        # Check for URLs for preview control
        has_url = "http://" in text or "https://" in text

        payload = {
            "messaging_product": "whatsapp",
            "to": recipient,
            "type": "text",
            "text": {"body": text, "preview_url": has_url and not disable_preview},
        }

        # Add reply context if specified
        if reply_to_message_id:
            payload["context"] = {"message_id": reply_to_message_id}

        return payload

    def create_read_status_message(
        self, message_id: str, typing: bool = False
    ) -> dict[str, Any]:
        """Create WhatsApp read status payload with typing support.

        Creates WhatsApp Business API payload for marking messages as read
        with optional typing indicator support.
        """
        payload = {
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": message_id,
        }

        # Add typing indicator if requested (key requirement)
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
        """Create WhatsApp image message payload."""
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient,
            "type": "image",
        }

        # Create media object based on reference type
        media_obj = {"link": media_reference} if is_url else {"id": media_reference}

        # Add optional caption
        if caption:
            media_obj["caption"] = caption

        payload["image"] = media_obj

        # Add reply context if specified
        if reply_to_message_id:
            payload["context"] = {"message_id": reply_to_message_id}

        return payload

    def create_video_message(
        self,
        media_reference: str,
        recipient: str,
        caption: str | None = None,
        reply_to_message_id: str | None = None,
        is_url: bool = False,
    ) -> dict[str, Any]:
        """Create WhatsApp video message payload."""
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient,
            "type": "video",
        }

        # Create media object based on reference type
        media_obj = {"link": media_reference} if is_url else {"id": media_reference}

        # Add optional caption
        if caption:
            media_obj["caption"] = caption

        payload["video"] = media_obj

        # Add reply context if specified
        if reply_to_message_id:
            payload["context"] = {"message_id": reply_to_message_id}

        return payload

    def create_audio_message(
        self,
        media_reference: str,
        recipient: str,
        reply_to_message_id: str | None = None,
        is_url: bool = False,
    ) -> dict[str, Any]:
        """Create WhatsApp audio message payload."""
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient,
            "type": "audio",
        }

        # Create media object based on reference type
        media_obj = {"link": media_reference} if is_url else {"id": media_reference}

        payload["audio"] = media_obj

        # Add reply context if specified
        if reply_to_message_id:
            payload["context"] = {"message_id": reply_to_message_id}

        return payload

    def create_document_message(
        self,
        media_reference: str,
        recipient: str,
        filename: str | None = None,
        reply_to_message_id: str | None = None,
        is_url: bool = False,
    ) -> dict[str, Any]:
        """Create WhatsApp document message payload."""
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient,
            "type": "document",
        }

        # Create media object based on reference type
        media_obj = {"link": media_reference} if is_url else {"id": media_reference}

        # Add optional filename
        if filename:
            media_obj["filename"] = filename

        payload["document"] = media_obj

        # Add reply context if specified
        if reply_to_message_id:
            payload["context"] = {"message_id": reply_to_message_id}

        return payload

    def create_sticker_message(
        self,
        media_reference: str,
        recipient: str,
        reply_to_message_id: str | None = None,
        is_url: bool = False,
    ) -> dict[str, Any]:
        """Create WhatsApp sticker message payload."""
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient,
            "type": "sticker",
        }

        # Create media object based on reference type
        media_obj = {"link": media_reference} if is_url else {"id": media_reference}

        payload["sticker"] = media_obj

        # Add reply context if specified
        if reply_to_message_id:
            payload["context"] = {"message_id": reply_to_message_id}

        return payload

    def validate_message(self, message_payload: dict[str, Any]) -> bool:
        """Validate WhatsApp message payload.

        Performs basic validation against WhatsApp Business API requirements.
        """
        try:
            # Check required fields
            if "messaging_product" not in message_payload:
                return False
            if message_payload["messaging_product"] != "whatsapp":
                return False
            if "to" not in message_payload:
                return False

            # Validate text messages
            if message_payload.get("type") == "text":
                if "text" not in message_payload:
                    return False
                if "body" not in message_payload["text"]:
                    return False
                if len(message_payload["text"]["body"]) > 4096:
                    return False

            # Validate read status messages
            if "status" in message_payload:
                if message_payload["status"] == "read":
                    if "message_id" not in message_payload:
                        return False

            return True

        except (KeyError, TypeError):
            return False

    def get_message_limits(self) -> dict[str, Any]:
        """Get WhatsApp-specific text message limits.

        Returns current WhatsApp Business API limits for text message validation.
        Note: For media limits, use MediaFactory.get_media_limits().
              For interactive limits, see /api/whatsapp/interactive/limits.
              For template limits, see /api/whatsapp/templates/limits.
        """
        return {
            "max_text_length": 4096,
            "max_preview_url_text_length": 4096,
            "max_recipient_phone_length": 20,
        }
