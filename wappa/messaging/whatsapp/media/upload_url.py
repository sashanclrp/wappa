"""Media upload from a public URL: download it, then re-upload to WhatsApp."""

from __future__ import annotations

from wappa.domain.models.media_result import MediaUploadResult
from wappa.messaging.whatsapp.media.upload import _UploadMixin
from wappa.resilience.rate_limits import RateLimitedError
from wappa.schemas.core.types import PlatformType


class _UrlUploadMixin(_UploadMixin):
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

            async with self._media_download_client.stream(
                "GET", url, timeout=timeout
            ) as response:
                if response.status_code != 200:
                    return MediaUploadResult(
                        platform=PlatformType.WHATSAPP,
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
                        platform=PlatformType.WHATSAPP,
                        success=False,
                        error=f"Source URL did not provide a usable Content-Type header: {url}",
                        error_code="MIME_TYPE_UNKNOWN",
                        inbox_id=self._inbox_id,
                    )

                if not self.validate_media_type(content_type):
                    return MediaUploadResult(
                        platform=PlatformType.WHATSAPP,
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
                        platform=PlatformType.WHATSAPP,
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
                            platform=PlatformType.WHATSAPP,
                            success=False,
                            error=f"Download aborted: file size exceeded {max_size} bytes for type {content_type}",
                            error_code="FILE_SIZE_EXCEEDED",
                            inbox_id=self._inbox_id,
                        )
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
                platform=PlatformType.WHATSAPP,
                success=False,
                error=f"Download timed out after {timeout}s: {url}",
                error_code="DOWNLOAD_FAILED",
                inbox_id=self._inbox_id,
            )
        except RateLimitedError:
            raise  # the caller maps it to rate_limited
        except Exception as e:
            self.logger.exception(f"Failed to upload media from URL {url}: {e}")
            return MediaUploadResult(
                platform=PlatformType.WHATSAPP,
                success=False,
                error=str(e),
                error_code="DOWNLOAD_FAILED",
                inbox_id=self._inbox_id,
            )
