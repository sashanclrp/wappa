"""
Media factory pattern for creating platform-specific media message objects.

This factory creates properly formatted media message objects based on
existing payload generation logic from whatsapp_latest/services/handle_media.py.
"""

from abc import ABC, abstractmethod
from typing import Any

from wappa.schemas.core.types import PlatformType


class MediaFactory(ABC):
    """
    Abstract factory for creating platform-specific media message objects.

    This factory creates properly formatted media message objects that can be
    sent through the IMessenger interface while maintaining platform
    compatibility and type safety.

    Based on existing payload generation patterns from handle_media.py.
    """

    @property
    @abstractmethod
    def platform(self) -> PlatformType:
        """Get the platform this factory creates messages for."""
        pass

    # Media Message Creation Methods
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

    # Validation Methods
    @abstractmethod
    def validate_media_message(self, message_payload: dict[str, Any]) -> bool:
        """Validate media message payload against platform constraints.

        Args:
            message_payload: Media message payload to validate

        Returns:
            True if payload is valid, False otherwise
        """
        pass

    @abstractmethod
    def get_media_limits(self) -> dict[str, Any]:
        """Get platform-specific media limits.

        Returns:
            Dictionary containing platform-specific media limits
        """
        pass


class WhatsAppMediaFactory(MediaFactory):
    """WhatsApp implementation of the media factory.

    Based on existing payload generation patterns from
    whatsapp_latest/services/handle_media.py send_media() method.
    """

    @property
    def platform(self) -> PlatformType:
        """Get the platform this factory creates messages for."""
        return PlatformType.WHATSAPP

    def create_image_message(
        self,
        media_reference: str,
        recipient: str,
        caption: str | None = None,
        reply_to_message_id: str | None = None,
        is_url: bool = False,
    ) -> dict[str, Any]:
        """Create WhatsApp image message payload.

        Based on existing send_media() logic for MediaType.IMAGE.
        """
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
        """Create WhatsApp video message payload.

        Based on existing send_media() logic for MediaType.VIDEO.
        """
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
        """Create WhatsApp audio message payload.

        Based on existing send_media() logic for MediaType.AUDIO.
        Note: Audio messages do not support captions.
        """
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
        """Create WhatsApp document message payload.

        Based on existing send_media() logic for MediaType.DOCUMENT.
        """
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
        """Create WhatsApp sticker message payload.

        Based on existing send_media() logic for MediaType.STICKER.
        Note: Sticker messages do not support captions.
        """
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

    def validate_media_message(self, message_payload: dict[str, Any]) -> bool:
        """Validate WhatsApp media message payload.

        Performs validation against WhatsApp Business API requirements.
        """
        try:
            # Check required fields
            if "messaging_product" not in message_payload:
                return False
            if message_payload["messaging_product"] != "whatsapp":
                return False
            if "to" not in message_payload:
                return False
            if "type" not in message_payload:
                return False

            message_type = message_payload["type"]
            valid_types = ["image", "video", "audio", "document", "sticker"]
            if message_type not in valid_types:
                return False

            # Check that media object exists
            if message_type not in message_payload:
                return False

            media_obj = message_payload[message_type]

            # Must have either 'id' or 'link'
            if "id" not in media_obj and "link" not in media_obj:
                return False

            # Validate caption length if present
            if "caption" in media_obj:
                if len(media_obj["caption"]) > 1024:
                    return False
                # Caption not allowed for audio and sticker
                if message_type in ["audio", "sticker"]:
                    return False

            return True

        except (KeyError, TypeError):
            return False

    def get_media_limits(self) -> dict[str, Any]:
        """Get WhatsApp-specific media limits.

        Based on existing MediaType.get_max_file_size() and supported types.
        """
        return {
            "max_caption_length": 1024,
            "max_filename_length": 255,
            "supported_media_types": {
                "image": ["image/jpeg", "image/png"],
                "video": ["video/mp4", "video/3gpp"],
                "audio": [
                    "audio/aac",
                    "audio/amr",
                    "audio/mpeg",
                    "audio/mp4",
                    "audio/ogg",
                ],
                "document": [
                    "text/plain",
                    "application/pdf",
                    "application/vnd.ms-powerpoint",
                    "application/msword",
                    "application/vnd.ms-excel",
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ],
                "sticker": ["image/webp"],
            },
            "max_file_sizes": {
                "image": 5 * 1024 * 1024,  # 5MB
                "video": 16 * 1024 * 1024,  # 16MB
                "audio": 16 * 1024 * 1024,  # 16MB
                "document": 100 * 1024 * 1024,  # 100MB
                "sticker": 500 * 1024,  # 500KB (animated), 100KB (static)
            },
            "caption_support": {
                "image": True,
                "video": True,
                "audio": False,
                "document": False,  # Uses filename instead
                "sticker": False,
            },
            "filename_support": {
                "document": True,
                "image": False,
                "video": False,
                "audio": False,
                "sticker": False,
            },
        }
