"""WhatsApp media types: MIME types and size caps per media type.

The neutral media send request models live in ``wappa.schemas.requests``.
"""

from __future__ import annotations

from enum import Enum


class MediaType(Enum):
    AUDIO = "audio"
    DOCUMENT = "document"
    IMAGE = "image"
    STICKER = "sticker"
    VIDEO = "video"

    @classmethod
    def get_supported_mime_types(cls, media_type: MediaType) -> set[str]:
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
    def get_max_file_size(cls, media_type: MediaType) -> int:
        max_sizes = {
            cls.AUDIO: 16 * 1024 * 1024,  # 16MB
            cls.DOCUMENT: 100 * 1024 * 1024,  # 100MB
            cls.IMAGE: 5 * 1024 * 1024,  # 5MB
            cls.STICKER: 500 * 1024,  # 500KB (animated), 100KB (static)
            cls.VIDEO: 16 * 1024 * 1024,  # 16MB
        }
        return max_sizes[media_type]
