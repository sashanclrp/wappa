"""
Media message models for WhatsApp messaging.

Pydantic schemas for media messaging operations based on WhatsApp Cloud API 2025
specifications and existing handle_media.py implementation patterns.
"""

from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field, field_validator

# Shared field for AI context description across media types
# This is NOT sent to WhatsApp - used for internal AI agent context only
AI_DESCRIPTION_FIELD = Field(
    None,
    max_length=2048,
    description=(
        "Optional description for AI context. "
        "Describes the media content for AI agents. "
        "NOT sent to WhatsApp - internal context only."
    ),
)

# Shared field for AI context transcript for audio/video media
# This is NOT sent to WhatsApp - used for internal AI agent context only
AI_TRANSCRIPT_FIELD = Field(
    None,
    max_length=10000,
    description=(
        "Optional transcript for audio/video content. "
        "Provides text transcription of audio for AI agents. "
        "NOT sent to WhatsApp - internal context only."
    ),
)


class MediaType(Enum):
    """Supported media types for WhatsApp messages.

    Based on WhatsApp Cloud API 2025 specifications and existing
    WhatsAppServiceMedia.MediaType implementation.
    """

    AUDIO = "audio"
    DOCUMENT = "document"
    IMAGE = "image"
    STICKER = "sticker"
    VIDEO = "video"

    @classmethod
    def get_supported_mime_types(cls, media_type: "MediaType") -> set[str]:
        """
        Returns set of supported MIME types for each media type.

        Extracted from existing WhatsAppServiceMedia.MediaType.get_supported_mime_types()
        and validated against WhatsApp Cloud API 2025 specifications.
        """
        supported_types = {
            cls.AUDIO: {
                "audio/aac",
                "audio/mp4",
                "audio/mpeg",
                "audio/amr",
                "audio/ogg",
            },
            cls.DOCUMENT: {
                "text/plain",
                "application/pdf",
                "application/vnd.ms-powerpoint",
                "application/msword",
                "application/vnd.ms-excel",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            },
            cls.IMAGE: {"image/jpeg", "image/png"},
            cls.STICKER: {"image/webp"},
            cls.VIDEO: {"video/3gp", "video/mp4"},
        }
        return supported_types[media_type]

    @classmethod
    def get_max_file_size(cls, media_type: "MediaType") -> int:
        """
        Returns maximum file size in bytes for each media type.

        Based on WhatsApp Cloud API 2025 specifications and existing
        validation logic from handle_media.py.
        """
        max_sizes = {
            cls.AUDIO: 16 * 1024 * 1024,  # 16MB
            cls.DOCUMENT: 100 * 1024 * 1024,  # 100MB
            cls.IMAGE: 5 * 1024 * 1024,  # 5MB
            cls.STICKER: 500 * 1024,  # 500KB (animated), 100KB (static)
            cls.VIDEO: 16 * 1024 * 1024,  # 16MB
        }
        return max_sizes[media_type]


class MediaMessage(BaseModel):
    """Base media message schema for media operations.

    Common fields for all media message types based on existing
    send_media() method signature from handle_media.py.
    """

    recipient: str = Field(
        ..., min_length=1, description="Recipient phone number or user identifier"
    )
    media_type: MediaType = Field(
        ..., description="Type of media (audio, document, image, sticker, video)"
    )
    media_source: str | Path = Field(
        ..., description="Either a URL string or a Path object to the local media file"
    )
    caption: str | None = Field(
        None,
        max_length=1024,
        description="Optional caption for the media (not supported for audio and sticker)",
    )
    filename: str | None = Field(
        None, description="Optional filename (used for documents)"
    )
    reply_to_message_id: str | None = Field(
        None, description="Optional message ID for replies"
    )

    @field_validator("caption")
    @classmethod
    def validate_caption_for_media_type(cls, v, info):
        """Validate caption is not used for audio and sticker media types."""
        if v is not None and info.data and "media_type" in info.data:
            media_type = info.data["media_type"]
            if media_type in (MediaType.AUDIO, MediaType.STICKER):
                raise ValueError(
                    f"Caption not supported for {media_type.value} media type"
                )
        return v

    @field_validator("filename")
    @classmethod
    def validate_filename_for_documents(cls, v, info):
        """Validate filename is provided for document media types when needed."""
        if v is not None and info.data and "media_type" in info.data:
            media_type = info.data["media_type"]
            if media_type != MediaType.DOCUMENT:
                raise ValueError(
                    f"Filename only supported for document media type, not {media_type.value}"
                )
        return v


