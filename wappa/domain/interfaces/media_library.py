"""Media Library: store, inspect and fetch media files for an Inbox (ADR-0016).

A separate responsibility from sending messages, shaped like the WhatsApp
Cloud API Media endpoints. Every Platform that keeps reusable media
implements it:

- ``upload(source, family, *, mime_type=None, filename=None)`` stores a local
  file (``Path``) or raw ``bytes`` and returns a reusable ``media_id``. Pass
  that ID to the Messenger's ``send_image`` / ``send_video`` / ``send_audio``
  / ``send_document`` / ``send_sticker`` on the same Inbox. ``mime_type`` is
  honoured where the Platform takes one (WhatsApp); ``filename`` names a
  ``bytes`` upload (a ``Path`` keeps its own name). A local-rule violation
  raises ``ValueError``; a Platform refusal returns ``REJECTED``.
- ``download(media_id, *, max_bytes=None)`` reads an inbound media message's
  bytes. Pass ``webhook.message.media_id`` unchanged. ``max_bytes`` bounds
  the read (the Platform default applies when ``None``); an oversize read
  returns ``REJECTED`` with ``error_code="SIZE"``.
- ``info(media_id)`` describes a stored media file (URL, MIME type, size,
  SHA-256) and ``delete(media_id)`` removes it. A Platform without such an
  endpoint raises ``UnsupportedOperationError`` (Instagram has neither).

Reach it with ``messenger.require_capability(IMediaLibrary)``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from wappa.domain.interfaces.conversation_capabilities import MediaBytes, ReadResult
from wappa.domain.results import _ProviderResult


class MediaFamily(StrEnum):
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    DOCUMENT = "document"
    STICKER = "sticker"


class UploadResult(_ProviderResult):
    """Upload evidence; ``media_id`` is present only when accepted."""

    media_id: str | None = None


class MediaInfo(BaseModel):
    """What the Platform holds for one stored media file.

    ``url`` is the Platform's short-lived retrieval URL (WhatsApp: about five
    minutes, fetched with the Inbox token); use ``download`` for the bytes.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    media_id: str
    url: str | None = None
    mime_type: str | None = None
    size: int | None = None
    sha256: str | None = None


class DeleteResult(_ProviderResult):
    """Evidence of a media deletion; ``success`` only when the Platform confirmed."""

    media_id: str


class IMediaLibrary(ABC):
    """Inbox-bound media storage: upload once, send by ID; read inbound media."""

    @abstractmethod
    async def upload(
        self,
        source: Path | bytes,
        family: MediaFamily,
        *,
        mime_type: str | None = None,
        filename: str | None = None,
    ) -> UploadResult: ...

    @abstractmethod
    async def download(
        self, media_id: str, *, max_bytes: int | None = None
    ) -> ReadResult[MediaBytes]: ...

    @abstractmethod
    async def info(self, media_id: str) -> ReadResult[MediaInfo]: ...

    @abstractmethod
    async def delete(self, media_id: str) -> DeleteResult: ...


__all__ = [
    "DeleteResult",
    "IMediaLibrary",
    "MediaFamily",
    "MediaInfo",
    "UploadResult",
]
