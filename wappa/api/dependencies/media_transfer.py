"""Media upload over HTTP for every Platform (ADR-0021).

WhatsApp keeps its Media API handler, which honours an explicit ``media_type``
from the multipart form. Other Platforms upload through their Messenger's
``IMediaLibrary`` behind the same ``upload_media_from_bytes`` call, so the
route stays one route. A Platform without a media library answers 501.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Protocol

from fastapi import Depends, HTTPException, Request

from wappa.api.dependencies.inbox_context import (
    InboxExecutionContext,
    get_inbox_execution_context,
)
from wappa.domain.interfaces.media_library import IMediaLibrary, MediaFamily
from wappa.domain.models.media_result import MediaUploadResult
from wappa.messaging.whatsapp.handlers.whatsapp_media_handler import (
    WhatsAppMediaHandler,
)
from wappa.schemas.core.types import PlatformType


class MediaUploader(Protocol):
    async def upload_media_from_bytes(
        self, file_data: bytes, media_type: str, filename: str
    ) -> MediaUploadResult: ...


def media_family(media_type: str) -> MediaFamily | None:
    major = media_type.split("/", 1)[0].lower()
    if major in {"image", "video", "audio"}:
        return MediaFamily(major)
    if media_type.lower().startswith(("application/", "text/")):
        return MediaFamily.DOCUMENT
    return None


class LibraryMediaUploader:
    """``upload_media_from_bytes`` over a Platform's ``IMediaLibrary``."""

    def __init__(self, library: IMediaLibrary, platform: PlatformType, inbox_id: str):
        self._library = library
        self._platform = platform
        self._inbox_id = inbox_id

    async def upload_media_from_bytes(
        self, file_data: bytes, media_type: str, filename: str
    ) -> MediaUploadResult:
        family = media_family(media_type)
        if family is None:
            return self._failed(
                f"Unsupported media type {media_type}", "MIME_TYPE_UNSUPPORTED"
            )
        name = Path(filename).name or "upload"
        with tempfile.TemporaryDirectory(prefix="wappa-upload-") as folder:
            path = Path(folder) / name
            path.write_bytes(file_data)
            try:
                result = await self._library.upload(path, family)
            except ValueError as exc:  # local Platform rule (format, size, name)
                return self._failed(str(exc), "MEDIA_REJECTED")
        return MediaUploadResult(
            success=result.success,
            platform=self._platform,
            media_id=result.media_id,
            mime_type=media_type,
            file_size=len(file_data),
            error=result.error,
            error_code=result.error_code,
            inbox_id=self._inbox_id,
        )

    def _failed(self, error: str, code: str) -> MediaUploadResult:
        return MediaUploadResult(
            success=False,
            platform=self._platform,
            error=error,
            error_code=code,
            inbox_id=self._inbox_id,
        )


async def get_media_uploader(
    request: Request,
    context: InboxExecutionContext = Depends(get_inbox_execution_context),
) -> MediaUploader:
    """The selected Inbox's uploader: WhatsApp Media API, or ``IMediaLibrary``."""
    if context.inbox_ref.platform is PlatformType.WHATSAPP:
        return WhatsAppMediaHandler(
            client=context.whatsapp_client(),
            inbox_id=context.inbox_id,
            media_download_client=context.media_download_client_provider(),
        )
    messenger = await context.messenger(request.app)
    library = messenger.capability(IMediaLibrary)
    if library is None:
        raise HTTPException(
            status_code=501,
            detail=f"{context.inbox_ref.platform.value} does not provide IMediaLibrary",
        )
    return LibraryMediaUploader(library, context.inbox_ref.platform, context.inbox_id)


__all__ = [
    "LibraryMediaUploader",
    "MediaUploader",
    "get_media_uploader",
    "media_family",
]
