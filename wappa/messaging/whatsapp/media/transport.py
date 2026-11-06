"""``WhatsAppMediaTransport``: WhatsApp's Media API (upload, info, download, delete).

WhatsApp-only extension surface (``WhatsAppMessengerAdapter.media_transport``).
The shared HandlingMedia seam is ``IMediaLibrary``; ``WhatsAppMediaLibrary``
wraps this class.
"""

from __future__ import annotations

from wappa.messaging.whatsapp.media.download import _DownloadMixin
from wappa.messaging.whatsapp.media.upload_url import _UrlUploadMixin


class WhatsAppMediaTransport(_UrlUploadMixin, _DownloadMixin):
    """Upload, info, download, stream, delete and limits for one Inbox."""


__all__ = ["WhatsAppMediaTransport"]
