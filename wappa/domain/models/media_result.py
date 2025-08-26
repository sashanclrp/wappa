"""
Media result models for platform-agnostic media operations.

These models represent the results of media operations across different
messaging platforms, providing consistent response structures while
maintaining compatibility with platform-specific response formats.
"""

from datetime import datetime

from pydantic import BaseModel, Field

from wappa.schemas.core.types import PlatformType


class MediaUploadResult(BaseModel):
    """Result of a media upload operation.

    Standard response model for media upload operations across platforms.
    Based on WhatsApp Cloud API response: {"id": "<MEDIA_ID>"}
    """

    success: bool
    platform: PlatformType = PlatformType.WHATSAPP
    media_id: str | None = None
    media_url: str | None = None
    file_size: int | None = None
    mime_type: str | None = None
    error: str | None = None
    error_code: str | None = None
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)
    tenant_id: str | None = None  # phone_number_id in WhatsApp context

    class Config:
        use_enum_values = True


class MediaInfoResult(BaseModel):
    """Result of a media info retrieval operation.

    Standard response model for media info operations.
    Based on WhatsApp Cloud API response:
    {
        "messaging_product": "whatsapp",
        "url": "<URL>",
        "mime_type": "<MIME_TYPE>",
        "sha256": "<HASH>",
        "file_size": "<FILE_SIZE>",
        "id": "<MEDIA_ID>"
    }
    """

    success: bool
    platform: PlatformType = PlatformType.WHATSAPP
    media_id: str | None = None
    url: str | None = None
    mime_type: str | None = None
    file_size: int | None = None
    sha256: str | None = None
    error: str | None = None
    error_code: str | None = None
    retrieved_at: datetime = Field(default_factory=datetime.utcnow)
    tenant_id: str | None = None

    class Config:
        use_enum_values = True


class MediaDownloadResult(BaseModel):
    """Result of a media download operation.

    Standard response model for media download operations.
    Compatible with existing handle_media.py download patterns.
    """

    success: bool
    platform: PlatformType = PlatformType.WHATSAPP
    file_data: bytes | None = None
    file_path: str | None = None
    mime_type: str | None = None
    file_size: int | None = None
    sha256: str | None = None
    error: str | None = None
    error_code: str | None = None
    downloaded_at: datetime = Field(default_factory=datetime.utcnow)
    tenant_id: str | None = None

    class Config:
        use_enum_values = True
        # Allow bytes in file_data field
        arbitrary_types_allowed = True


class MediaDeleteResult(BaseModel):
    """Result of a media delete operation.

    Standard response model for media delete operations.
    Based on WhatsApp Cloud API response: {"success": true}
    """

    success: bool
    platform: PlatformType = PlatformType.WHATSAPP
    media_id: str | None = None
    error: str | None = None
    error_code: str | None = None
    deleted_at: datetime = Field(default_factory=datetime.utcnow)
    tenant_id: str | None = None

    class Config:
        use_enum_values = True
