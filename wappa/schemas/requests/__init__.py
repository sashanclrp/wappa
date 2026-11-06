"""Neutral HTTP request models fronting the ``IMessenger`` contract.

They live in the schemas layer so the API routes and the outbound classifier
(``wappa.messaging.classification``) share them without either depending on
the other.

Every model subclasses ``DeliveryRequest`` and serves every Platform path; the
limits are the shared ones from ``wappa.domain.interactive`` (ADR-0028).
"""

from .basic_models import BasicTextMessage, ReadStatusMessage
from .interactive_models import ButtonMessage, CTAMessage, ListMessage
from .media_models import (
    AudioMessage,
    DocumentMessage,
    ImageMessage,
    MediaMessage,
    StickerMessage,
    VideoMessage,
)
from .specialized_models import (
    ContactMessage,
    ContactRequestMessage,
    LocationMessage,
    LocationRequestMessage,
)

__all__ = [
    "AudioMessage",
    "BasicTextMessage",
    "ButtonMessage",
    "CTAMessage",
    "ContactMessage",
    "ContactRequestMessage",
    "DocumentMessage",
    "ImageMessage",
    "ListMessage",
    "LocationMessage",
    "LocationRequestMessage",
    "MediaMessage",
    "ReadStatusMessage",
    "StickerMessage",
    "VideoMessage",
]
