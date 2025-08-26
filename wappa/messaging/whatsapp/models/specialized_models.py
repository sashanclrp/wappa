"""
WhatsApp specialized message models.

Provides Pydantic v2 validation models for WhatsApp specialized operations:
- ContactMessage: Contact card sharing with comprehensive contact information
- LocationMessage: Geographic location sharing with coordinates
- LocationRequestMessage: Interactive location request from users

Based on WhatsApp Cloud API 2025 specialized message specifications.
"""

from enum import Enum

from pydantic import BaseModel, Field, field_validator


class AddressType(str, Enum):
    """Contact address types."""

    HOME = "HOME"
    WORK = "WORK"


class EmailType(str, Enum):
    """Contact email types."""

    HOME = "HOME"
    WORK = "WORK"


class PhoneType(str, Enum):
    """Contact phone number types."""

    HOME = "HOME"
    WORK = "WORK"
    CELL = "CELL"
    MAIN = "MAIN"
    IPHONE = "IPHONE"
    WHATSAPP = "WHATSAPP"


class UrlType(str, Enum):
    """Contact URL types."""

    HOME = "HOME"
    WORK = "WORK"


class ContactAddress(BaseModel):
    """Contact address information."""

    street: str | None = Field(None, max_length=500, description="Street address")
    city: str | None = Field(None, max_length=100, description="City name")
    state: str | None = Field(None, max_length=100, description="State or province")
    zip: str | None = Field(None, max_length=20, description="ZIP or postal code")
    country: str | None = Field(None, max_length=100, description="Country name")
    country_code: str | None = Field(
        None, pattern=r"^[A-Z]{2}$", description="ISO country code"
    )
    type: AddressType = Field(..., description="Address type")


class ContactEmail(BaseModel):
    """Contact email information."""

    email: str = Field(
        ..., pattern=r"^[^@]+@[^@]+\.[^@]+$", description="Email address"
    )
    type: EmailType = Field(..., description="Email type")


class ContactName(BaseModel):
    """Contact name information."""

    formatted_name: str = Field(
        ..., min_length=1, max_length=100, description="Full formatted name"
    )
    first_name: str | None = Field(None, max_length=50, description="First name")
    last_name: str | None = Field(None, max_length=50, description="Last name")
    middle_name: str | None = Field(None, max_length=50, description="Middle name")
    suffix: str | None = Field(None, max_length=20, description="Name suffix")
    prefix: str | None = Field(None, max_length=20, description="Name prefix")

    @field_validator("formatted_name")
    @classmethod
    def validate_formatted_name_required(cls, v):
        """Validate that formatted_name is not empty."""
        if not v or not v.strip():
            raise ValueError("formatted_name is required and cannot be empty")
        return v.strip()


class ContactOrganization(BaseModel):
    """Contact organization information."""

    company: str | None = Field(None, max_length=100, description="Company name")
    department: str | None = Field(None, max_length=100, description="Department")
    title: str | None = Field(None, max_length=100, description="Job title")


class ContactPhone(BaseModel):
    """Contact phone information."""

    phone: str = Field(
        ..., pattern=r"^\+?[\d\s\-\(\)]{7,20}$", description="Phone number"
    )
    type: PhoneType = Field(..., description="Phone type")
    wa_id: str | None = Field(None, pattern=r"^\d{10,15}$", description="WhatsApp ID")


class ContactUrl(BaseModel):
    """Contact URL information."""

    url: str = Field(..., pattern=r"^https?://", description="Website URL")
    type: UrlType = Field(..., description="URL type")


class ContactCard(BaseModel):
    """Complete contact card information."""

    addresses: list[ContactAddress] | None = Field(
        None, max_length=5, description="Contact addresses"
    )
    birthday: str | None = Field(
        None, pattern=r"^\d{4}-\d{2}-\d{2}$", description="Birthday (YYYY-MM-DD)"
    )
    emails: list[ContactEmail] | None = Field(
        None, max_length=5, description="Email addresses"
    )
    name: ContactName = Field(..., description="Contact name information")
    org: ContactOrganization | None = Field(
        None, description="Organization information"
    )
    phones: list[ContactPhone] = Field(
        ..., min_length=1, max_length=5, description="Phone numbers"
    )
    urls: list[ContactUrl] | None = Field(
        None, max_length=5, description="Website URLs"
    )

    @field_validator("phones")
    @classmethod
    def validate_at_least_one_phone(cls, v):
        """Validate that at least one phone number is provided."""
        if not v or len(v) == 0:
            raise ValueError("At least one phone number is required")
        return v


