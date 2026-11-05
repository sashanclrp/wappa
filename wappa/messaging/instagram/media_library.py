"""Instagram Media Library: reusable attachment upload and CDN reads.

- ``upload``: ``POST /{ig}/message_attachments`` with ``is_reusable`` →
  ``attachment_id`` (send it with ``send_image(attachment_id, ...)`` etc.).
- ``download``: the attachment URL Instagram delivered, fetched without
  credentials from allowed Meta CDN hosts.
"""

from __future__ import annotations

import json
from pathlib import Path

from wappa.domain.interfaces.conversation_capabilities import MediaBytes, ReadResult
from wappa.domain.interfaces.media_library import (
    IMediaLibrary,
    MediaFamily,
    UploadResult,
)
from wappa.domain.results import OperationOutcome
from wappa.schemas.core.types import PlatformType

from .graph import InstagramGraphClient
from .media import InstagramAttachmentReader, mime_for, validate_local_file


class InstagramMediaLibrary(IMediaLibrary):
    def __init__(
        self, graph: InstagramGraphClient, reader: InstagramAttachmentReader
    ) -> None:
        self._graph = graph
        self._reader = reader

    async def upload(self, source: Path, family: MediaFamily) -> UploadResult:
        rule = validate_local_file(source, family.value)
        message = {
            "attachment": {"type": rule.wire_type, "payload": {"is_reusable": True}}
        }
        with source.open("rb") as handle:
            response = await self._graph.request(
                "POST",
                f"{self._graph.account_id}/message_attachments",
                data={"platform": "instagram", "message": json.dumps(message)},
                files={"filedata": (source.name, handle, mime_for(source))},
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
            platform_response=response.body or None,
        )

    async def download(self, media_id: str) -> ReadResult[MediaBytes]:
        return await self._reader.get_bytes(media_id)


__all__ = ["InstagramMediaLibrary"]
