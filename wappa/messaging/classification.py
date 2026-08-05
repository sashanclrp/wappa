"""One classifier over Wappa's validated outbound payload schemas.

Wappa already receives strongly shaped payloads: a text send is a
``BasicTextMessage``, a Template send is one of three discriminated Template
transport requests. Callers that re-derive "what kind of send is this?" with
their own ``type`` checks — or worse, by noticing which optional context field
happens to be populated — end up with as many answers as there are call sites,
and the answers drift.

Classification here is a statement about **transport shape only**. It says a
payload is a Template because it is a Template envelope, never because of who
is sending it, which Conversation it belongs to, or what metadata rides along.
Whether a given send is *permitted* is a Host Application question and is
deliberately not answerable from this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from pydantic import BaseModel

from wappa.messaging.template_transport import (
    LocationTemplateTransportRequest,
    MediaTemplateTransportRequest,
    TextTemplateTransportRequest,
)
from wappa.messaging.whatsapp.models.basic_models import (
    BasicTextMessage,
    ReadStatusMessage,
)
from wappa.messaging.whatsapp.models.interactive_models import (
    ButtonMessage,
    CTAMessage,
    ListMessage,
)
from wappa.messaging.whatsapp.models.media_models import (
    AudioMessage,
    DocumentMessage,
    ImageMessage,
    MediaMessage,
    MediaType,
    StickerMessage,
    VideoMessage,
)
from wappa.messaging.whatsapp.models.specialized_models import (
    ContactMessage,
    LocationMessage,
    LocationRequestMessage,
)


class UnsupportedOutboundPayloadError(TypeError):
    """Raised when a payload is not one of Wappa's outbound send schemas."""


class OutboundTransportFamily(StrEnum):
    """The transport family a validated outbound payload belongs to."""

    TEXT = "text"
    MEDIA = "media"
    INTERACTIVE = "interactive"
    LOCATION = "location"
    CONTACT = "contact"
    TEMPLATE = "template"
    READ_RECEIPT = "read_receipt"


class OutboundTransportSubkind(StrEnum):
    """The concrete variant within a family, where the family has several."""

    # Media family
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    DOCUMENT = "document"
    STICKER = "sticker"
    # Interactive family
    BUTTON = "button"
    LIST = "list"
    CTA = "cta"
    LOCATION_REQUEST = "location_request"
    # Template family — which header the Template envelope carries
    TEXT_HEADER = "text_header"
    MEDIA_HEADER = "media_header"
    LOCATION_HEADER = "location_header"


# Families whose event label is the concrete variant rather than the family:
# Wappa's outbound event stream has always named an image send "image", not
# "media". Templates go the other way — every Template is labelled "template",
# because which header it carries does not change what kind of send it was.
_LABELLED_BY_SUBKIND = frozenset(
    {OutboundTransportFamily.MEDIA, OutboundTransportFamily.INTERACTIVE}
)


@dataclass(frozen=True, slots=True)
class OutboundClassification:
    """What transport shape a payload has — nothing about who may send it."""

    family: OutboundTransportFamily
    subkind: OutboundTransportSubkind | None = None

    @property
    def is_template(self) -> bool:
        """Whether this payload is a Template envelope."""
        return self.family is OutboundTransportFamily.TEMPLATE

    @property
    def message_type(self) -> str:
        """The stable label Wappa reports for this send in outbound events."""
        if self.family in _LABELLED_BY_SUBKIND and self.subkind is not None:
            return self.subkind.value
        return self.family.value


_TEXT = OutboundClassification(OutboundTransportFamily.TEXT)
_CONTACT = OutboundClassification(OutboundTransportFamily.CONTACT)
_LOCATION = OutboundClassification(OutboundTransportFamily.LOCATION)
_READ_RECEIPT = OutboundClassification(OutboundTransportFamily.READ_RECEIPT)


def _media(subkind: OutboundTransportSubkind) -> OutboundClassification:
    return OutboundClassification(OutboundTransportFamily.MEDIA, subkind)


def _interactive(subkind: OutboundTransportSubkind) -> OutboundClassification:
    return OutboundClassification(OutboundTransportFamily.INTERACTIVE, subkind)


