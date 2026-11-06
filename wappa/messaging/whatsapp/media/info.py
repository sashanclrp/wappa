"""Media info and delete (``GET`` and ``DELETE /{media_id}``)."""

from __future__ import annotations

from wappa.domain.models.media_result import MediaDeleteResult, MediaInfoResult
from wappa.messaging.meta.graph import MetaGraphError
from wappa.messaging.whatsapp.media._base import _MediaTransportBase
from wappa.schemas.core.types import PlatformType


class _InfoMixin(_MediaTransportBase):
    async def get_media_info(self, media_id: str) -> MediaInfoResult:
        try:
            self.logger.debug(f"Fetching media info for ID: {media_id}")

            result = await self.client.get_request(endpoint=f"{media_id}/")

            if not result or "url" not in result:
                return MediaInfoResult(
                    platform=PlatformType.WHATSAPP,
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

        except MetaGraphError as e:
            # Keep Graph's status so a caller can tell an unknown Media ID
            # (400/404) or a refused token (401/403) from an outage (5xx).
            self.logger.warning(f"Media info for ID {media_id} failed: {e}")
            return MediaInfoResult(
                platform=PlatformType.WHATSAPP,
                success=False,
                error=str(e),
                error_code=f"HTTP_{e.status_code}"
                if e.status_code
                else "INDETERMINATE",
                inbox_id=self._inbox_id,
            )
        except Exception as e:
            self.logger.exception(f"Error getting info for media ID {media_id}: {e}")
            return MediaInfoResult(
                platform=PlatformType.WHATSAPP,
                success=False,
                error=str(e),
                error_code="INFO_RETRIEVAL_FAILED",
                inbox_id=self._inbox_id,
            )

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
                error_code="DELETION_REJECTED",
                platform=PlatformType.WHATSAPP,
                inbox_id=self._inbox_id,
            )

        except MetaGraphError as e:
            # Keep Graph's status: an unknown Media ID (400/404) or a refused
            # token (401/403) is a refusal, not an unknown outcome; a 5xx or
            # transport failure is (DELETION_FAILED → indeterminate).
            self.logger.warning(f"Deleting media ID {media_id} failed: {e}")
            return MediaDeleteResult(
                success=False,
                media_id=media_id,
                error=str(e),
                error_code="DELETION_FAILED"
                if e.indeterminate
                else f"HTTP_{e.status_code}",
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
