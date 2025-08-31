"""
WhatsApp implementation of the IMediaHandler interface.

Refactored from existing WhatsAppServiceMedia in whatsapp_latest/services/handle_media.py
to follow SOLID principles with dependency injection and proper separation of concerns.
"""

import mimetypes
import os
import tempfile
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Any, AsyncContextManager, BinaryIO

from wappa.core.logging.logger import get_logger
from wappa.domain.interfaces.media_interface import IMediaHandler
from wappa.domain.models.media_result import (
    MediaDeleteResult,
    MediaDownloadResult,
    MediaInfoResult,
    MediaUploadResult,
)
from wappa.messaging.whatsapp.client.whatsapp_client import WhatsAppClient
from wappa.messaging.whatsapp.models.media_models import MediaType
from wappa.schemas.core.types import PlatformType


class WhatsAppMediaHandler(IMediaHandler):
    """
    WhatsApp implementation of the media handler interface.

    Refactored from existing WhatsAppServiceMedia to follow SOLID principles:
    - Single Responsibility: Only handles media operations
    - Open/Closed: Extensible through interface implementation
    - Dependency Inversion: Depends on WhatsAppClient abstraction

    Based on WhatsApp Cloud API 2025 endpoints:
    - POST /PHONE_NUMBER_ID/media (upload)
    - GET /MEDIA_ID (get info/URL)
    - DELETE /MEDIA_ID (delete)
    - GET /MEDIA_URL (download)
    """

    def __init__(self, client: WhatsAppClient, tenant_id: str):
        """Initialize WhatsApp media handler with client and tenant context.

        Args:
            client: Configured WhatsApp client for API operations
            tenant_id: Tenant identifier (phone_number_id in WhatsApp context)
        """
        self.client = client
        self._tenant_id = tenant_id
        self.logger = get_logger(__name__)

    @property
    def platform(self) -> PlatformType:
        """Get the platform this handler manages."""
        return PlatformType.WHATSAPP

    @property
    def tenant_id(self) -> str:
        """Get the tenant ID this handler serves."""
        return self._tenant_id

    @property
    def supported_media_types(self) -> set[str]:
        """Get supported MIME types for WhatsApp."""
        supported_types = set()
        for media_type in MediaType:
            supported_types.update(MediaType.get_supported_mime_types(media_type))
        return supported_types

    @property
    def max_file_size(self) -> dict[str, int]:
        """Get maximum file sizes by media category."""
        return {
            "image": 5 * 1024 * 1024,  # 5MB
            "video": 16 * 1024 * 1024,  # 16MB
            "audio": 16 * 1024 * 1024,  # 16MB
            "document": 100 * 1024 * 1024,  # 100MB
            "sticker": 500 * 1024,  # 500KB (animated), 100KB (static)
        }

    async def upload_media(
        self,
        file_path: str | Path,
        media_type: str | None = None,
        filename: str | None = None,
    ) -> MediaUploadResult:
        """
        Upload media file to WhatsApp servers.

        Based on existing WhatsAppServiceMedia.upload_media() method.
        Implements POST /PHONE_NUMBER_ID/media endpoint.
        """
        try:
            media_path = Path(file_path)
            if not media_path.exists():
                return MediaUploadResult(
                    success=False,
                    error=f"Media file not found: {media_path}",
                    error_code="FILE_NOT_FOUND",
                    tenant_id=self._tenant_id,
                )

            # Auto-detect MIME type if not provided
            if media_type is None:
                media_type = mimetypes.guess_type(media_path)[0]
                if not media_type:
                    return MediaUploadResult(
                        success=False,
                        error=f"Could not determine MIME type for file: {media_path}",
                        error_code="MIME_TYPE_UNKNOWN",
                        tenant_id=self._tenant_id,
                    )

            # Validate MIME type
            if not self.validate_media_type(media_type):
                return MediaUploadResult(
                    success=False,
                    error=f"Unsupported MIME type '{media_type}'. Supported types: {sorted(self.supported_media_types)}",
                    error_code="MIME_TYPE_UNSUPPORTED",
                    tenant_id=self._tenant_id,
                )

            # Validate file size
            file_size = media_path.stat().st_size
            if not self.validate_file_size(file_size, media_type):
                max_size = self._get_max_size_for_mime_type(media_type)
                return MediaUploadResult(
                    success=False,
                    error=f"File size ({file_size} bytes) exceeds the limit ({max_size} bytes) for type {media_type}",
                    error_code="FILE_SIZE_EXCEEDED",
                    tenant_id=self._tenant_id,
                )

            # Prepare upload data
            data = {"messaging_product": "whatsapp", "type": media_type}

            # Construct upload URL using client's URL builder
            upload_url = self.client.url_builder.get_media_url()

            self.logger.debug(f"Uploading media file {media_path.name} to {upload_url}")

            with open(media_path, "rb") as file_handle:
                files = {"file": (filename or media_path.name, file_handle, media_type)}

                # Use the injected client for upload
                result = await self.client.post_request(
                    payload=data, custom_url=upload_url, files=files
                )

            media_id = result.get("id")
            if not media_id:
                return MediaUploadResult(
                    success=False,
                    error=f"No media ID in response for {media_path.name}: {result}",
                    error_code="NO_MEDIA_ID",
                    tenant_id=self._tenant_id,
                )

            self.logger.info(
                f"Successfully uploaded {media_path.name} (ID: {media_id})"
            )
            return MediaUploadResult(
                success=True,
                media_id=media_id,
                file_size=file_size,
                mime_type=media_type,
                platform=PlatformType.WHATSAPP,
                tenant_id=self._tenant_id,
            )

        except Exception as e:
            self.logger.exception(f"Failed to upload {file_path}: {e}")
            return MediaUploadResult(
                success=False,
                error=str(e),
                error_code="UPLOAD_FAILED",
                tenant_id=self._tenant_id,
            )

    async def upload_media_from_bytes(
        self, file_data: bytes, media_type: str, filename: str
    ) -> MediaUploadResult:
        """Upload media from bytes data."""
        try:
            # Validate MIME type
            if not self.validate_media_type(media_type):
                return MediaUploadResult(
                    success=False,
                    error=f"Unsupported MIME type '{media_type}'. Supported types: {sorted(self.supported_media_types)}",
                    error_code="MIME_TYPE_UNSUPPORTED",
                    tenant_id=self._tenant_id,
                )

            # Validate file size
            file_size = len(file_data)
            if not self.validate_file_size(file_size, media_type):
                max_size = self._get_max_size_for_mime_type(media_type)
                return MediaUploadResult(
                    success=False,
                    error=f"File size ({file_size} bytes) exceeds the limit ({max_size} bytes) for type {media_type}",
                    error_code="FILE_SIZE_EXCEEDED",
                    tenant_id=self._tenant_id,
                )

            # Prepare upload data
            data = {"messaging_product": "whatsapp", "type": media_type}

            # Construct upload URL using client's URL builder
            upload_url = self.client.url_builder.get_media_url()

            self.logger.debug(f"Uploading media from bytes: {filename}")

            files = {"file": (filename, file_data, media_type)}

            result = await self.client.post_request(
                payload=data, custom_url=upload_url, files=files
            )

            media_id = result.get("id")
            if not media_id:
                return MediaUploadResult(
                    success=False,
                    error=f"No media ID in response for {filename}: {result}",
                    error_code="NO_MEDIA_ID",
                    tenant_id=self._tenant_id,
                )

            self.logger.info(
                f"Successfully uploaded {filename} from bytes (ID: {media_id})"
            )
            return MediaUploadResult(
                success=True,
                media_id=media_id,
                file_size=file_size,
                mime_type=media_type,
                platform=PlatformType.WHATSAPP,
                tenant_id=self._tenant_id,
            )

        except Exception as e:
            self.logger.exception(f"Failed to upload {filename} from bytes: {e}")
            return MediaUploadResult(
                success=False,
                error=str(e),
                error_code="UPLOAD_FAILED",
                tenant_id=self._tenant_id,
            )

    async def upload_media_from_stream(
        self,
        file_stream: BinaryIO,
        media_type: str,
        filename: str,
        file_size: int | None = None,
    ) -> MediaUploadResult:
        """Upload media from file stream."""
        try:
            # Read stream data
            file_data = file_stream.read()

            # Use the bytes upload method
            return await self.upload_media_from_bytes(file_data, media_type, filename)

        except Exception as e:
            self.logger.exception(f"Failed to upload {filename} from stream: {e}")
            return MediaUploadResult(
                success=False,
                error=str(e),
                error_code="UPLOAD_FAILED",
                tenant_id=self._tenant_id,
            )

    async def get_media_info(self, media_id: str) -> MediaInfoResult:
        """
        Retrieve media information using media ID.

        Based on existing WhatsAppServiceMedia.get_media_url() method.
        Implements GET /MEDIA_ID endpoint.
        """
        try:
            endpoint = f"{media_id}/"
            self.logger.debug(f"Fetching media info for ID: {media_id}")

            result = await self.client.get_request(endpoint=endpoint)

            if not result or "url" not in result:
                return MediaInfoResult(
                    success=False,
                    error=f"Invalid response for media ID {media_id}: {result}",
                    error_code="INVALID_RESPONSE",
                    tenant_id=self._tenant_id,
                )

            self.logger.info(f"Successfully retrieved media URL for ID: {media_id}")
            return MediaInfoResult(
                success=True,
                media_id=media_id,
                url=result.get("url"),
                mime_type=result.get("mime_type"),
                file_size=result.get("file_size"),
                sha256=result.get("sha256"),
                platform=PlatformType.WHATSAPP,
                tenant_id=self._tenant_id,
            )

        except Exception as e:
            self.logger.exception(f"Error getting info for media ID {media_id}: {e}")
            return MediaInfoResult(
                success=False,
                error=str(e),
                error_code="INFO_RETRIEVAL_FAILED",
                tenant_id=self._tenant_id,
            )

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
        Download WhatsApp media using its media ID.

        Based on existing WhatsAppServiceMedia.download_media() method.
        Implements workflow: GET /MEDIA_ID -> GET /MEDIA_URL

        Args:
            media_id: Platform-specific media identifier
            destination_path: Optional path to save file (ignored if use_tempfile=True)
            sender_id: Optional sender ID for filename generation
            use_tempfile: If True, creates a temporary file with automatic cleanup
            temp_suffix: Custom suffix for temporary file (e.g., '.mp3', '.jpg')
            auto_cleanup: If True, temp files are cleaned up automatically
        """
        try:
            # Get media info first
            media_info_result = await self.get_media_info(media_id)
            if not media_info_result.success:
                return MediaDownloadResult(
                    success=False,
                    error=f"Failed to get media URL for ID {media_id}: {media_info_result.error}",
                    error_code="MEDIA_INFO_FAILED",
                    tenant_id=self._tenant_id,
                )

            media_url = media_info_result.url
            content_type = media_info_result.mime_type

            self.logger.debug(
                f"Starting download for media ID: {media_id} from URL: {media_url}"
            )

            # Use the client for streaming request
            session, response = await self.client.get_request_stream(media_url)

            try:
                if response.status != 200:
                    error_text = await response.text()
                    return MediaDownloadResult(
                        success=False,
                        error=f"Download failed for {media_id}: {response.status} - {error_text}",
                        error_code=f"HTTP_{response.status}",
                        tenant_id=self._tenant_id,
                    )

                # Validate content type and size
                response_content_type = response.headers.get(
                    "content-type", content_type
                )
                content_length_str = response.headers.get("content-length", "0")

                try:
                    content_length = int(content_length_str)
                except ValueError:
                    content_length = 0

                # Validate against platform limits
                if not self.validate_file_size(content_length, response_content_type):
                    max_size = self._get_max_size_for_mime_type(response_content_type)
                    return MediaDownloadResult(
                        success=False,
                        error=f"Media file size ({content_length} bytes) exceeds max allowed ({max_size} bytes) for type {response_content_type}",
                        error_code="FILE_SIZE_EXCEEDED",
                        tenant_id=self._tenant_id,
                    )

                # Read response data
                data = bytearray()
                downloaded_size = 0
                max_size = self._get_max_size_for_mime_type(response_content_type)

                async for chunk in response.content.iter_chunked(8192):
                    if chunk:
                        downloaded_size += len(chunk)
                        if downloaded_size > max_size:
                            return MediaDownloadResult(
                                success=False,
                                error=f"Download aborted: file size ({downloaded_size}) exceeded max ({max_size}) bytes for type {response_content_type}",
                                error_code="FILE_SIZE_EXCEEDED",
                                tenant_id=self._tenant_id,
                            )
                        data.extend(chunk)

                # Save to file if destination_path provided or tempfile requested
                final_path = None
                is_temp_file = False

                if use_tempfile:
                    # Create temporary file
                    extension_map = self._get_extension_map()
                    extension = temp_suffix or extension_map.get(
                        response_content_type, ""
                    )

                    # Create named temporary file
                    temp_fd, temp_path = tempfile.mkstemp(
                        suffix=extension, prefix="wappa_media_"
                    )
                    try:
                        with os.fdopen(temp_fd, "wb") as temp_file:
                            temp_file.write(data)
                        final_path = Path(temp_path)
                        is_temp_file = True
                        self.logger.info(
                            f"Media downloaded to temp file {final_path} ({downloaded_size} bytes)"
                        )
                    except Exception:
                        # Clean up on error
                        with suppress(Exception):
                            os.unlink(temp_path)
                        raise

                elif destination_path:
                    # Original destination path logic
                    extension_map = self._get_extension_map()
                    extension = extension_map.get(response_content_type, "")
                    media_type_base = response_content_type.split("/")[0]
                    timestamp = int(time.time())
                    filename_final = f"{media_type_base}_{sender_id or 'unknown'}_{timestamp}{extension}"

                    path = Path(destination_path)
                    path.mkdir(parents=True, exist_ok=True)
                    final_path = path / filename_final

                    with open(final_path, "wb") as f:
                        f.write(data)

                    self.logger.info(
                        f"Media successfully downloaded to {final_path} ({downloaded_size} bytes)"
                    )

                # Create result with temp file handling
                result = MediaDownloadResult(
                    success=True,
                    file_data=bytes(data),
                    file_path=str(final_path) if final_path else None,
                    mime_type=response_content_type,
                    file_size=downloaded_size,
                    sha256=media_info_result.sha256,
                    platform=PlatformType.WHATSAPP,
                    tenant_id=self._tenant_id,
                )

                # Mark as temp file if needed
                if is_temp_file:
                    result.mark_as_temp_file(cleanup_on_exit=auto_cleanup)

                return result

            finally:
                # Ensure response is closed
                if response and not response.closed:
                    response.release()

        except Exception as e:
            self.logger.exception(f"Error downloading media ID {media_id}: {e}")
            return MediaDownloadResult(
                success=False,
                error=str(e),
                error_code="DOWNLOAD_FAILED",
                tenant_id=self._tenant_id,
            )

    @asynccontextmanager
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
        result = await self.download_media(
            media_id=media_id,
            use_tempfile=True,
            temp_suffix=temp_suffix,
            sender_id=sender_id,
            auto_cleanup=True,
        )

        try:
            yield result
        finally:
            # Context manager cleanup handled by MediaDownloadResult
            result._cleanup_temp_file()

    async def get_media_as_bytes(self, media_id: str) -> MediaDownloadResult:
        """
        Download media as bytes without creating any files.

        Memory-only download for processing that doesn't require file system access.

        Args:
            media_id: Platform-specific media identifier

        Returns:
            MediaDownloadResult with file_data bytes (file_path will be None)
        """
        return await self.download_media(
            media_id=media_id, destination_path=None, use_tempfile=False
        )

    async def stream_media(
        self, media_id: str, chunk_size: int = 8192
    ) -> AsyncIterator[bytes]:
        """Stream media by ID for large files."""
        try:
            # Get media info first
            media_info_result = await self.get_media_info(media_id)
            if not media_info_result.success:
                raise RuntimeError(
                    f"Failed to get media URL for ID {media_id}: {media_info_result.error}"
                )

            media_url = media_info_result.url

            # Use the client for streaming request
            session, response = await self.client.get_request_stream(media_url)

            try:
                if response.status != 200:
                    error_text = await response.text()
                    raise RuntimeError(
                        f"Download failed for {media_id}: {response.status} - {error_text}"
                    )

                async for chunk in response.content.iter_chunked(chunk_size):
                    if chunk:
                        yield chunk

            finally:
                # Ensure response is closed
                if response and not response.closed:
                    response.release()

        except Exception as e:
            self.logger.exception(f"Error streaming media ID {media_id}: {e}")
            raise

    async def delete_media(self, media_id: str) -> MediaDeleteResult:
        """
        Delete media from WhatsApp servers using the media ID.

        Based on existing WhatsAppServiceMedia.delete_media() method.
        Implements DELETE /MEDIA_ID endpoint.
        """
        try:
            endpoint = f"{media_id}"
            params = {}

            self.logger.debug(f"Attempting to delete media ID: {media_id}")

            result = await self.client.delete_request(endpoint=endpoint, params=params)

            if result.get("success"):
                self.logger.info(f"Successfully deleted media ID: {media_id}")
                return MediaDeleteResult(
                    success=True,
                    media_id=media_id,
                    platform=PlatformType.WHATSAPP,
                    tenant_id=self._tenant_id,
                )
            else:
                error_msg = result.get("error", {}).get("message", "Unknown reason")
                return MediaDeleteResult(
                    success=False,
                    media_id=media_id,
                    error=f"API indicated deletion failed: {error_msg}",
                    error_code="DELETION_FAILED",
                    platform=PlatformType.WHATSAPP,
                    tenant_id=self._tenant_id,
                )

        except Exception as e:
            self.logger.exception(f"Error deleting media ID {media_id}: {e}")
            return MediaDeleteResult(
                success=False,
                media_id=media_id,
                error=str(e),
                error_code="DELETION_FAILED",
                platform=PlatformType.WHATSAPP,
                tenant_id=self._tenant_id,
            )

    def validate_media_type(self, mime_type: str) -> bool:
        """Validate if MIME type is supported by WhatsApp."""
        return mime_type in self.supported_media_types

    def validate_file_size(self, file_size: int, mime_type: str) -> bool:
        """Validate if file size is within WhatsApp limits."""
        max_size = self._get_max_size_for_mime_type(mime_type)
        return file_size <= max_size

    def get_media_limits(self) -> dict[str, Any]:
        """Get WhatsApp-specific media limits and constraints."""
        return {
            "max_sizes": self.max_file_size,
            "supported_types": sorted(self.supported_media_types),
            "url_expiry_minutes": 5,
            "media_persistence_days": 30,
            "platform": "whatsapp",
            "api_version": self.client.api_version,
        }

    def _get_max_size_for_mime_type(self, mime_type: str) -> int:
        """Get maximum file size for a specific MIME type."""
        if mime_type.startswith("audio/") or mime_type.startswith("video/"):
            return 16 * 1024 * 1024  # 16MB
        elif mime_type.startswith("image/"):
            if mime_type == "image/webp":
                return 500 * 1024  # 500KB for animated stickers
            return 5 * 1024 * 1024  # 5MB for regular images
        elif mime_type.startswith("application/") or mime_type == "text/plain":
            return 100 * 1024 * 1024  # 100MB
        else:
            return 100 * 1024 * 1024  # Default to 100MB

    def _get_extension_map(self) -> dict[str, str]:
        """Get file extension mapping by MIME type."""
        return {
            "audio/aac": ".aac",
            "audio/amr": ".amr",
            "audio/mpeg": ".mp3",
            "audio/mp4": ".m4a",
            "audio/ogg": ".ogg",
            "text/plain": ".txt",
            "application/vnd.ms-excel": ".xls",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
            "application/msword": ".doc",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
            "application/vnd.ms-powerpoint": ".ppt",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
            "application/pdf": ".pdf",
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/webp": ".webp",
            "video/3gpp": ".3gp",
            "video/mp4": ".mp4",
        }