class ImageMessage(BaseModel):
    """Image message schema for send_image operations.

    Supports JPEG and PNG images up to 5MB.
    Images must be 8-bit, RGB or RGBA (WhatsApp Cloud API 2025).
    """

    recipient: str = Field(
        ..., min_length=1, description="Recipient phone number or user identifier"
    )
    media_source: str | Path = Field(
        ..., description="Either a URL string or a Path object to the local media file"
    )
    caption: str | None = Field(
        None, max_length=1024, description="Optional caption for the image"
    )
    description: str | None = AI_DESCRIPTION_FIELD
    reply_to_message_id: str | None = Field(
        None, description="Optional message ID for replies"
    )


class VideoMessage(BaseModel):
    """Video message schema for send_video operations.

    Supports MP4 and 3GP videos up to 16MB.
    Only H.264 video codec and AAC audio codec supported.
    Single audio stream or no audio stream only (WhatsApp Cloud API 2025).
    """

    recipient: str = Field(
        ..., min_length=1, description="Recipient phone number or user identifier"
    )
    media_source: str | Path = Field(
        ..., description="Either a URL string or a Path object to the local media file"
    )
    caption: str | None = Field(
        None, max_length=1024, description="Optional caption for the video"
    )
    description: str | None = AI_DESCRIPTION_FIELD
    transcript: str | None = AI_TRANSCRIPT_FIELD
    reply_to_message_id: str | None = Field(
        None, description="Optional message ID for replies"
    )


class AudioMessage(BaseModel):
    """Audio message schema for send_audio operations.

    Supports AAC, AMR, MP3, M4A, and OGG audio up to 16MB.
    OGG must use OPUS codecs only, mono input only (WhatsApp Cloud API 2025).
    Note: Captions are not supported for audio messages.
    """

    recipient: str = Field(
        ..., min_length=1, description="Recipient phone number or user identifier"
    )
    media_source: str | Path = Field(
        ..., description="Either a URL string or a Path object to the local media file"
    )
    description: str | None = AI_DESCRIPTION_FIELD
    transcript: str | None = AI_TRANSCRIPT_FIELD
    reply_to_message_id: str | None = Field(
        None, description="Optional message ID for replies"
    )


class DocumentMessage(BaseModel):
    """Document message schema for send_document operations.

    Supports TXT, PDF, DOC, DOCX, XLS, XLSX, PPT, PPTX up to 100MB.
    """

    recipient: str = Field(
        ..., min_length=1, description="Recipient phone number or user identifier"
    )
    media_source: str | Path = Field(
        ..., description="Either a URL string or a Path object to the local media file"
    )
    caption: str | None = Field(
        None, max_length=1024, description="Optional caption for the document"
    )
    description: str | None = AI_DESCRIPTION_FIELD
    filename: str | None = Field(None, description="Optional filename for the document")
    reply_to_message_id: str | None = Field(
        None, description="Optional message ID for replies"
    )


class StickerMessage(BaseModel):
    """Sticker message schema for send_sticker operations.

    Supports WebP images only.
    Static stickers: 100KB max, Animated stickers: 500KB max.
    Note: Captions are not supported for sticker messages.
    """

    recipient: str = Field(
        ..., min_length=1, description="Recipient phone number or user identifier"
    )
    media_source: str | Path = Field(
        ..., description="Either a URL string or a Path object to the local media file"
    )
    description: str | None = AI_DESCRIPTION_FIELD
    reply_to_message_id: str | None = Field(
        None, description="Optional message ID for replies"
    )


class MediaUploadRequest(BaseModel):
    """Request schema for media upload operations.

    Used for direct media upload endpoints.
    """

    media_type: str = Field(..., description="MIME type of the media file")
    filename: str | None = Field(None, description="Original filename of the media")

    @field_validator("media_type")
    @classmethod
    def validate_mime_type(cls, v):
        """Validate MIME type is supported by WhatsApp."""
        supported_types = set()
        for media_type in MediaType:
            supported_types.update(MediaType.get_supported_mime_types(media_type))

        if v not in supported_types:
            raise ValueError(
                f"Unsupported MIME type: {v}. Supported types: {sorted(supported_types)}"
            )
        return v
