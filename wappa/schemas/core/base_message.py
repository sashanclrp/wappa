"""
Base message abstractions for platform-agnostic message handling.

This module defines the abstract base classes for different message types
that provide consistent interfaces regardless of the messaging platform.
"""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .types import (
    ConversationType,
    InteractiveType,
    MediaType,
    MessageType,
    PlatformType,
    UniversalMessageData,
)


class BaseMessageContext(BaseModel, ABC):
    """
    Platform-agnostic message context base class.

    Represents context information for replies, forwards, and threaded messages.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @property
    @abstractmethod
    def original_message_id(self) -> str | None:
        """Get the ID of the original message being replied to or forwarded."""
        pass

    @property
    @abstractmethod
    def original_sender_id(self) -> str | None:
        """Get the sender ID of the original message."""
        pass

    @property
    @abstractmethod
    def is_reply(self) -> bool:
        """Check if this represents a reply context."""
        pass

    @property
    @abstractmethod
    def is_forward(self) -> bool:
        """Check if this represents a forward context."""
        pass

    @abstractmethod
    def to_universal_dict(self) -> dict[str, Any]:
        """Convert to platform-agnostic dictionary representation."""
        pass


class BaseMessage(BaseModel, ABC):
    """
    Platform-agnostic message base class.

    All platform-specific message models must inherit from this class
    to provide a consistent interface for message processing.
    """

    model_config = ConfigDict(
        extra="forbid", str_strip_whitespace=True, validate_assignment=True
    )

    # Universal fields
    processed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When the message was processed by our system",
    )

    @property
    @abstractmethod
    def platform(self) -> PlatformType:
        """Get the platform this message came from."""
        pass

    @property
    @abstractmethod
    def message_type(self) -> MessageType:
        """Get the universal message type."""
        pass

    @property
    @abstractmethod
    def message_id(self) -> str:
        """Get the unique message identifier."""
        pass

    @property
    @abstractmethod
    def sender_id(self) -> str:
        """Get the sender's universal identifier."""
        pass

    @property
    @abstractmethod
    def timestamp(self) -> int:
        """Get the message timestamp as Unix timestamp."""
        pass

    @property
    @abstractmethod
    def conversation_id(self) -> str:
        """Get the conversation/chat identifier."""
        pass

    @property
    def conversation_type(self) -> ConversationType:
        """Get the type of conversation (private, group, channel)."""
        return ConversationType.PRIVATE  # Default implementation

    @abstractmethod
    def has_context(self) -> bool:
        """Check if this message has context (reply, forward, etc.)."""
        pass

    @abstractmethod
    def get_context(self) -> BaseMessageContext | None:
        """Get message context if available."""
        pass

    @abstractmethod
    def to_universal_dict(self) -> UniversalMessageData:
        """
        Convert to platform-agnostic dictionary representation.

        This method should return a standardized dictionary structure
        that can be used across all platforms for Symphony AI processing.
        """
        pass

    @abstractmethod
    def get_platform_data(self) -> dict[str, Any]:
        """
        Get platform-specific data for advanced processing.

        This returns platform-specific fields that don't have
        universal equivalents but may be needed for specialized logic.
        """
        pass

    def get_message_summary(self) -> dict[str, Any]:
        """
        Get a summary of the message for logging and analytics.

        Returns:
            Dictionary with key message information.
        """
        return {
            "message_id": self.message_id,
            "platform": self.platform.value,
            "message_type": self.message_type.value,
            "sender_id": self.sender_id,
            "conversation_id": self.conversation_id,
            "conversation_type": self.conversation_type.value,
            "timestamp": self.timestamp,
            "processed_at": self.processed_at.isoformat(),
            "has_context": self.has_context(),
        }

    @classmethod
    @abstractmethod
    def from_platform_data(cls, data: dict[str, Any], **kwargs) -> "BaseMessage":
        """
        Create message instance from platform-specific data.

        Args:
            data: Raw message data from platform webhook
            **kwargs: Additional platform-specific parameters

        Returns:
            Validated message instance
        """
        pass


class BaseTextMessage(BaseMessage):
    """
    Platform-agnostic text message base class.

    Handles text content with universal methods for common operations.
    """

    @property
    def message_type(self) -> MessageType:
        """Text messages always have TEXT type."""
        return MessageType.TEXT

    @property
    @abstractmethod
    def text_content(self) -> str:
        """Get the text content of the message."""
        pass

    @property
    @abstractmethod
    def is_reply(self) -> bool:
        """Check if this is a reply to another message."""
        pass

    @property
    @abstractmethod
    def is_forwarded(self) -> bool:
        """Check if this message was forwarded."""
        pass

    @property
    def is_frequently_forwarded(self) -> bool:
        """Check if this message was forwarded many times."""
        return False  # Default implementation

    @abstractmethod
    def get_reply_context(self) -> tuple[str | None, str | None]:
        """
        Get reply context information.

        Returns:
            Tuple of (original_sender_id, original_message_id) if reply,
            (None, None) otherwise.
        """
        pass

    def get_text_length(self) -> int:
        """Get the length of the text content."""
        return len(self.text_content)

    def contains_keyword(self, keyword: str, case_sensitive: bool = False) -> bool:
        """Check if text content contains a specific keyword."""
        text = self.text_content
        search_text = text if case_sensitive else text.lower()
        search_keyword = keyword if case_sensitive else keyword.lower()
        return search_keyword in search_text

    def contains_any_keyword(
        self, keywords: list[str], case_sensitive: bool = False
    ) -> bool:
        """Check if text content contains any of the specified keywords."""
        return any(self.contains_keyword(kw, case_sensitive) for kw in keywords)


