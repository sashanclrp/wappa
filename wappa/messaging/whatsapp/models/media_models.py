"""Media message models for WhatsApp messaging."""

from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field, field_validator

from wappa.schemas.core.recipient import RecipientRequest

# Shared field for AI context description across media types.
# NOT sent to WhatsApp - used for internal AI agent context only.
AI_DESCRIPTION_FIELD = Field(
    None,
    max_length=2048,
    description=(
        "Optional description for AI context. "
        "Describes the media content for AI agents. "
        "NOT sent to WhatsApp - internal context only."
    ),
)

# Shared field for AI context transcript for audio/video media.
# NOT sent to WhatsApp - used for internal AI agent context only.
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
    AUDIO = "audio"
    DOCUMENT = "document"
    IMAGE = "image"
    STICKER = "sticker"
    VIDEO = "video"

    @classmethod
    def get_supported_mime_types(cls, media_type: "MediaType") -> set[str]:
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
        max_sizes = {
            cls.AUDIO: 16 * 1024 * 1024,  # 16MB
            cls.DOCUMENT: 100 * 1024 * 1024,  # 100MB
            cls.IMAGE: 5 * 1024 * 1024,  # 5MB
            cls.STICKER: 500 * 1024,  # 500KB (animated), 100KB (static)
            cls.VIDEO: 16 * 1024 * 1024,  # 16MB
        }
        return max_sizes[media_type]


class MediaMessage(RecipientRequest):
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
        if v is not None and info.data and "media_type" in info.data:
            media_type = info.data["media_type"]
            if media_type != MediaType.DOCUMENT:
                raise ValueError(
                    f"Filename only supported for document media type, not {media_type.value}"
                )
        return v


class ImageMessage(RecipientRequest):
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


class VideoMessage(RecipientRequest):
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


class AudioMessage(RecipientRequest):
    media_source: str | Path = Field(
        ..., description="Either a URL string or a Path object to the local media file"
    )
    description: str | None = AI_DESCRIPTION_FIELD
    transcript: str | None = AI_TRANSCRIPT_FIELD
    reply_to_message_id: str | None = Field(
        None, description="Optional message ID for replies"
    )


class DocumentMessage(RecipientRequest):
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


class StickerMessage(RecipientRequest):
    media_source: str | Path = Field(
        ..., description="Either a URL string or a Path object to the local media file"
    )
    description: str | None = AI_DESCRIPTION_FIELD
    reply_to_message_id: str | None = Field(
        None, description="Optional message ID for replies"
    )


class MediaUploadRequest(BaseModel):
    media_type: str = Field(..., description="MIME type of the media file")
    filename: str | None = Field(None, description="Original filename of the media")

    @field_validator("media_type")
    @classmethod
    def validate_mime_type(cls, v):
        supported_types: set[str] = set()
        for media_type in MediaType:
            supported_types.update(MediaType.get_supported_mime_types(media_type))

        if v not in supported_types:
            raise ValueError(
                f"Unsupported MIME type: {v}. Supported types: {sorted(supported_types)}"
            )
        return v
