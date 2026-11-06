"""Shared state and limits of the WhatsApp media transport.

Holds the client, the Inbox id, the download client and the per-type size and
MIME limits that upload, download, info and delete all consult.
"""

from __future__ import annotations

import httpx

from wappa.core.logging.logger import get_logger
from wappa.messaging.whatsapp.client import WhatsAppClient
from wappa.messaging.whatsapp.models.media_models import MediaType
from wappa.schemas.core.types import PlatformType


class _MediaTransportBase:
    """Typed attributes and limit helpers every transport mixin relies on."""

    def __init__(
        self,
        client: WhatsAppClient,
        inbox_id: str,
        *,
        media_download_client: httpx.AsyncClient,
    ):
        self.client = client
        self._inbox_id = inbox_id
        self._media_download_client = media_download_client
        self.logger = get_logger(__name__)

    @property
    def platform(self) -> PlatformType:
        return PlatformType.WHATSAPP

    @property
    def inbox_id(self) -> str:
        return self._inbox_id

    @property
    def supported_media_types(self) -> set[str]:
        return {
            mime
            for media_type in MediaType
            for mime in MediaType.get_supported_mime_types(media_type)
        }

    @property
    def max_file_size(self) -> dict[str, int]:
        return {
            "image": 5 * 1024 * 1024,
            "video": 16 * 1024 * 1024,
            "audio": 16 * 1024 * 1024,
            "document": 100 * 1024 * 1024,
            "sticker": 500 * 1024,
        }

    def validate_media_type(self, mime_type: str) -> bool:
        return mime_type in self.supported_media_types

    def validate_file_size(self, file_size: int, mime_type: str) -> bool:
        return file_size <= self._get_max_size_for_mime_type(mime_type)

    def _get_max_size_for_mime_type(self, mime_type: str) -> int:
        if mime_type.startswith("audio/") or mime_type.startswith("video/"):
            return 16 * 1024 * 1024
        if mime_type == "image/webp":
            return 500 * 1024
        if mime_type.startswith("image/"):
            return 5 * 1024 * 1024
        return 100 * 1024 * 1024

    def _get_extension_map(self) -> dict[str, str]:
        return {
            "audio/aac": ".aac",
            "audio/amr": ".amr",
            "audio/mpeg": ".mp3",
            "audio/mp4": ".m4a",
            "audio/ogg": ".ogg",
            "text/plain": ".txt",
            "application/vnd.ms-excel": ".xls",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
            "application/msword": ".doc",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
            "application/vnd.ms-powerpoint": ".ppt",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
            "application/pdf": ".pdf",
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/webp": ".webp",
            "video/3gpp": ".3gp",
            "video/mp4": ".mp4",
        }
