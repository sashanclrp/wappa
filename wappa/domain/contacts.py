"""Platform-neutral contact card (ADR-0025).

One typed value for ``IMessenger.send_contact`` on every Platform: WhatsApp
sends one or several cards as a native contacts message; Instagram renders
each card as a text block. Only ``name.formatted_name`` is
required: WhatsApp also needs one name part, so a name without any takes
``first_name`` from ``formatted_name`` when it is built.
"""

from collections.abc import Sequence
from typing import Self

from pydantic import BaseModel, Field, field_validator, model_validator

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

    @model_validator(mode="after")
    def _one_name_part(self) -> Self:
        # WhatsApp rejects a name with only formatted_name (131009, "ContactName
        # should have at least one optional value be set along with formatted
        # Name"), so a card that builds always carries one part.
        parts = (
            self.first_name,
            self.last_name,
            self.middle_name,
            self.suffix,
            self.prefix,
        )
        if not any(parts):
            self.first_name = self.formatted_name[:50]
        return self


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
    phones: list[ContactPhone] | None = Field(
        None, max_length=5, description="Phone numbers"
    )
    urls: list[ContactUrl] | None = Field(
        None, max_length=5, description="Website URLs"
    )


def contact_cards(contacts: ContactCard | Sequence[ContactCard]) -> list[ContactCard]:
    """``send_contact``'s one card or several, as a non-empty list."""
    cards = [contacts] if isinstance(contacts, ContactCard) else list(contacts)
    if not cards:
        raise ValueError("send_contact needs at least one ContactCard")
    return cards


__all__ = [
    "ContactAddress",
    "ContactCard",
    "ContactEmail",
    "ContactName",
    "ContactOrganization",
    "ContactPhone",
    "ContactUrl",
    "contact_cards",
]
