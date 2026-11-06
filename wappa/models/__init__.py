"""
Wappa data models for API endpoint schemas.

Re-exports the neutral send request models (``wappa.schemas.requests``) and
the neutral values they carry, for FastAPI endpoint typing on any Platform:

    from wappa.models import BasicTextMessage, MessageResult
    from wappa.models import ButtonMessage, ListMessage, CTAMessage
    from wappa.models import ImageMessage, VideoMessage, AudioMessage
    from wappa.models import ContactMessage, LocationMessage

WhatsApp-only models (``MediaType``, ``BusinessContact``, ``PersonalContact``,
the validator results, ``TemplateParameter``, ``WhatsAppTemplateType``) import
from ``wappa.messaging.whatsapp.models``. Template transport requests are
public from ``wappa.messaging``.
"""

from ..domain.contacts import ContactCard
from ..domain.results import MessageResult
from ..schemas.requests import (
    AudioMessage,
    BasicTextMessage,
    ButtonMessage,
    ContactMessage,
    ContactRequestMessage,
    CTAMessage,
    DocumentMessage,
    ImageMessage,
    ListMessage,
    LocationMessage,
    LocationRequestMessage,
    ReadStatusMessage,
    StickerMessage,
    VideoMessage,
)

__all__ = [
    "BasicTextMessage",
    "MessageResult",
    "ReadStatusMessage",
    "ButtonMessage",
    "CTAMessage",
    "ListMessage",
    "ImageMessage",
    "VideoMessage",
    "AudioMessage",
    "DocumentMessage",
    "StickerMessage",
    "ContactCard",
    "ContactMessage",
    "ContactRequestMessage",
    "LocationMessage",
    "LocationRequestMessage",
]
