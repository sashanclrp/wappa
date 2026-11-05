"""WhatsApp Media Library over the Cloud API Media endpoints.

``upload`` returns a Media ID (send it with ``send_image(media_id, ...)``);
``download`` resolves an inbound Media ID and returns its bytes.
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

    async def upload(self, source: Path, family: MediaFamily) -> UploadResult:
        _ = family  # WhatsApp infers the media type from the file
        result = await self._handler.upload_media(source)
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

    async def download(self, media_id: str) -> ReadResult[MediaBytes]:
        result = await self._handler.get_media_as_bytes(media_id)
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
        return ReadResult(
            outcome=ReadOutcome.UNAVAILABLE,
            error=result.error or "WhatsApp media download failed",
            error_code=result.error_code,
        )


__all__ = ["WhatsAppMediaLibrary"]
