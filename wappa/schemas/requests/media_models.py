"""Neutral HTTP request models for media sends.

``caption`` keeps WhatsApp's limit (``CAPTION_MAX``); Instagram sends it as a
follow-up text and splits it. ``description`` and ``transcript`` are never
sent to the Platform: middleware sees them on the ``SendInvocation``.
"""

from pathlib import Path

from pydantic import Field, ValidationInfo, field_validator

from wappa.domain.interactive import CAPTION_MAX
from wappa.domain.interfaces.media_library import MediaFamily
from wappa.schemas.core.recipient import DeliveryRequest

# Shared field for AI context description across media types.
# Never sent to the Platform: metadata for middleware and AI agents only.
AI_DESCRIPTION_FIELD = Field(
    None,
    max_length=2048,
    description=(
        "Optional description for AI context. "
        "Describes the media content for AI agents. "
        "Never sent to the Platform; visible to middleware only."
    ),
)

# Shared field for AI context transcript for audio/video media.
# Never sent to the Platform: metadata for middleware and AI agents only.
AI_TRANSCRIPT_FIELD = Field(
    None,
    max_length=10000,
    description=(
        "Optional transcript for audio/video content. "
        "Provides text transcription of audio for AI agents. "
        "Never sent to the Platform; visible to middleware only."
    ),
)


class MediaMessage(DeliveryRequest):
    media_type: MediaFamily = Field(
        ..., description="Type of media (audio, document, image, sticker, video)"
    )
    media_source: str | Path = Field(
        ..., description="Either a URL string or a Path object to the local media file"
    )
    caption: str | None = Field(
        None,
        max_length=CAPTION_MAX,
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
    def validate_caption_for_media_type(
        cls, v: str | None, info: ValidationInfo
    ) -> str | None:
        if v is not None and info.data and "media_type" in info.data:
            media_type = info.data["media_type"]
            if media_type in (MediaFamily.AUDIO, MediaFamily.STICKER):
                raise ValueError(
                    f"Caption not supported for {media_type.value} media type"
                )
        return v

    @field_validator("filename")
    @classmethod
    def validate_filename_for_documents(
        cls, v: str | None, info: ValidationInfo
    ) -> str | None:
        if v is not None and info.data and "media_type" in info.data:
            media_type = info.data["media_type"]
            if media_type != MediaFamily.DOCUMENT:
                raise ValueError(
                    f"Filename only supported for document media type, not {media_type.value}"
                )
        return v


class ImageMessage(DeliveryRequest):
    media_source: str | Path = Field(
        ..., description="Either a URL string or a Path object to the local media file"
    )
    caption: str | None = Field(
        None, max_length=CAPTION_MAX, description="Optional caption for the image"
    )
    description: str | None = AI_DESCRIPTION_FIELD
    reply_to_message_id: str | None = Field(
        None, description="Optional message ID for replies"
    )


class VideoMessage(DeliveryRequest):
    media_source: str | Path = Field(
        ..., description="Either a URL string or a Path object to the local media file"
    )
    caption: str | None = Field(
        None, max_length=CAPTION_MAX, description="Optional caption for the video"
    )
    description: str | None = AI_DESCRIPTION_FIELD
    transcript: str | None = AI_TRANSCRIPT_FIELD
    reply_to_message_id: str | None = Field(
        None, description="Optional message ID for replies"
    )


class AudioMessage(DeliveryRequest):
    media_source: str | Path = Field(
        ..., description="Either a URL string or a Path object to the local media file"
    )
    description: str | None = AI_DESCRIPTION_FIELD
    transcript: str | None = AI_TRANSCRIPT_FIELD
    is_voice: bool = Field(
        False,
        description=(
            "Deliver as a voice note (waveform). WhatsApp: .ogg (Opus, mono) only, "
            "otherwise 400. Instagram shows all audio as a voice message and "
            "ignores the flag"
        ),
    )
    reply_to_message_id: str | None = Field(
        None, description="Optional message ID for replies"
    )


class DocumentMessage(DeliveryRequest):
    media_source: str | Path = Field(
        ..., description="Either a URL string or a Path object to the local media file"
    )
    caption: str | None = Field(
        None, max_length=CAPTION_MAX, description="Optional caption for the document"
    )
    description: str | None = AI_DESCRIPTION_FIELD
    filename: str | None = Field(None, description="Optional filename for the document")
    reply_to_message_id: str | None = Field(
        None, description="Optional message ID for replies"
    )


class StickerMessage(DeliveryRequest):
    media_source: str | Path = Field(
        ..., description="Either a URL string or a Path object to the local media file"
    )
    description: str | None = AI_DESCRIPTION_FIELD
    reply_to_message_id: str | None = Field(
        None, description="Optional message ID for replies"
    )