class ContactMessage(BaseModel):
    """Contact card message request."""

    recipient: str = Field(
        ..., pattern=r"^\d{10,15}$", description="Recipient phone number"
    )
    contact: ContactCard = Field(..., description="Contact card information")
    reply_to_message_id: str | None = Field(None, description="Message ID to reply to")


class LocationMessage(BaseModel):
    """Location sharing message request."""

    recipient: str = Field(
        ..., pattern=r"^\d{10,15}$", description="Recipient phone number"
    )
    latitude: float = Field(
        ..., ge=-90, le=90, description="Location latitude (-90 to 90)"
    )
    longitude: float = Field(
        ..., ge=-180, le=180, description="Location longitude (-180 to 180)"
    )
    name: str | None = Field(None, max_length=100, description="Location name")
    address: str | None = Field(None, max_length=1000, description="Location address")
    reply_to_message_id: str | None = Field(None, description="Message ID to reply to")

    @field_validator("latitude")
    @classmethod
    def validate_latitude_range(cls, v):
        """Validate latitude is within valid range."""
        if not -90 <= v <= 90:
            raise ValueError("Latitude must be between -90 and 90 degrees")
        return v

    @field_validator("longitude")
    @classmethod
    def validate_longitude_range(cls, v):
        """Validate longitude is within valid range."""
        if not -180 <= v <= 180:
            raise ValueError("Longitude must be between -180 and 180 degrees")
        return v


class LocationRequestMessage(BaseModel):
    """Location request message (asks user to share their location)."""

    recipient: str = Field(
        ..., pattern=r"^\d{10,15}$", description="Recipient phone number"
    )
    body: str = Field(
        ..., min_length=1, max_length=1024, description="Request message text"
    )
    reply_to_message_id: str | None = Field(None, description="Message ID to reply to")

    @field_validator("body")
    @classmethod
    def validate_body_length(cls, v):
        """Validate body text length."""
        if len(v) > 1024:
            raise ValueError("Body text cannot exceed 1024 characters")
        return v


class ContactValidationResult(BaseModel):
    """Contact validation result."""

    valid: bool = Field(..., description="Whether contact is valid")
    errors: list[str] | None = Field(None, description="Validation errors")
    warnings: list[str] | None = Field(None, description="Validation warnings")


class LocationValidationResult(BaseModel):
    """Location validation result."""

    valid: bool = Field(..., description="Whether location is valid")
    latitude: float | None = Field(None, description="Validated latitude")
    longitude: float | None = Field(None, description="Validated longitude")
    errors: list[str] | None = Field(None, description="Validation errors")
    address_suggestions: list[str] | None = Field(
        None, description="Address suggestions"
    )


# Example contact structures for common use cases
class BusinessContact(BaseModel):
    """Simplified business contact model."""

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
        """Convert to full ContactCard format."""
        phones = [ContactPhone(phone=self.phone, type=PhoneType.WORK)]
        emails = (
            [ContactEmail(email=self.email, type=EmailType.WORK)]
            if self.email
            else None
        )
        urls = (
            [ContactUrl(url=self.website, type=UrlType.WORK)] if self.website else None
        )

        return ContactCard(
            name=ContactName(formatted_name=self.business_name),
            phones=phones,
            emails=emails,
            urls=urls,
            org=ContactOrganization(company=self.business_name),
        )


class PersonalContact(BaseModel):
    """Simplified personal contact model."""

    first_name: str = Field(..., max_length=50, description="First name")
    last_name: str | None = Field(None, max_length=50, description="Last name")
    phone: str = Field(
        ..., pattern=r"^\+?[\d\s\-\(\)]{7,20}$", description="Phone number"
    )
    email: str | None = Field(
        None, pattern=r"^[^@]+@[^@]+\.[^@]+$", description="Email address"
    )

    def to_contact_card(self) -> ContactCard:
        """Convert to full ContactCard format."""
        formatted_name = (
            f"{self.first_name} {self.last_name}".strip()
            if self.last_name
            else self.first_name
        )
        phones = [ContactPhone(phone=self.phone, type=PhoneType.CELL)]
        emails = (
            [ContactEmail(email=self.email, type=EmailType.HOME)]
            if self.email
            else None
        )

        return ContactCard(
            name=ContactName(
                formatted_name=formatted_name,
                first_name=self.first_name,
                last_name=self.last_name,
            ),
            phones=phones,
            emails=emails,
        )
