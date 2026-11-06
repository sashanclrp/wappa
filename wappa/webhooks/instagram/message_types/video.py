"""Instagram video message."""

from __future__ import annotations

from pydantic import ConfigDict

from wappa.schemas.core.types import MediaType
from wappa.webhooks.core.base_message import BaseVideoMessage

from ._attachment import InstagramAttachmentMessage


class InstagramVideoMessage(InstagramAttachmentMessage, BaseVideoMessage):
    model_config = ConfigDict(extra="allow", str_strip_whitespace=False)

    @property
    def media_type(self) -> MediaType:
        return MediaType.VIDEO_MP4

    @property
    def duration(self) -> int | None:
        return None

    @property
    def dimensions(self) -> tuple[int, int] | None:
        return None
