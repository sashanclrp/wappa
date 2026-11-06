"""Media upload over HTTP for every Platform (ADR-0021).

Every Platform uploads through its Messenger's ``IMediaLibrary``; the
multipart ``media_type`` reaches it as ``mime_type`` (WhatsApp honours it).
A Platform without a media library answers 501.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import Depends

from wappa.api.dependencies.inbox_context import (
    InboxExecutionContext,
    get_inbox_execution_context,
    requires_capability,
)
from wappa.domain.interfaces.media_library import IMediaLibrary, MediaFamily
from wappa.domain.models.media_result import MediaUploadResult
from wappa.schemas.core.types import PlatformType


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
                result = await self._library.upload(path, family, mime_type=media_type)
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
    library: IMediaLibrary = Depends(requires_capability(IMediaLibrary)),
    context: InboxExecutionContext = Depends(get_inbox_execution_context),
) -> LibraryMediaUploader:
    """The selected Inbox's ``IMediaLibrary`` uploader, or 501."""
    return LibraryMediaUploader(library, context.inbox_ref.platform, context.inbox_id)


__all__ = [
    "LibraryMediaUploader",
    "get_media_uploader",
    "media_family",
]
