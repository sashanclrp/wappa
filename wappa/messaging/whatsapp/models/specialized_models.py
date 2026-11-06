"""WhatsApp specialized message models."""

from pydantic import BaseModel, Field

# Note: All contact type enums removed - WhatsApp accepts any string values
# Common type values across all fields: "HOME", "WORK", etc.
# Phone-specific: "CELL", "MOBILE", "MAIN", "IPHONE", "WHATSAPP"
from wappa.domain.contacts import (
    ContactCard,
    ContactEmail,
    ContactName,
    ContactOrganization,
    ContactPhone,
    ContactUrl,
)
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


class ContactValidationResult(BaseModel):
    valid: bool = Field(..., description="Whether contact is valid")
    errors: list[str] | None = Field(None, description="Validation errors")
    warnings: list[str] | None = Field(None, description="Validation warnings")


class LocationValidationResult(BaseModel):
    valid: bool = Field(..., description="Whether location is valid")
    latitude: float | None = Field(None, description="Validated latitude")
    longitude: float | None = Field(None, description="Validated longitude")
    errors: list[str] | None = Field(None, description="Validation errors")
    address_suggestions: list[str] | None = Field(
        None, description="Address suggestions"
    )


class BusinessContact(BaseModel):
    business_name: str = Field(..., max_length=100, description="Business name")
    phone: str = Field(
        ..., pattern=r"^\+?[\d\s\-\(\)]{7,20}$", description="Business phone"
    )
    email: str | None = Field(
        None, pattern=r"^[^@]+@[^@]+\.[^@]+$", description="Business email"
    )
    website: str | None = Field(
        None, pattern=r"^https?://", description="Business website"
    )
    address: str | None = Field(None, max_length=500, description="Business address")

    def to_contact_card(self) -> ContactCard:
        phones = [ContactPhone(phone=self.phone, type="WORK")]
        emails = [ContactEmail(email=self.email, type="WORK")] if self.email else None
        urls = [ContactUrl(url=self.website, type="WORK")] if self.website else None

        return ContactCard(
            name=ContactName(formatted_name=self.business_name),
            phones=phones,
            emails=emails,
            urls=urls,
            org=ContactOrganization(company=self.business_name),
        )


class PersonalContact(BaseModel):
    first_name: str = Field(..., max_length=50, description="First name")
    last_name: str | None = Field(None, max_length=50, description="Last name")
    phone: str = Field(
        ..., pattern=r"^\+?[\d\s\-\(\)]{7,20}$", description="Phone number"
    )
    email: str | None = Field(
        None, pattern=r"^[^@]+@[^@]+\.[^@]+$", description="Email address"
    )

    def to_contact_card(self) -> ContactCard:
        formatted_name = (
            f"{self.first_name} {self.last_name}".strip()
            if self.last_name
            else self.first_name
        )
        phones = [ContactPhone(phone=self.phone, type="CELL")]
        emails = [ContactEmail(email=self.email, type="HOME")] if self.email else None

        return ContactCard(
            name=ContactName(
                formatted_name=formatted_name,
                first_name=self.first_name,
                last_name=self.last_name,
            ),
            phones=phones,
            emails=emails,
        )
