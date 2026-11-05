"""Platform-neutral contact card (ADR-0016).

One typed value for ``IMessenger.send_contact`` on every Platform: WhatsApp
sends it as a native contact message; Instagram renders it as text.
"""

from pydantic import BaseModel, Field, field_validator

# Type values are free strings on WhatsApp ("HOME", "WORK", "CELL", ...).


class ContactAddress(BaseModel):
    street: str | None = Field(None, max_length=500, description="Street address")
    city: str | None = Field(None, max_length=100, description="City name")
    state: str | None = Field(None, max_length=100, description="State or province")
    zip: str | None = Field(None, max_length=20, description="ZIP or postal code")
    country: str | None = Field(None, max_length=100, description="Country name")
    country_code: str | None = Field(
        None, pattern=r"^[A-Z]{2}$", description="ISO country code"
    )
    type: str | None = Field(None, description="Address type (e.g., HOME, WORK)")


class ContactEmail(BaseModel):
    email: str = Field(
        ..., pattern=r"^[^@]+@[^@]+\.[^@]+$", description="Email address"
    )
    type: str | None = Field(None, description="Email type (e.g., HOME, WORK)")


class ContactName(BaseModel):
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
    def validate_formatted_name_required(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("formatted_name is required and cannot be empty")
        return v.strip()


class ContactOrganization(BaseModel):
    company: str | None = Field(None, max_length=100, description="Company name")
    department: str | None = Field(None, max_length=100, description="Department")
    title: str | None = Field(None, max_length=100, description="Job title")


class ContactPhone(BaseModel):
    phone: str = Field(
        ..., pattern=r"^\+?[\d\s\-\(\)]{7,20}$", description="Phone number"
    )
    type: str | None = Field(
        None,
        description="Phone type (e.g., CELL, MOBILE, HOME, WORK, MAIN, IPHONE, WHATSAPP)",
    )
    wa_id: str | None = Field(None, pattern=r"^\d{10,15}$", description="WhatsApp ID")


class ContactUrl(BaseModel):
    url: str = Field(..., pattern=r"^https?://", description="Website URL")
    type: str | None = Field(None, description="URL type (e.g., HOME, WORK)")


class ContactCard(BaseModel):
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


__all__ = [
    "ContactAddress",
    "ContactCard",
    "ContactEmail",
    "ContactName",
    "ContactOrganization",
    "ContactPhone",
    "ContactUrl",
]
