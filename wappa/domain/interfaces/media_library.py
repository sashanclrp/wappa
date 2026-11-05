"""Media Library: store and fetch media files for an Inbox (ADR-0016).

A separate responsibility from sending messages. Every Platform that keeps
reusable media implements it:

- ``upload(path, family)`` stores a local file and returns a reusable
  ``media_id``. Pass that ID to the Messenger's ``send_image`` /
  ``send_video`` / ``send_audio`` / ``send_document`` on the same Inbox.
- ``download(media_id)`` reads an inbound media message's bytes. Pass
  ``webhook.message.media_id`` unchanged.

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
    async def upload(self, source: Path, family: MediaFamily) -> UploadResult: ...

    @abstractmethod
    async def download(self, media_id: str) -> ReadResult[MediaBytes]: ...


__all__ = ["IMediaLibrary", "MediaFamily", "UploadResult"]
