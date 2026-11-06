"""Platform-agnostic media message base classes: image, audio, video and document."""

from __future__ import annotations

from abc import abstractmethod
from typing import Any

from wappa.schemas.core.types import (
    MediaType,
    MessageType,
)
from wappa.webhooks.core.base_message.core import BaseMessage


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

    @property
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
