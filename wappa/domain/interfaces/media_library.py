"""Media Library: store and fetch media files for an Inbox (ADR-0016).

A separate responsibility from sending messages. Every Platform that keeps
reusable media implements it:

- ``upload(path, family, *, mime_type=None)`` stores a local file and
  returns a reusable ``media_id``. Pass that ID to the Messenger's
  ``send_image`` / ``send_video`` / ``send_audio`` / ``send_document`` on the
  same Inbox. ``mime_type`` is honoured where the Platform takes one
  (WhatsApp) and ignored otherwise. A local-rule violation raises
  ``ValueError``; a Platform refusal returns ``REJECTED``.
- ``download(media_id, *, max_bytes=None)`` reads an inbound media message's
  bytes. Pass ``webhook.message.media_id`` unchanged. ``max_bytes`` bounds
  the read (the Platform default applies when ``None``); an oversize read
  returns ``REJECTED`` with ``error_code="SIZE"``.

Reach it with ``messenger.require_capability(IMediaLibrary)``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import StrEnum
from pathlib import Path

from wappa.domain.interfaces.conversation_capabilities import MediaBytes, ReadResult
from wappa.domain.results import _ProviderResult


class MediaFamily(StrEnum):
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    DOCUMENT = "document"


class UploadResult(_ProviderResult):
    """Upload evidence; ``media_id`` is present only when accepted."""

    media_id: str | None = None


class IMediaLibrary(ABC):
    """Inbox-bound media storage: upload once, send by ID; read inbound media."""

    @abstractmethod
    async def upload(
        self, source: Path, family: MediaFamily, *, mime_type: str | None = None
    ) -> UploadResult: ...

    @abstractmethod
    async def download(
        self, media_id: str, *, max_bytes: int | None = None
    ) -> ReadResult[MediaBytes]: ...


__all__ = ["IMediaLibrary", "MediaFamily", "UploadResult"]
