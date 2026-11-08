"""Instagram Media Library: reusable attachment upload and CDN reads.

- ``upload``: ``POST /{ig}/message_attachments`` with ``is_reusable`` →
  ``attachment_id`` (send it with ``send_image(attachment_id, ...)`` etc.).
  A file or bytes go up as multipart; a sticker uploads as an image (Instagram
  has no stickers).
- ``download``: the attachment URL Instagram delivered, fetched without
  credentials from allowed Meta CDN hosts, bounded by ``max_bytes``.
- ``info`` / ``delete``: ``UnsupportedOperationError``; Instagram has no
  endpoint to describe or delete an uploaded attachment.

Instagram's rules key off the file suffix of the name the file goes out
with: ``filename`` when given (a ``Path`` lends its suffix to a ``filename``
without one), else the ``Path``'s own name, else for ``bytes`` a name built
from ``mime_type``. The name is transliterated to ASCII with its extension
kept, and ``mime_type`` (else the type guessed from the name) is the upload's
content type.
"""

from __future__ import annotations

import json
from contextlib import nullcontext
from dataclasses import replace
from pathlib import Path

from wappa.domain.interfaces.conversation_capabilities import MediaBytes, ReadResult
from wappa.domain.interfaces.media_library import (
    DeleteResult,
    IMediaLibrary,
    MediaFamily,
    MediaInfo,
    UploadResult,
)
from wappa.domain.messaging_targets import UnsupportedOperationError
from wappa.domain.results import OperationOutcome
from wappa.schemas.core.types import PlatformType

from ..client import InstagramClient
from .rules import (
    ascii_name,
    check_upload_content,
    mime_for,
    upload_name,
    validate_local_file,
    validate_upload,
)
from .transport import InstagramAttachmentReader


class InstagramMediaLibrary(IMediaLibrary):
    def __init__(
        self, graph: InstagramClient, reader: InstagramAttachmentReader
    ) -> None:
        self._graph = graph
        self._reader = reader

    async def upload(
        self,
        source: Path | bytes,
        family: MediaFamily,
        *,
        mime_type: str | None = None,
        filename: str | None = None,
    ) -> UploadResult:
        # Instagram has no stickers: a sticker is stored (and sent) as an image.
        kind = "image" if family is MediaFamily.STICKER else family.value
        if isinstance(source, bytes):
            name = upload_name(filename, mime_type)
            rule = validate_upload(name, len(source), kind)
        else:
            name = upload_name(filename, mime_type, path=source)
            rule = validate_local_file(source, kind, name=name)
        if rule.wire_type in ("image", "video"):
            check_upload_content(
                source if isinstance(source, bytes) else source.read_bytes(),
                rule.wire_type,
            )
        name = ascii_name(name)
        message = {
            "attachment": {"type": rule.wire_type, "payload": {"is_reusable": True}}
        }
        opened = source.open("rb") if isinstance(source, Path) else nullcontext(source)
        with opened as content:
            response = await self._graph.request(
                "POST",
                self._graph.attachments_path,
                data={"platform": "instagram", "message": json.dumps(message)},
                files={"filedata": (name, content, mime_type or mime_for(name))},
                operation=f"Instagram {family.value} upload",
                timeout=120.0,
            )
        attachment_id = response.body.get("attachment_id") if response.ok else None
        if isinstance(attachment_id, str) and attachment_id:
            return UploadResult(
                outcome=OperationOutcome.ACCEPTED,
                platform=PlatformType.INSTAGRAM,
                inbox_id=self._graph.account_id,
                media_id=attachment_id,
                platform_response=response.body or None,
            )
        outcome = OperationOutcome.INDETERMINATE if response.ok else response.outcome
        return UploadResult(
            outcome=outcome,
            platform=PlatformType.INSTAGRAM,
            inbox_id=self._graph.account_id,
            error=response.error
            or f"Instagram {family.value} upload returned no attachment_id",
            error_code=response.error_code or "INDETERMINATE",
            retry_after=response.retry_after,
            error_evidence=replace(response, outcome=outcome).error_evidence,
            platform_response=response.body or None,
        )

    async def download(
        self, media_id: str, *, max_bytes: int | None = None
    ) -> ReadResult[MediaBytes]:
        return await self._reader.get_bytes(media_id, max_bytes=max_bytes)

    async def info(self, media_id: str) -> ReadResult[MediaInfo]:
        raise UnsupportedOperationError(
            "Instagram has no endpoint to describe an uploaded attachment"
        )

    async def delete(self, media_id: str) -> DeleteResult:
        raise UnsupportedOperationError(
            "Instagram has no endpoint to delete an uploaded attachment"
        )


__all__ = ["InstagramMediaLibrary"]
