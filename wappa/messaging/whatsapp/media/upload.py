"""Media upload: from a file, bytes, a stream or a public URL."""

from __future__ import annotations

import mimetypes
from pathlib import Path

from wappa.domain.models.media_result import MediaUploadResult
from wappa.messaging.meta.graph import MetaGraphError
from wappa.messaging.whatsapp.media._base import _MediaTransportBase
from wappa.resilience.rate_limits import RateLimitedError
from wappa.schemas.core.types import PlatformType


class _UploadMixin(_MediaTransportBase):
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
                    platform=PlatformType.WHATSAPP,
                    success=False,
                    error=f"Media file not found: {media_path}",
                    error_code="FILE_NOT_FOUND",
                    inbox_id=self._inbox_id,
                )

            if media_type is None:
                media_type = mimetypes.guess_type(media_path)[0]
                if not media_type:
                    return MediaUploadResult(
                        platform=PlatformType.WHATSAPP,
                        success=False,
                        error=f"Could not determine MIME type for file: {media_path}",
                        error_code="MIME_TYPE_UNKNOWN",
                        inbox_id=self._inbox_id,
                    )

            if not self.validate_media_type(media_type):
                return MediaUploadResult(
                    platform=PlatformType.WHATSAPP,
                    success=False,
                    error=f"Unsupported MIME type '{media_type}'. Supported types: {sorted(self.supported_media_types)}",
                    error_code="MIME_TYPE_UNSUPPORTED",
                    inbox_id=self._inbox_id,
                )

            file_size = media_path.stat().st_size
            if not self.validate_file_size(file_size, media_type):
                max_size = self._get_max_size_for_mime_type(media_type)
                return MediaUploadResult(
                    platform=PlatformType.WHATSAPP,
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
                    platform=PlatformType.WHATSAPP,
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

        except RateLimitedError:
            raise  # the caller maps it to rate_limited
        except MetaGraphError as e:
            # Classified once by MetaGraphClient: keep rejected vs unknown.
            self.logger.warning(f"Media upload failed: {e}")
            return MediaUploadResult(
                platform=PlatformType.WHATSAPP,
                success=False,
                error=str(e),
                error_code="INDETERMINATE"
                if e.indeterminate
                else e.code or "UPLOAD_FAILED",
                inbox_id=self._inbox_id,
            )
        except Exception as e:
            self.logger.exception(f"Failed to upload {file_path}: {e}")
            return MediaUploadResult(
                platform=PlatformType.WHATSAPP,
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
                    platform=PlatformType.WHATSAPP,
                    success=False,
                    error=f"Unsupported MIME type '{media_type}'. Supported types: {sorted(self.supported_media_types)}",
                    error_code="MIME_TYPE_UNSUPPORTED",
                    inbox_id=self._inbox_id,
                )

            file_size = len(file_data)
            if not self.validate_file_size(file_size, media_type):
                max_size = self._get_max_size_for_mime_type(media_type)
                return MediaUploadResult(
                    platform=PlatformType.WHATSAPP,
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
                    platform=PlatformType.WHATSAPP,
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

        except RateLimitedError:
            raise  # the caller maps it to rate_limited
        except MetaGraphError as e:
            # Classified once by MetaGraphClient: keep rejected vs unknown.
            self.logger.warning(f"Media upload failed: {e}")
            return MediaUploadResult(
                platform=PlatformType.WHATSAPP,
                success=False,
                error=str(e),
                error_code="INDETERMINATE"
                if e.indeterminate
                else e.code or "UPLOAD_FAILED",
                inbox_id=self._inbox_id,
            )
        except Exception as e:
            self.logger.exception(f"Failed to upload {filename} from bytes: {e}")
            return MediaUploadResult(
                platform=PlatformType.WHATSAPP,
                success=False,
                error=str(e),
                error_code="UPLOAD_FAILED",
                inbox_id=self._inbox_id,
            )
