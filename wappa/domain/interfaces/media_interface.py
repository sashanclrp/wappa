"""
Media handling interface for platform-agnostic media operations.

This interface defines the contract for media handling operations that can be
implemented across different messaging platforms (WhatsApp, Telegram, Teams, etc.).

Based on existing WhatsAppServiceMedia implementation from handle_media.py
and WhatsApp Cloud API 2025 specifications for the 4 core endpoints:
- POST /PHONE_NUMBER_ID/media (upload)
- GET /MEDIA_ID (get info/URL)
- DELETE /MEDIA_ID (delete)
- GET /MEDIA_URL (download)
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from pathlib import Path
from typing import AsyncContextManager, BinaryIO

from wappa.domain.models.media_result import (
    MediaDeleteResult,
    MediaDownloadResult,
    MediaInfoResult,
    MediaUploadResult,
)
from wappa.schemas.core.types import PlatformType


class IMediaHandler(ABC):
    """
    Platform-agnostic media handling interface.

    Provides consistent media operations across different messaging platforms
    while abstracting platform-specific implementations.

    Based on existing WhatsAppServiceMedia methods:
    - upload_media() -> upload_media()
    - get_media_url() -> get_media_info()
    - download_media() -> download_media()
    - delete_media() -> delete_media()
    """

    @property
    @abstractmethod
    def platform(self) -> PlatformType:
        """Get the platform this handler manages."""
        pass

    @property
    @abstractmethod
    def tenant_id(self) -> str:
        """Get the tenant ID this handler serves.

        Note: In WhatsApp context, this is the phone_number_id.
        Different platforms may use different tenant identifiers.
        """
        pass

    @property
    @abstractmethod
    def supported_media_types(self) -> set[str]:
        """Get supported MIME types for this platform.

        Returns:
            Set of supported MIME type strings
        """
        pass

    @property
    @abstractmethod
    def max_file_size(self) -> dict[str, int]:
        """Get maximum file sizes in bytes by media category.

        Returns:
            Dictionary mapping media categories to max sizes in bytes
            Example: {"image": 5242880, "video": 16777216, "audio": 16777216, "document": 104857600}
        """
        pass

    # Upload Operations (POST /PHONE_NUMBER_ID/media)
    @abstractmethod
    async def upload_media(
        self,
        file_path: str | Path,
        media_type: str | None = None,
        filename: str | None = None,
    ) -> MediaUploadResult:
        """
        Upload media file to platform.

        Based on existing WhatsAppServiceMedia.upload_media() method.
        Implements POST /PHONE_NUMBER_ID/media endpoint.

        Args:
            file_path: Path to the file to upload
            media_type: MIME type (auto-detected if None)
            filename: Original filename (extracted from path if None)

        Returns:
            MediaUploadResult with upload status and media ID

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If MIME type unsupported or file too large
            Platform-specific exceptions for API failures
        """
        pass

    @abstractmethod
    async def upload_media_from_bytes(
        self, file_data: bytes, media_type: str, filename: str
    ) -> MediaUploadResult:
        """
        Upload media from bytes data.

        Extension of existing upload functionality for in-memory files.
        Implements POST /PHONE_NUMBER_ID/media endpoint.

        Args:
            file_data: Binary file data
            media_type: MIME type of the data
            filename: Filename for the upload

        Returns:
            MediaUploadResult with upload status and media ID

        Raises:
            ValueError: If MIME type unsupported or file too large
            Platform-specific exceptions for API failures
        """
        pass

    @abstractmethod
    async def upload_media_from_stream(
        self,
        file_stream: BinaryIO,
        media_type: str,
        filename: str,
        file_size: int | None = None,
    ) -> MediaUploadResult:
        """
        Upload media from file stream.

        Extension of existing upload functionality for streaming uploads.
        Implements POST /PHONE_NUMBER_ID/media endpoint.

        Args:
            file_stream: Binary file stream
            media_type: MIME type of the data
            filename: Filename for the upload
            file_size: Size of the file (for progress tracking)

        Returns:
            MediaUploadResult with upload status and media ID

        Raises:
            ValueError: If MIME type unsupported or file too large
            Platform-specific exceptions for API failures
        """
        pass

    # Retrieval Operations (GET /MEDIA_ID)
    @abstractmethod
    async def get_media_info(self, media_id: str) -> MediaInfoResult:
        """
        Get media information by ID.

        Based on existing WhatsAppServiceMedia.get_media_url() method.
        Implements GET /MEDIA_ID endpoint.

        WhatsApp API Response:
        {
            "messaging_product": "whatsapp",
            "url": "<URL>",
            "mime_type": "<MIME_TYPE>",
            "sha256": "<HASH>",
            "file_size": "<FILE_SIZE>",
            "id": "<MEDIA_ID>"
        }

        Args:
            media_id: Platform-specific media identifier

        Returns:
            MediaInfoResult with media info or error details

        Note:
            URLs expire after 5 minutes in WhatsApp Cloud API.
            Call this method again if URL expires.
        """
        pass

    # Download Operations (GET /MEDIA_URL)
    @abstractmethod
    async def download_media(
        self,
        media_id: str,
        destination_path: str | Path | None = None,
        sender_id: str | None = None,
        use_tempfile: bool = False,
        temp_suffix: str | None = None,
        auto_cleanup: bool = True,
    ) -> MediaDownloadResult:
        """
        Download media by ID.

        Based on existing WhatsAppServiceMedia.download_media() method.
        Implements workflow: GET /MEDIA_ID -> GET /MEDIA_URL

        Args:
            media_id: Platform-specific media identifier
            destination_path: Optional path to save file (ignored if use_tempfile=True)
            sender_id: Optional sender ID for filename generation
            use_tempfile: If True, creates a temporary file with automatic cleanup
            temp_suffix: Custom suffix for temporary file (e.g., '.mp3', '.jpg')
            auto_cleanup: If True, temp files are cleaned up automatically

        Returns:
            MediaDownloadResult with file data and metadata

        Note:
            If destination_path provided, saves file to disk.
            If use_tempfile=True, creates temporary file that can be auto-cleaned.
            If neither provided, returns file data in memory.
            Handles URL expiration by re-fetching URL if needed.
        """
        pass

    @abstractmethod
    async def download_media_tempfile(
        self,
        media_id: str,
        temp_suffix: str | None = None,
        sender_id: str | None = None,
    ) -> AsyncContextManager[MediaDownloadResult]:
        """
        Download media to a temporary file with automatic cleanup.

        Convenience method that provides a context manager for temporary file handling.
        The temporary file is automatically deleted when the context exits.

        Args:
            media_id: Platform-specific media identifier
            temp_suffix: Custom suffix for temporary file (e.g., '.mp3', '.jpg')
            sender_id: Optional sender ID for logging/debugging

        Returns:
            Async context manager yielding MediaDownloadResult with temp file path

        Example:
            async with handler.download_media_tempfile(media_id, '.mp3') as result:
                if result.success:
                    # Use result.file_path - file auto-deleted on exit
                    process_audio(result.file_path)
        """
        pass

    @abstractmethod
    async def get_media_as_bytes(self, media_id: str) -> MediaDownloadResult:
        """
        Download media as bytes without creating any files.

        Memory-only download for processing that doesn't require file system access.

        Args:
            media_id: Platform-specific media identifier

        Returns:
            MediaDownloadResult with file_data bytes (file_path will be None)
        """
        pass

    @abstractmethod
    async def stream_media(
        self, media_id: str, chunk_size: int = 8192
    ) -> AsyncIterator[bytes]:
        """
        Stream media by ID for large files.

        Extension of download functionality for memory-efficient streaming.
        Implements workflow: GET /MEDIA_ID -> GET /MEDIA_URL with streaming.

        Args:
            media_id: Platform-specific media identifier
            chunk_size: Size of chunks to yield

        Yields:
            Bytes chunks of the media file

        Raises:
            Platform-specific exceptions for API failures or URL expiration
        """
        pass

    # Delete Operations (DELETE /MEDIA_ID)
    @abstractmethod
    async def delete_media(self, media_id: str) -> MediaDeleteResult:
        """
        Delete media by ID.

        Based on existing WhatsAppServiceMedia.delete_media() method.
        Implements DELETE /MEDIA_ID endpoint.

        WhatsApp API Response:
        {
            "success": true
        }

        Args:
            media_id: Platform-specific media identifier to delete

        Returns:
            MediaDeleteResult with deletion status

        Note:
            Media files persist for 30 days unless deleted earlier.
            Deletion is permanent and cannot be undone.
        """
        pass

    # Validation Operations
    @abstractmethod
    def validate_media_type(self, mime_type: str) -> bool:
        """
        Validate if MIME type is supported by platform.

        Args:
            mime_type: MIME type to validate

        Returns:
            True if supported, False otherwise
        """
        pass

    @abstractmethod
    def validate_file_size(self, file_size: int, mime_type: str) -> bool:
        """
        Validate if file size is within platform limits.

        Args:
            file_size: File size in bytes
            mime_type: MIME type of the file

        Returns:
            True if within limits, False otherwise
        """
        pass

    @abstractmethod
    def get_media_limits(self) -> dict[str, any]:
        """
        Get platform-specific media limits and constraints.

        Returns:
            Dictionary containing platform-specific limits
            Example: {
                "max_sizes": {"image": 5242880, "video": 16777216},
                "supported_types": ["image/jpeg", "video/mp4"],
                "url_expiry_minutes": 5
            }
        """
        pass
