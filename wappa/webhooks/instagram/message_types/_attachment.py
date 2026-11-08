"""Shared base for Instagram attachment messages (media and shares)."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from wappa.schemas.core.types import UniversalMessageData
from wappa.webhooks.instagram.models import InstagramAttachment

from ._base import InstagramMessageBase


class InstagramAttachmentMessage(InstagramMessageBase):
    """Media evidence is a provider CDN URL, not a WhatsApp media ID."""

    attachments: tuple[InstagramAttachment, ...] = Field(min_length=1)
    text: str | None = None

    @property
    def primary(self) -> InstagramAttachment:
        return self.attachments[0]

    @property
    def url(self) -> str | None:
        return self.primary.url

    @property
    def urls(self) -> tuple[str, ...]:
        return tuple(a.url for a in self.attachments if a.url)

    @property
    def attachment_type(self) -> str:
        return self.primary.type

    @property
    def media_id(self) -> str:
        # Instagram supplies no reusable media ID; the URL is the reference.
        return self.url or ""

    @property
    def file_size(self) -> int | None:
        return None

    @property
    def caption(self) -> str | None:
        return self.text

    def get_download_info(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "urls": list(self.urls),
            "requires_platform_auth": False,
            "may_expire": True,
        }

    def to_universal_dict(self) -> UniversalMessageData:
        from wappa.webhooks.core.base_message.projections import media_projection

        return media_projection(self)
