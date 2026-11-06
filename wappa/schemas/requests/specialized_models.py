"""Neutral HTTP request models for contact and location sends.

``LocationRequestMessage`` and ``ContactRequestMessage`` front the
``IUserDataRequests`` capability (WhatsApp today; 501 elsewhere).
"""

from pydantic import Field

from wappa.domain.contacts import ContactCard
from wappa.schemas.core.recipient import DeliveryRequest


class ContactMessage(DeliveryRequest):
    contacts: list[ContactCard] = Field(
        ..., min_length=1, description="One or more contact cards, sent together"
    )
    reply_to_message_id: str | None = Field(None, description="Message ID to reply to")


class LocationMessage(DeliveryRequest):
    latitude: float = Field(
        ..., ge=-90, le=90, description="Location latitude (-90 to 90)"
    )
    longitude: float = Field(
        ..., ge=-180, le=180, description="Location longitude (-180 to 180)"
    )
    name: str | None = Field(None, max_length=100, description="Location name")
    address: str | None = Field(None, max_length=1000, description="Location address")
    reply_to_message_id: str | None = Field(None, description="Message ID to reply to")


class LocationRequestMessage(DeliveryRequest):
    body: str = Field(
        ..., min_length=1, max_length=1024, description="Request message text"
    )
    reply_to_message_id: str | None = Field(None, description="Message ID to reply to")


class ContactRequestMessage(DeliveryRequest):
    body: str = Field(
        ..., min_length=1, max_length=1024, description="Request message text"
    )
    reply_to_message_id: str | None = Field(None, description="Message ID to reply to")
