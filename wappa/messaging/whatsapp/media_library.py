"""WhatsApp Media Library over the Cloud API Media endpoints.

``upload`` returns a Media ID (send it with ``send_image(media_id, ...)``) and
passes ``mime_type`` to the Media API; ``download`` resolves an inbound Media
ID and returns its bytes, bounded by ``max_bytes`` and the WhatsApp per-type
limit.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from wappa.domain.interfaces.conversation_capabilities import (
    MediaBytes,
    ReadOutcome,
    ReadResult,
)
from wappa.domain.interfaces.media_library import (
    IMediaLibrary,
    MediaFamily,
    UploadResult,
)
from wappa.domain.results import OperationOutcome
from wappa.schemas.core.types import PlatformType

if TYPE_CHECKING:
    from wappa.messaging.whatsapp.handlers.whatsapp_media_handler import (
        WhatsAppMediaHandler,
    )


class WhatsAppMediaLibrary(IMediaLibrary):
    def __init__(self, media_handler: WhatsAppMediaHandler, inbox_id: str) -> None:
        self._handler = media_handler
        self._inbox_id = inbox_id

    async def upload(
        self, source: Path, family: MediaFamily, *, mime_type: str | None = None
    ) -> UploadResult:
        _ = family  # WhatsApp takes the MIME type, inferred from the file if None
        result = await self._handler.upload_media(source, media_type=mime_type)
        if result.success and result.media_id:
            return UploadResult(
                outcome=OperationOutcome.ACCEPTED,
                platform=PlatformType.WHATSAPP,
                inbox_id=self._inbox_id,
                media_id=result.media_id,
            )
        return UploadResult(
            outcome=OperationOutcome.REJECTED,
            platform=PlatformType.WHATSAPP,
            inbox_id=self._inbox_id,
            error=result.error or "WhatsApp media upload failed",
            error_code=result.error_code,
        )

    async def download(
        self, media_id: str, *, max_bytes: int | None = None
    ) -> ReadResult[MediaBytes]:
        result = await self._handler.get_media_as_bytes(media_id, max_bytes=max_bytes)
        if result.success and result.file_data is not None:
            return ReadResult(
                outcome=ReadOutcome.FOUND,
                value=MediaBytes(
                    content=result.file_data,
                    content_type=result.mime_type,
                    size=result.file_size or len(result.file_data),
                    source_host="graph.facebook.com",
                ),
            )
        if result.error_code == "FILE_SIZE_EXCEEDED":
            return ReadResult(
                outcome=ReadOutcome.REJECTED, error=result.error, error_code="SIZE"
            )
        return ReadResult(
            outcome=_failure_outcome(result.error_code),
            error=result.error or "WhatsApp media download failed",
            error_code=result.error_code,
        )


# A Media ID Graph rejects (400/404), an info answer without a URL, or a CDN 404
# is gone for good; callers must not retry it as an outage. A 401/403 from Graph
# or the CDN is ACCESS_DENIED. Timeouts, 5xx and transport errors (including
# MEDIA_INFO_FAILED) stay UNAVAILABLE.
_NOT_FOUND_CODES = frozenset(
    {"INVALID_RESPONSE", "MEDIA_URL_MISSING", "HTTP_400", "HTTP_404"}
)
_ACCESS_DENIED_CODES = frozenset({"HTTP_401", "HTTP_403"})


def _failure_outcome(error_code: str | None) -> ReadOutcome:
    if error_code in _NOT_FOUND_CODES:
        return ReadOutcome.NOT_FOUND
    if error_code in _ACCESS_DENIED_CODES:
        return ReadOutcome.ACCESS_DENIED
    if error_code is not None and error_code.startswith("HTTP_4"):
        return ReadOutcome.REJECTED
    return ReadOutcome.UNAVAILABLE


__all__ = ["WhatsAppMediaLibrary"]
