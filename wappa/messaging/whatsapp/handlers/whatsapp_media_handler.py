import mimetypes
import os
import tempfile
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Any, BinaryIO

import httpx

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
    """WhatsApp implementation of the media handler interface."""

    def __init__(
        self,
        client: WhatsAppClient,
        inbox_id: str,
        *,
        media_download_client: httpx.AsyncClient | None = None,
    ):
        self.client = client
        self._inbox_id = inbox_id
        self._media_download_client = media_download_client
        self.logger = get_logger(__name__)

    @property
    def platform(self) -> PlatformType:
        return PlatformType.WHATSAPP

    @property
    def inbox_id(self) -> str:
        return self._inbox_id

    @property
    def supported_media_types(self) -> set[str]:
        return {
            mime
            for media_type in MediaType
            for mime in MediaType.get_supported_mime_types(media_type)
        }

    @property
    def max_file_size(self) -> dict[str, int]:
        return {
            "image": 5 * 1024 * 1024,
            "video": 16 * 1024 * 1024,
            "audio": 16 * 1024 * 1024,
            "document": 100 * 1024 * 1024,
            "sticker": 500 * 1024,
        }

    async def upload_media(
        self,
        file_path: str | Path,
        media_type: str | None = None,
        filename: str | None = None,
    ) -> MediaUploadResult:
        try:
            media_path = Path(file_path)
            if not media_path.exists():
                return MediaUploadResult(
                    success=False,
                    error=f"Media file not found: {media_path}",
                    error_code="FILE_NOT_FOUND",
                    inbox_id=self._inbox_id,
                )

            if media_type is None:
                media_type = mimetypes.guess_type(media_path)[0]
                if not media_type:
                    return MediaUploadResult(
                        success=False,
                        error=f"Could not determine MIME type for file: {media_path}",
                        error_code="MIME_TYPE_UNKNOWN",
                        inbox_id=self._inbox_id,
                    )

            if not self.validate_media_type(media_type):
                return MediaUploadResult(
                    success=False,
                    error=f"Unsupported MIME type '{media_type}'. Supported types: {sorted(self.supported_media_types)}",
                    error_code="MIME_TYPE_UNSUPPORTED",
                    inbox_id=self._inbox_id,
                )

            file_size = media_path.stat().st_size
            if not self.validate_file_size(file_size, media_type):
                max_size = self._get_max_size_for_mime_type(media_type)
                return MediaUploadResult(
                    success=False,
                    error=f"File size ({file_size} bytes) exceeds the limit ({max_size} bytes) for type {media_type}",
                    error_code="FILE_SIZE_EXCEEDED",
                    inbox_id=self._inbox_id,
                )

            upload_url = self.client.url_builder.get_media_url()
            data = {"messaging_product": "whatsapp", "type": media_type}

            self.logger.debug(f"Uploading media file {media_path.name} to {upload_url}")

            with open(media_path, "rb") as file_handle:
                files = {"file": (filename or media_path.name, file_handle, media_type)}
                result = await self.client.post_request(
                    payload=data, custom_url=upload_url, files=files
                )

            media_id = result.get("id")
            if not media_id:
                return MediaUploadResult(
                    success=False,
                    error=f"No media ID in response for {media_path.name}: {result}",
                    error_code="NO_MEDIA_ID",
                    inbox_id=self._inbox_id,
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
                inbox_id=self._inbox_id,
            )

        except Exception as e:
            self.logger.exception(f"Failed to upload {file_path}: {e}")
            return MediaUploadResult(
                success=False,
                error=str(e),
                error_code="UPLOAD_FAILED",
                inbox_id=self._inbox_id,
            )

    async def upload_media_from_bytes(
        self, file_data: bytes, media_type: str, filename: str
    ) -> MediaUploadResult:
        try:
            if not self.validate_media_type(media_type):
                return MediaUploadResult(
                    success=False,
                    error=f"Unsupported MIME type '{media_type}'. Supported types: {sorted(self.supported_media_types)}",
                    error_code="MIME_TYPE_UNSUPPORTED",
                    inbox_id=self._inbox_id,
                )

            file_size = len(file_data)
            if not self.validate_file_size(file_size, media_type):
                max_size = self._get_max_size_for_mime_type(media_type)
                return MediaUploadResult(
                    success=False,
                    error=f"File size ({file_size} bytes) exceeds the limit ({max_size} bytes) for type {media_type}",
                    error_code="FILE_SIZE_EXCEEDED",
                    inbox_id=self._inbox_id,
                )

            upload_url = self.client.url_builder.get_media_url()
            data = {"messaging_product": "whatsapp", "type": media_type}
            files = {"file": (filename, file_data, media_type)}

            self.logger.debug(f"Uploading media from bytes: {filename}")

            result = await self.client.post_request(
                payload=data, custom_url=upload_url, files=files
            )

            media_id = result.get("id")
            if not media_id:
                return MediaUploadResult(
                    success=False,
                    error=f"No media ID in response for {filename}: {result}",
                    error_code="NO_MEDIA_ID",
                    inbox_id=self._inbox_id,
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
                inbox_id=self._inbox_id,
            )

        except Exception as e:
            self.logger.exception(f"Failed to upload {filename} from bytes: {e}")
            return MediaUploadResult(
                success=False,
                error=str(e),
                error_code="UPLOAD_FAILED",
                inbox_id=self._inbox_id,
            )

    async def upload_media_from_stream(
        self,
        file_stream: BinaryIO,
        media_type: str,
        filename: str,
        file_size: int | None = None,
    ) -> MediaUploadResult:
        try:
            return await self.upload_media_from_bytes(
                file_stream.read(), media_type, filename
            )
        except Exception as e:
            self.logger.exception(f"Failed to upload {filename} from stream: {e}")
            return MediaUploadResult(
                success=False,
                error=str(e),
                error_code="UPLOAD_FAILED",
                inbox_id=self._inbox_id,
            )

    async def upload_media_from_url(
        self,
        url: str,
        *,
        filename: str = "download",
        timeout: float = 60.0,
    ) -> MediaUploadResult:
        """Download a public URL and re-upload to WhatsApp Media API.

        Uses a separate HTTP client with no auth headers to avoid
        leaking the WhatsApp Bearer token to third-party hosts.
        """
        try:
            self.logger.debug(f"Downloading media from URL for re-upload: {url}")

            owns_client = self._media_download_client is None
            download_client = (
                self._media_download_client
                or httpx.AsyncClient(timeout=httpx.Timeout(timeout))
            )
            try:
                async with download_client.stream("GET", url) as response:
                    if response.status_code != 200:
                        return MediaUploadResult(
                            success=False,
                            error=f"Download failed: HTTP {response.status_code} from {url}",
                            error_code="DOWNLOAD_FAILED",
                            inbox_id=self._inbox_id,
                        )

                    content_type = (
                        response.headers.get("content-type", "").split(";")[0].strip()
                    )

                    if not content_type or content_type == "application/octet-stream":
                        return MediaUploadResult(
                            success=False,
                            error=f"Source URL did not provide a usable Content-Type header: {url}",
                            error_code="MIME_TYPE_UNKNOWN",
                            inbox_id=self._inbox_id,
                        )

                    if not self.validate_media_type(content_type):
                        return MediaUploadResult(
                            success=False,
                            error=f"Unsupported MIME type '{content_type}' from source URL. Supported types: {sorted(self.supported_media_types)}",
                            error_code="MIME_TYPE_UNSUPPORTED",
                            inbox_id=self._inbox_id,
                        )

                    max_size = self._get_max_size_for_mime_type(content_type)

                    if (
                        content_length_str := response.headers.get("content-length")
                    ) and int(content_length_str) > max_size:
                        return MediaUploadResult(
                            success=False,
                            error=f"Source file size ({content_length_str} bytes) exceeds the limit ({max_size} bytes) for type {content_type}",
                            error_code="FILE_SIZE_EXCEEDED",
                            inbox_id=self._inbox_id,
                        )

                    data = bytearray()
                    async for chunk in response.aiter_bytes(8192):
                        data.extend(chunk)
                        if len(data) > max_size:
                            return MediaUploadResult(
                                success=False,
                                error=f"Download aborted: file size exceeded {max_size} bytes for type {content_type}",
                                error_code="FILE_SIZE_EXCEEDED",
                                inbox_id=self._inbox_id,
                            )
            finally:
                if owns_client:
                    await download_client.aclose()

            extension_map = self._get_extension_map()
            ext = extension_map.get(content_type, "")
            upload_filename = (
                f"{filename}{ext}" if not filename.endswith(ext) else filename
            )

            self.logger.debug(
                f"Downloaded {len(data)} bytes ({content_type}), re-uploading as {upload_filename}"
            )

            return await self.upload_media_from_bytes(
                file_data=bytes(data),
                media_type=content_type,
                filename=upload_filename,
            )

        except TimeoutError:
            self.logger.warning(f"Download timed out after {timeout}s: {url}")
            return MediaUploadResult(
                success=False,
                error=f"Download timed out after {timeout}s: {url}",
                error_code="DOWNLOAD_FAILED",
                inbox_id=self._inbox_id,
            )
        except Exception as e:
            self.logger.exception(f"Failed to upload media from URL {url}: {e}")
            return MediaUploadResult(
                success=False,
                error=str(e),
                error_code="DOWNLOAD_FAILED",
                inbox_id=self._inbox_id,
            )

    async def get_media_info(self, media_id: str) -> MediaInfoResult:
        try:
            self.logger.debug(f"Fetching media info for ID: {media_id}")

            result = await self.client.get_request(endpoint=f"{media_id}/")

            if not result or "url" not in result:
                return MediaInfoResult(
                    success=False,
                    error=f"Invalid response for media ID {media_id}: {result}",
                    error_code="INVALID_RESPONSE",
                    inbox_id=self._inbox_id,
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
                inbox_id=self._inbox_id,
            )

        except Exception as e:
            self.logger.exception(f"Error getting info for media ID {media_id}: {e}")
            return MediaInfoResult(
                success=False,
                error=str(e),
                error_code="INFO_RETRIEVAL_FAILED",
                inbox_id=self._inbox_id,
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
        try:
            media_info_result = await self.get_media_info(media_id)
            if not media_info_result.success:
                return MediaDownloadResult(
                    success=False,
                    error=f"Failed to get media URL for ID {media_id}: {media_info_result.error}",
                    error_code="MEDIA_INFO_FAILED",
                    inbox_id=self._inbox_id,
                )

            media_url = media_info_result.url
            content_type = media_info_result.mime_type

            self.logger.debug(
                f"Starting download for media ID: {media_id} from URL: {media_url}"
            )

            async with self.client.stream_get(media_url) as response:
                if response.status_code != 200:
                    await response.aread()
                    return MediaDownloadResult(
                        success=False,
                        error=f"Download failed for {media_id}: {response.status_code} - {response.text}",
                        error_code=f"HTTP_{response.status_code}",
                        inbox_id=self._inbox_id,
                    )

                response_content_type = response.headers.get(
                    "content-type", content_type
                )

                try:
                    content_length = int(response.headers.get("content-length", "0"))
                except ValueError:
                    content_length = 0

                if not self.validate_file_size(content_length, response_content_type):
                    max_size = self._get_max_size_for_mime_type(response_content_type)
                    return MediaDownloadResult(
                        success=False,
                        error=f"Media file size ({content_length} bytes) exceeds max allowed ({max_size} bytes) for type {response_content_type}",
                        error_code="FILE_SIZE_EXCEEDED",
                        inbox_id=self._inbox_id,
                    )

                data = bytearray()
                downloaded_size = 0
                max_size = self._get_max_size_for_mime_type(response_content_type)

                async for chunk in response.aiter_bytes(8192):
                    if chunk:
                        downloaded_size += len(chunk)
                        if downloaded_size > max_size:
                            return MediaDownloadResult(
                                success=False,
                                error=f"Download aborted: file size ({downloaded_size}) exceeded max ({max_size}) bytes for type {response_content_type}",
                                error_code="FILE_SIZE_EXCEEDED",
                                inbox_id=self._inbox_id,
                            )
                        data.extend(chunk)

            final_path = None
            is_temp_file = False

            if use_tempfile:
                extension_map = self._get_extension_map()
                extension = temp_suffix or extension_map.get(response_content_type, "")

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
                    with suppress(Exception):
                        os.unlink(temp_path)
                    raise

            elif destination_path:
                extension_map = self._get_extension_map()
                extension = extension_map.get(response_content_type, "")
                media_type_base = response_content_type.split("/")[0]
                timestamp = int(time.time())
                filename_final = (
                    f"{media_type_base}_{sender_id or 'unknown'}_{timestamp}{extension}"
                )

                path = Path(destination_path)
                path.mkdir(parents=True, exist_ok=True)
                final_path = path / filename_final

                with open(final_path, "wb") as f:
                    f.write(data)

                self.logger.info(
                    f"Media successfully downloaded to {final_path} ({downloaded_size} bytes)"
                )

            result = MediaDownloadResult(
                success=True,
                file_data=bytes(data),
                file_path=str(final_path) if final_path else None,
                mime_type=response_content_type,
                file_size=downloaded_size,
                sha256=media_info_result.sha256,
                platform=PlatformType.WHATSAPP,
                inbox_id=self._inbox_id,
            )

            if is_temp_file:
                result.mark_as_temp_file(cleanup_on_exit=auto_cleanup)

            return result

        except Exception as e:
            self.logger.exception(f"Error downloading media ID {media_id}: {e}")
            return MediaDownloadResult(
                success=False,
                error=str(e),
                error_code="DOWNLOAD_FAILED",
                inbox_id=self._inbox_id,
            )

    @asynccontextmanager
    async def download_media_tempfile(
        self,
        media_id: str,
        temp_suffix: str | None = None,
        sender_id: str | None = None,
    ):
        """Download media to a temporary file with automatic cleanup.

        Example:
            async with handler.download_media_tempfile(media_id, '.mp3') as result:
                if result.success:
                    process_audio(result.file_path)  # file auto-deleted on exit
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
            result._cleanup_temp_file()

    async def get_media_as_bytes(self, media_id: str) -> MediaDownloadResult:
        """Download media as bytes without writing to the file system."""
        return await self.download_media(
            media_id=media_id, destination_path=None, use_tempfile=False
        )

    async def stream_media(
        self, media_id: str, chunk_size: int = 8192
    ) -> AsyncIterator[bytes]:
        """Stream media by ID for large files."""
        try:
            media_info_result = await self.get_media_info(media_id)
            if not media_info_result.success:
                raise RuntimeError(
                    f"Failed to get media URL for ID {media_id}: {media_info_result.error}"
                )

            async with self.client.stream_get(media_info_result.url) as response:
                if response.status_code != 200:
                    await response.aread()
                    raise RuntimeError(
                        f"Download failed for {media_id}: {response.status_code} - {response.text}"
                    )

                async for chunk in response.aiter_bytes(chunk_size):
                    if chunk:
                        yield chunk

        except Exception as e:
            self.logger.exception(f"Error streaming media ID {media_id}: {e}")
            raise

    async def delete_media(self, media_id: str) -> MediaDeleteResult:
        try:
            self.logger.debug(f"Attempting to delete media ID: {media_id}")

            result = await self.client.delete_request(endpoint=f"{media_id}")

            if result.get("success"):
                self.logger.info(f"Successfully deleted media ID: {media_id}")
                return MediaDeleteResult(
                    success=True,
                    media_id=media_id,
                    platform=PlatformType.WHATSAPP,
                    inbox_id=self._inbox_id,
                )

            error_msg = result.get("error", {}).get("message", "Unknown reason")
            return MediaDeleteResult(
                success=False,
                media_id=media_id,
                error=f"API indicated deletion failed: {error_msg}",
                error_code="DELETION_FAILED",
                platform=PlatformType.WHATSAPP,
                inbox_id=self._inbox_id,
            )

        except Exception as e:
            self.logger.exception(f"Error deleting media ID {media_id}: {e}")
            return MediaDeleteResult(
                success=False,
                media_id=media_id,
                error=str(e),
                error_code="DELETION_FAILED",
                platform=PlatformType.WHATSAPP,
                inbox_id=self._inbox_id,
            )

    def validate_media_type(self, mime_type: str) -> bool:
        return mime_type in self.supported_media_types

    def validate_file_size(self, file_size: int, mime_type: str) -> bool:
        return file_size <= self._get_max_size_for_mime_type(mime_type)

    def get_media_limits(self) -> dict[str, Any]:
        return {
            "max_sizes": self.max_file_size,
            "supported_types": sorted(self.supported_media_types),
            "url_expiry_minutes": 5,
            "media_persistence_days": 30,
            "platform": "whatsapp",
            "api_version": self.client.api_version,
        }

    def _get_max_size_for_mime_type(self, mime_type: str) -> int:
        if mime_type.startswith("audio/") or mime_type.startswith("video/"):
            return 16 * 1024 * 1024
        if mime_type == "image/webp":
            return 500 * 1024
        if mime_type.startswith("image/"):
            return 5 * 1024 * 1024
        return 100 * 1024 * 1024

    def _get_extension_map(self) -> dict[str, str]:
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
