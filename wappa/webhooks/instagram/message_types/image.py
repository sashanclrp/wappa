"""Instagram image message (sticker-aware)."""

from __future__ import annotations

from pydantic import ConfigDict

from wappa.schemas.core.types import MediaType
from wappa.webhooks.core.base_message import BaseImageMessage

from ._attachment import InstagramAttachmentMessage


class InstagramImageMessage(InstagramAttachmentMessage, BaseImageMessage):
    model_config = ConfigDict(extra="allow", str_strip_whitespace=False)

    @property
    def media_type(self) -> MediaType:
        # Nominal: Instagram webhooks carry no MIME; MediaBytes has the real one.
        return MediaType.IMAGE_JPEG

    @property
    def is_sticker(self) -> bool:
        return bool(self.primary.payload and self.primary.payload.sticker_id)
