"""Instagram file (document) message."""

from __future__ import annotations

from pydantic import ConfigDict

from wappa.schemas.core.types import MediaType
from wappa.webhooks.core.base_message import BaseDocumentMessage

from ._attachment import InstagramAttachmentMessage


class InstagramFileMessage(InstagramAttachmentMessage, BaseDocumentMessage):
    model_config = ConfigDict(extra="allow", str_strip_whitespace=False)

    @property
    def media_type(self) -> MediaType:
        return MediaType.DOCUMENT_PDF

    @property
    def filename(self) -> str | None:
        return self.primary.payload.title if self.primary.payload else None

    @property
    def file_extension(self) -> str | None:
        name = self.filename
        return name.rsplit(".", 1)[-1].lower() if name and "." in name else None
