"""Media download: bytes, a file, a temp file or a stream."""

from __future__ import annotations

import os
import tempfile
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from wappa.domain.models.media_result import MediaDownloadResult
from wappa.messaging.whatsapp.media.info import _InfoMixin
from wappa.schemas.core.types import PlatformType


class _DownloadMixin(_InfoMixin):
    async def download_media(
        self,
        media_id: str,
        destination_path: str | Path | None = None,
        sender_id: str | None = None,
        use_tempfile: bool = False,
        temp_suffix: str | None = None,
        auto_cleanup: bool = True,
        max_bytes: int | None = None,
    ) -> MediaDownloadResult:
        """Download media by ID; ``max_bytes`` lowers the per-type size limit."""
        try:
            media_info_result = await self.get_media_info(media_id)
            if not media_info_result.success:
                return MediaDownloadResult(
                    platform=PlatformType.WHATSAPP,
                    success=False,
                    error=f"Failed to get media URL for ID {media_id}: {media_info_result.error}",
                    error_code=_info_failure_code(media_info_result.error_code),
                    inbox_id=self._inbox_id,
                )

            media_url = media_info_result.url
            if media_url is None:
                return MediaDownloadResult(
                    platform=PlatformType.WHATSAPP,
                    success=False,
                    error=f"Media URL missing for ID {media_id}",
                    error_code="MEDIA_URL_MISSING",
                    inbox_id=self._inbox_id,
                )
            content_type = media_info_result.mime_type

            self.logger.debug(
                f"Starting download for media ID: {media_id} from URL: {media_url}"
            )

            async with self.client.stream_get(media_url) as response:
                if response.status_code != 200:
                    await response.aread()
                    return MediaDownloadResult(
                        platform=PlatformType.WHATSAPP,
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

                max_size = self._get_max_size_for_mime_type(response_content_type)
                if max_bytes is not None:
                    max_size = min(max_size, max_bytes)
                if content_length > max_size:
                    return MediaDownloadResult(
                        platform=PlatformType.WHATSAPP,
                        success=False,
                        error=f"Media file size ({content_length} bytes) exceeds max allowed ({max_size} bytes) for type {response_content_type}",
                        error_code="FILE_SIZE_EXCEEDED",
                        inbox_id=self._inbox_id,
                    )

                data = bytearray()
                downloaded_size = 0

                async for chunk in response.aiter_bytes(8192):
                    if chunk:
                        downloaded_size += len(chunk)
                        if downloaded_size > max_size:
                            return MediaDownloadResult(
                                platform=PlatformType.WHATSAPP,
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
                platform=PlatformType.WHATSAPP,
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
    ) -> AsyncIterator[MediaDownloadResult]:
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

    async def get_media_as_bytes(
        self, media_id: str, *, max_bytes: int | None = None
    ) -> MediaDownloadResult:
        """Download media as bytes without writing to the file system."""
        return await self.download_media(
            media_id=media_id,
            destination_path=None,
            use_tempfile=False,
            max_bytes=max_bytes,
        )


def _info_failure_code(info_error_code: str | None) -> str:
    """Keep a media-info failure's cause: Graph's ``HTTP_<status>`` or a URL-less
    answer pass through; a timeout or transport error is ``MEDIA_INFO_FAILED``."""
    if info_error_code is not None and (
        info_error_code.startswith("HTTP_") or info_error_code == "INVALID_RESPONSE"
    ):
        return info_error_code
    return "MEDIA_INFO_FAILED"