def _template(subkind: OutboundTransportSubkind) -> OutboundClassification:
    return OutboundClassification(OutboundTransportFamily.TEMPLATE, subkind)


# Exact schema -> classification. A bare base class (``InteractiveMessage``,
# ``RecipientRequest``) is absent on purpose: it names no concrete transport,
# so it must fail rather than be guessed at.
_BY_SCHEMA: dict[type[BaseModel], OutboundClassification] = {
    BasicTextMessage: _TEXT,
    ReadStatusMessage: _READ_RECEIPT,
    ImageMessage: _media(OutboundTransportSubkind.IMAGE),
    VideoMessage: _media(OutboundTransportSubkind.VIDEO),
    AudioMessage: _media(OutboundTransportSubkind.AUDIO),
    DocumentMessage: _media(OutboundTransportSubkind.DOCUMENT),
    StickerMessage: _media(OutboundTransportSubkind.STICKER),
    ButtonMessage: _interactive(OutboundTransportSubkind.BUTTON),
    ListMessage: _interactive(OutboundTransportSubkind.LIST),
    CTAMessage: _interactive(OutboundTransportSubkind.CTA),
    LocationRequestMessage: _interactive(OutboundTransportSubkind.LOCATION_REQUEST),
    ContactMessage: _CONTACT,
    LocationMessage: _LOCATION,
    TextTemplateTransportRequest: _template(OutboundTransportSubkind.TEXT_HEADER),
    MediaTemplateTransportRequest: _template(OutboundTransportSubkind.MEDIA_HEADER),
    LocationTemplateTransportRequest: _template(
        OutboundTransportSubkind.LOCATION_HEADER
    ),
}

# ``MediaMessage`` carries its variant in a field instead of its class.
_BY_MEDIA_TYPE: dict[MediaType, OutboundTransportSubkind] = {
    MediaType.IMAGE: OutboundTransportSubkind.IMAGE,
    MediaType.VIDEO: OutboundTransportSubkind.VIDEO,
    MediaType.AUDIO: OutboundTransportSubkind.AUDIO,
    MediaType.DOCUMENT: OutboundTransportSubkind.DOCUMENT,
    MediaType.STICKER: OutboundTransportSubkind.STICKER,
}


def classify_outbound_payload(payload: Any) -> OutboundClassification:
    """Classify one validated outbound payload by its transport shape.

    Args:
        payload: An instance of a Wappa outbound send schema.

    Returns:
        The transport family, plus the concrete variant where the family has
        more than one.

    Raises:
        UnsupportedOutboundPayloadError: The value is not an outbound send
            schema, or is a base class that names no concrete transport.

    Example:
        >>> classify_outbound_payload(
        ...     BasicTextMessage(recipient="573001112233", text="hi")
        ... ).family
        <OutboundTransportFamily.TEXT: 'text'>
    """
    if not isinstance(payload, BaseModel):
        raise UnsupportedOutboundPayloadError(
            f"Expected a Wappa outbound payload schema, got {type(payload).__name__}"
        )

    if isinstance(payload, MediaMessage):
        return _classify_media_message(payload)

    # Exact match first; then the MRO, so a Host Application subclass of a
    # concrete schema classifies as the schema it extends.
    for schema in type(payload).__mro__:
        classification = _BY_SCHEMA.get(schema)
        if classification is not None:
            return classification

    raise UnsupportedOutboundPayloadError(
        f"{type(payload).__name__} is not a Wappa outbound send schema; it names "
        "no transport family"
    )


def _classify_media_message(payload: MediaMessage) -> OutboundClassification:
    subkind = _BY_MEDIA_TYPE.get(payload.media_type)
    if subkind is None:
        raise UnsupportedOutboundPayloadError(
            f"MediaMessage carries an unclassifiable media_type: {payload.media_type!r}"
        )
    return OutboundClassification(OutboundTransportFamily.MEDIA, subkind)


__all__ = [
    "OutboundClassification",
    "OutboundTransportFamily",
    "OutboundTransportSubkind",
    "UnsupportedOutboundPayloadError",
    "classify_outbound_payload",
]