class BaseInteractiveMessage(BaseMessage):
    """
    Platform-agnostic interactive message base class.

    Handles button clicks, list selections, and other interactive elements.
    """

    @property
    def message_type(self) -> MessageType:
        """Interactive messages always have INTERACTIVE type."""
        return MessageType.INTERACTIVE

    @property
    @abstractmethod
    def interactive_type(self) -> InteractiveType:
        """Get the type of interactive element (button, list, etc.)."""
        pass

    @property
    @abstractmethod
    def selected_option_id(self) -> str:
        """Get the ID of the selected option."""
        pass

    @property
    @abstractmethod
    def selected_option_title(self) -> str:
        """Get the title/text of the selected option."""
        pass

    @property
    @abstractmethod
    def original_message_id(self) -> str:
        """Get the ID of the original interactive message."""
        pass

    @abstractmethod
    def is_button_reply(self) -> bool:
        """Check if this is a button selection."""
        pass

    @abstractmethod
    def is_list_reply(self) -> bool:
        """Check if this is a list selection."""
        pass

    def matches_option_pattern(self, pattern: str) -> bool:
        """Check if selected option ID matches a pattern (e.g., starts with prefix)."""
        return self.selected_option_id.startswith(pattern)

    def get_option_category(self, delimiter: str = "_") -> str | None:
        """Extract option category from ID using delimiter."""
        parts = self.selected_option_id.split(delimiter)
        return parts[0] if len(parts) > 1 else None


class BaseMediaMessage(BaseMessage):
    """
    Platform-agnostic media message base class.

    Handles images, audio, video, and document messages.
    """

    @property
    @abstractmethod
    def media_id(self) -> str:
        """Get the platform-specific media identifier."""
        pass

    @property
    @abstractmethod
    def media_type(self) -> MediaType:
        """Get the media MIME type."""
        pass

    @property
    @abstractmethod
    def file_size(self) -> int | None:
        """Get the file size in bytes if available."""
        pass

    @property
    @abstractmethod
    def caption(self) -> str | None:
        """Get the media caption/description if available."""
        pass

    @abstractmethod
    def get_download_info(self) -> dict[str, Any]:
        """
        Get information needed to download the media file.

        Returns:
            Dictionary with download URL, headers, or other platform-specific info.
        """
        pass

    def has_caption(self) -> bool:
        """Check if the media has a caption."""
        caption = self.caption
        return caption is not None and len(caption.strip()) > 0

    def is_image(self) -> bool:
        """Check if this is an image message."""
        return self.message_type == MessageType.IMAGE

    def is_audio(self) -> bool:
        """Check if this is an audio message."""
        return self.message_type == MessageType.AUDIO

    def is_video(self) -> bool:
        """Check if this is a video message."""
        return self.message_type == MessageType.VIDEO

    def is_document(self) -> bool:
        """Check if this is a document message."""
        return self.message_type == MessageType.DOCUMENT


class BaseImageMessage(BaseMediaMessage):
    """Platform-agnostic image message base class."""

    @property
    def message_type(self) -> MessageType:
        """Image messages always have IMAGE type."""
        return MessageType.IMAGE


class BaseAudioMessage(BaseMediaMessage):
    """Platform-agnostic audio message base class."""

    @property
    def message_type(self) -> MessageType:
        """Audio messages always have AUDIO type."""
        return MessageType.AUDIO

    @property
    @abstractmethod
    def is_voice_message(self) -> bool:
        """Check if this is a voice message (as opposed to audio file)."""
        pass

    @property
    @abstractmethod
    def duration(self) -> int | None:
        """Get audio duration in seconds if available."""
        pass


class BaseVideoMessage(BaseMediaMessage):
    """Platform-agnostic video message base class."""

    @property
    def message_type(self) -> MessageType:
        """Video messages always have VIDEO type."""
        return MessageType.VIDEO

    @property
    @abstractmethod
    def duration(self) -> int | None:
        """Get video duration in seconds if available."""
        pass

    @property
    @abstractmethod
    def dimensions(self) -> tuple[int, int] | None:
        """Get video dimensions (width, height) if available."""
        pass


class BaseDocumentMessage(BaseMediaMessage):
    """Platform-agnostic document message base class."""

    @property
    def message_type(self) -> MessageType:
        """Document messages always have DOCUMENT type."""
        return MessageType.DOCUMENT

    @property
    @abstractmethod
    def filename(self) -> str | None:
        """Get the original filename if available."""
        pass

    @property
    @abstractmethod
    def file_extension(self) -> str | None:
        """Get the file extension if available."""
        pass


class BaseContactMessage(BaseMessage):
    """Platform-agnostic contact sharing message base class."""

    @property
    def message_type(self) -> MessageType:
        """Contact messages always have CONTACT type."""
        return MessageType.CONTACT

    @property
    @abstractmethod
    def contact_name(self) -> str:
        """Get the shared contact's name."""
        pass

    @property
    @abstractmethod
    def contact_phone(self) -> str | None:
        """Get the shared contact's phone number if available."""
        pass

    @property
    @abstractmethod
    def contact_data(self) -> dict[str, Any]:
        """Get all available contact information."""
        pass


class BaseLocationMessage(BaseMessage):
    """Platform-agnostic location sharing message base class."""

    @property
    def message_type(self) -> MessageType:
        """Location messages always have LOCATION type."""
        return MessageType.LOCATION

    @property
    @abstractmethod
    def latitude(self) -> float:
        """Get the latitude coordinate."""
        pass

    @property
    @abstractmethod
    def longitude(self) -> float:
        """Get the longitude coordinate."""
        pass

    @property
    @abstractmethod
    def address(self) -> str | None:
        """Get the address description if available."""
        pass

    @property
    @abstractmethod
    def location_name(self) -> str | None:
        """Get the location name if available."""
        pass
