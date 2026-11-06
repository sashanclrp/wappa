"""WhatsApp Media Library over the Cloud API Media endpoints.

``upload`` takes a file or bytes, returns a Media ID (send it with
``send_image(media_id, ...)``) and passes ``mime_type`` to the Media API
(guessed from the file name and family when ``None``); ``download``
resolves an inbound Media ID and returns its bytes, bounded by ``max_bytes``
and the WhatsApp per-type limit; ``info`` is ``GET /{media_id}`` and
``delete`` is ``DELETE /{media_id}``.
"""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import TYPE_CHECKING

from wappa.domain.interfaces.conversation_capabilities import (
    MediaBytes,
    ReadOutcome,
    ReadResult,
)
from wappa.domain.interfaces.media_library import (
    DeleteResult,
    IMediaLibrary,
    MediaFamily,
    MediaInfo,
    UploadResult,
)
from wappa.domain.results import OperationOutcome
from wappa.messaging.whatsapp.media.rules import check_bytes, check_file
from wappa.resilience.rate_limits import RateLimitedError
from wappa.schemas.core.types import PlatformType

if TYPE_CHECKING:
    from wappa.messaging.whatsapp.media.transport import (
        WhatsAppMediaTransport,
    )


def _guess_mime(name: str, family: MediaFamily) -> str | None:
    """The MIME type for ``name``, read in the light of the upload's family.

    Python maps ``.3gp`` to ``audio/3gpp``, which WhatsApp refuses for a video
    (131053); a video upload sends ``video/3gpp`` instead.
    """
    mime = mimetypes.guess_type(name)[0]
    if family is MediaFamily.VIDEO and mime == "audio/3gpp":
        return "video/3gpp"
    return mime


class WhatsAppMediaLibrary(IMediaLibrary):
    def __init__(self, media_transport: WhatsAppMediaTransport, inbox_id: str) -> None:
        self._handler = media_transport
        self._inbox_id = inbox_id

    async def upload(
        self,
        source: Path | bytes,
        family: MediaFamily,
        *,
        mime_type: str | None = None,
        filename: str | None = None,
    ) -> UploadResult:
        use = family.value
        # An explicit mime_type overrides the name; the content is checked anyway.
        if isinstance(source, bytes):
            check_bytes(source, use, name=None if mime_type else filename)
        else:
            check_file(source, use, by_name=mime_type is None)
        try:
            if isinstance(source, bytes):
                name = filename or "upload"
                mime = mime_type or _guess_mime(name, family)
                if mime is None:
                    raise ValueError(
                        "WhatsApp byte uploads need a mime_type or a filename with "
                        "a known extension"
                    )
                result = await self._handler.upload_media_from_bytes(source, mime, name)
            else:
                result = await self._handler.upload_media(
                    source,
                    media_type=mime_type
                    or _guess_mime(filename or source.name, family),
                    filename=filename,
                )
        except RateLimitedError as limited:
            return UploadResult(
                outcome=OperationOutcome.RATE_LIMITED,
                platform=PlatformType.WHATSAPP,
                inbox_id=self._inbox_id,
                error=str(limited),
                error_code=limited.code,
                retry_after=limited.retry_after,
            )
        if result.success and result.media_id:
            return UploadResult(
                outcome=OperationOutcome.ACCEPTED,
                platform=PlatformType.WHATSAPP,
                inbox_id=self._inbox_id,
                media_id=result.media_id,
            )
        return UploadResult(
            outcome=OperationOutcome.INDETERMINATE
            if result.error_code == "INDETERMINATE"
            else OperationOutcome.REJECTED,
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

    async def info(self, media_id: str) -> ReadResult[MediaInfo]:
        result = await self._handler.get_media_info(media_id)
        if result.success:
            return ReadResult(
                outcome=ReadOutcome.FOUND,
                value=MediaInfo(
                    media_id=result.media_id or media_id,
                    url=result.url,
                    mime_type=result.mime_type,
                    size=result.file_size,
                    sha256=result.sha256,
                ),
            )
        return ReadResult(
            outcome=_failure_outcome(result.error_code),
            error=result.error or "WhatsApp media info failed",
            error_code=result.error_code,
        )

    async def delete(self, media_id: str) -> DeleteResult:
        result = await self._handler.delete_media(media_id)
        if result.success:
            outcome = OperationOutcome.ACCEPTED
        elif result.error_code == "DELETION_FAILED":
            outcome = OperationOutcome.INDETERMINATE  # transport error or no answer
        else:
            outcome = OperationOutcome.REJECTED
        return DeleteResult(
            outcome=outcome,
            platform=PlatformType.WHATSAPP,
            inbox_id=self._inbox_id,
            media_id=media_id,
            error=result.error,
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
