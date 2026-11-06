"""WhatsApp media rules: MIME types and size caps per media type.

The neutral media send request models live in ``wappa.schemas.requests``.
"""

from enum import Enum

from pydantic import BaseModel, Field, field_validator


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
            cls.VIDEO: {"video/3gpp", "video/mp4"},
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


class MediaUploadRequest(BaseModel):
    media_type: str = Field(..., description="MIME type of the media file")
    filename: str | None = Field(None, description="Original filename of the media")

    @field_validator("media_type")
    @classmethod
    def validate_mime_type(cls, v: str) -> str:
        supported_types: set[str] = set()
        for media_type in MediaType:
            supported_types.update(MediaType.get_supported_mime_types(media_type))

        if v not in supported_types:
            raise ValueError(
                f"Unsupported MIME type: {v}. Supported types: {sorted(supported_types)}"
            )
        return v
