"""
WhatsApp contact message schema.

This module contains Pydantic models for processing WhatsApp contact messages,
including complex contact information with addresses, phones, emails, and organization data.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from wappa.webhooks.core.base_message import BaseContactMessage, BaseMessageContext
from wappa.webhooks.core.types import (
    ConversationType,
    MessageType,
    PlatformType,
    UniversalMessageData,
)
from wappa.webhooks.whatsapp.base_models import AdReferral, MessageContext


class ContactAddress(BaseModel):
    """Contact address information."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    city: str | None = Field(None, description="City name")
    country: str | None = Field(None, description="Country name")
    country_code: str | None = Field(None, description="Country code (e.g., 'US')")
    state: str | None = Field(None, description="State or province")
    street: str | None = Field(None, description="Street address")
    type: str | None = Field(None, description="Address type (e.g., 'HOME', 'WORK')")
    zip: str | None = Field(None, description="ZIP or postal code")

    @field_validator("country_code")
    @classmethod
    def validate_country_code(cls, v: str | None) -> str | None:
        """Validate country code format."""
        if v is not None:
            v = v.strip().upper()
            if len(v) != 2:
                raise ValueError("Country code must be 2 characters")
        return v


class ContactEmail(BaseModel):
    """Contact email information."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    email: str = Field(..., description="Email address")
    type: str | None = Field(None, description="Email type (e.g., 'HOME', 'WORK')")

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        """Basic email validation."""
        email = v.strip()
        if "@" not in email or "." not in email:
            raise ValueError("Invalid email format")
        return email


class ContactName(BaseModel):
    """Contact name information."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    formatted_name: str = Field(..., description="Full formatted name")
    first_name: str | None = Field(None, description="First name")
    last_name: str | None = Field(None, description="Last name")
    middle_name: str | None = Field(None, description="Middle name")
    suffix: str | None = Field(None, description="Name suffix (e.g., 'Jr.', 'III')")
    prefix: str | None = Field(None, description="Name prefix (e.g., 'Mr.', 'Dr.')")

    @field_validator("formatted_name")
    @classmethod
    def validate_formatted_name(cls, v: str) -> str:
        """Validate formatted name is not empty."""
        if not v.strip():
            raise ValueError("Formatted name cannot be empty")
        return v.strip()


class ContactOrganization(BaseModel):
    """Contact organization information."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    company: str | None = Field(None, description="Company name")
    department: str | None = Field(None, description="Department")
    title: str | None = Field(None, description="Job title")


class ContactPhone(BaseModel):
    """Contact phone information."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    phone: str = Field(..., description="Phone number")
    wa_id: str | None = Field(
        None, description="WhatsApp ID (if contact uses WhatsApp)"
    )
    type: str | None = Field(
        None, description="Phone type (e.g., 'HOME', 'WORK', 'CELL')"
    )

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        """Basic phone validation."""
        phone = v.strip()
        if len(phone) < 7:
            raise ValueError("Phone number must be at least 7 characters")
        return phone


class ContactUrl(BaseModel):
    """Contact URL information."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    url: str = Field(..., description="URL")
    type: str | None = Field(None, description="URL type (e.g., 'HOME', 'WORK')")

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Basic URL validation."""
        url = v.strip()
        if not (
            url.startswith("http://")
            or url.startswith("https://")
            or url.startswith("www.")
        ):
            raise ValueError("URL must start with http://, https://, or www.")
        return url


class ContactInfo(BaseModel):
    """Individual contact information."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    addresses: list[ContactAddress] | None = Field(
        None, description="List of contact addresses"
    )
    birthday: str | None = Field(None, description="Contact birthday (format varies)")
    emails: list[ContactEmail] | None = Field(
        None, description="List of contact emails"
    )
    name: ContactName = Field(..., description="Contact name information")
    org: ContactOrganization | None = Field(
        None, description="Contact organization information"
    )
    phones: list[ContactPhone] | None = Field(
        None, description="List of contact phone numbers"
    )
    urls: list[ContactUrl] | None = Field(None, description="List of contact URLs")


class WhatsAppContactMessage(BaseContactMessage):
    """
    WhatsApp contact message model.

    Supports various contact message scenarios:
    - Single or multiple contacts
    - Complete contact information (names, phones, emails, addresses, etc.)
    - Click-to-WhatsApp ad contact messages
    """

    model_config = ConfigDict(
        extra="forbid", str_strip_whitespace=True, validate_assignment=True
    )

    # Standard message fields (BSUID support v24.0+)
    from_: str = Field(
        default="",
        alias="from",
        description="WhatsApp user phone number (may be empty for username-only users)",
    )
    from_bsuid: str | None = Field(
        None,
        alias="from_user_id",
        description="Business Scoped User ID (BSUID) - stable identifier from webhook",
    )
    id: str = Field(..., description="Unique WhatsApp message ID")
    timestamp_str: str = Field(
        ..., alias="timestamp", description="Unix timestamp when the message was sent"
    )
    type: Literal["contacts"] = Field(
        ..., description="Message type, always 'contacts' for contact messages"
    )

    # Contact content
    contacts: list[ContactInfo] = Field(..., description="List of contact information")

    # Optional context fields
    context: MessageContext | None = Field(
        None,
        description="Context for forwards (contacts don't support replies typically)",
    )
    referral: AdReferral | None = Field(
        None, description="Click-to-WhatsApp ad referral information"
    )

    @property
    def sender_id(self) -> str:
        """Get the recommended sender identifier (BSUID if available, else phone)."""
        if self.from_bsuid and self.from_bsuid.strip():
            return self.from_bsuid.strip()
        return self.from_

    @property
    def has_bsuid(self) -> bool:
        """Check if this message has a BSUID set."""
        return bool(self.from_bsuid and self.from_bsuid.strip())

    @field_validator("id")
    @classmethod
    def validate_message_id(cls, v: str) -> str:
        """Validate WhatsApp message ID format."""
        if not v or len(v) < 10:
            raise ValueError("WhatsApp message ID must be at least 10 characters")
        # WhatsApp message IDs typically start with 'wamid.'
        if not v.startswith("wamid."):
            raise ValueError("WhatsApp message ID should start with 'wamid.'")
        return v

    @field_validator("timestamp_str")
    @classmethod
    def validate_timestamp(cls, v: str) -> str:
        """Validate Unix timestamp format."""
        if not v.isdigit():
            raise ValueError("Timestamp must be numeric")
        # Validate reasonable timestamp range (after 2020, before 2100)
        timestamp_int = int(v)
        if timestamp_int < 1577836800 or timestamp_int > 4102444800:
            raise ValueError("Timestamp must be a valid Unix timestamp")
        return v

    @field_validator("contacts")
    @classmethod
    def validate_contacts_not_empty(cls, v: list[ContactInfo]) -> list[ContactInfo]:
        """Validate contacts list is not empty."""
        if not v or len(v) == 0:
            raise ValueError("Contacts list cannot be empty")
        if len(v) > 10:  # Reasonable limit
            raise ValueError("Cannot send more than 10 contacts at once")
        return v

    @property
    def is_ad_message(self) -> bool:
        """Check if this contact message came from a Click-to-WhatsApp ad."""
        return self.referral is not None

    @property
    def is_single_contact(self) -> bool:
        """Check if this message contains a single contact."""
        return len(self.contacts) == 1

    @property
    def is_multiple_contacts(self) -> bool:
        """Check if this message contains multiple contacts."""
        return len(self.contacts) > 1

    @property
    def contact_count(self) -> int:
        """Get the number of contacts in this message."""
        return len(self.contacts)

    @property
    def sender_phone(self) -> str:
        """Get the sender's phone number (clean accessor)."""
        return self.from_

    @property
    def unix_timestamp(self) -> int:
        """Get the timestamp as an integer."""
        return self.timestamp

    def get_primary_contact(self) -> ContactInfo:
        """Get the first contact from the list."""
        return self.contacts[0]

    def get_contact_names(self) -> list[str]:
        """Get a list of all contact formatted names."""
        return [contact.name.formatted_name for contact in self.contacts]

    def get_whatsapp_contacts(self) -> list[ContactInfo]:
        """Get contacts that have WhatsApp numbers."""
        whatsapp_contacts = []
        for contact in self.contacts:
            if contact.phones:
                for phone in contact.phones:
                    if phone.wa_id:
                        whatsapp_contacts.append(contact)
                        break
        return whatsapp_contacts

    def get_business_contacts(self) -> list[ContactInfo]:
        """Get contacts that have business/organization information."""
        business_contacts = []
        for contact in self.contacts:
            if contact.org and (contact.org.company or contact.org.title):
                business_contacts.append(contact)
        return business_contacts

    def get_contact_phone_count(self) -> int:
        """Get total number of phone numbers across all contacts."""
        total_phones = 0
        for contact in self.contacts:
            if contact.phones:
                total_phones += len(contact.phones)
        return total_phones

    def get_contact_email_count(self) -> int:
        """Get total number of email addresses across all contacts."""
        total_emails = 0
        for contact in self.contacts:
            if contact.emails:
                total_emails += len(contact.emails)
        return total_emails

    def get_contact_address_count(self) -> int:
        """Get total number of addresses across all contacts."""
        total_addresses = 0
        for contact in self.contacts:
            if contact.addresses:
                total_addresses += len(contact.addresses)
        return total_addresses

    def get_ad_context(self) -> tuple[str | None, str | None]:
        """
        Get ad context information for Click-to-WhatsApp contact messages.

        Returns:
            Tuple of (ad_id, ad_click_id) if this came from an ad,
            (None, None) otherwise.
        """
        if self.is_ad_message and self.referral:
            return (self.referral.source_id, self.referral.ctwa_clid)
        return (None, None)

    def to_summary_dict(self) -> dict[str, str | bool | int | list]:
        """
        Create a summary dictionary for logging and analysis.

        Returns:
            Dictionary with key message information for structured logging.
        """
        return {
            "message_id": self.id,
            "sender": self.sender_phone,
            "timestamp": self.unix_timestamp,
            "type": self.type,
            "contact_count": self.contact_count,
            "contact_names": self.get_contact_names(),
            "has_whatsapp_contacts": len(self.get_whatsapp_contacts()) > 0,
            "whatsapp_contact_count": len(self.get_whatsapp_contacts()),
            "is_ad_message": self.is_ad_message,
        }

    # Implement abstract methods from BaseMessage

    @property
    def platform(self) -> PlatformType:
        return PlatformType.WHATSAPP

    @property
    def message_type(self) -> MessageType:
        return MessageType.CONTACT

    @property
    def message_id(self) -> str:
        return self.id

    @property
    def timestamp(self) -> int:
        return int(self.timestamp_str)

    @property
    def conversation_id(self) -> str:
        return self.from_

    @property
    def conversation_type(self) -> ConversationType:
        return ConversationType.PRIVATE

    def has_context(self) -> bool:
        return self.context is not None

    def get_context(self) -> BaseMessageContext | None:
        from .text import WhatsAppMessageContext

        return WhatsAppMessageContext(self.context) if self.context else None

    def to_universal_dict(self) -> UniversalMessageData:
        return {
            "platform": self.platform.value,
            "message_type": self.message_type.value,
            "message_id": self.message_id,
            "sender_id": self.sender_id,
            "conversation_id": self.conversation_id,
            "conversation_type": self.conversation_type.value,
            "timestamp": self.timestamp,
            "processed_at": self.processed_at.isoformat(),
            "has_context": self.has_context(),
            "contact_count": self.contact_count,
            "contact_names": self.get_contact_names(),
            "primary_contact_name": self.get_primary_contact().name.formatted_name,
            "whatsapp_data": {
                "whatsapp_id": self.id,
                "from": self.from_,
                "timestamp_str": self.timestamp_str,
                "type": self.type,
                "contacts": [contact.model_dump() for contact in self.contacts],
                "context": self.context.model_dump() if self.context else None,
                "referral": self.referral.model_dump() if self.referral else None,
            },
        }

    def get_platform_data(self) -> dict[str, Any]:
        return {
            "whatsapp_message_id": self.id,
            "from_phone": self.from_,
            "timestamp_str": self.timestamp_str,
            "message_type": self.type,
            "contacts": [contact.model_dump() for contact in self.contacts],
            "context": self.context.model_dump() if self.context else None,
            "referral": self.referral.model_dump() if self.referral else None,
            "contact_summary": {
                "contact_count": self.contact_count,
                "is_single_contact": self.is_single_contact,
                "whatsapp_contact_count": len(self.get_whatsapp_contacts()),
            },
        }

    # Implement abstract methods from BaseContactMessage

    @property
    def contact_name(self) -> str:
        """Get the primary contact's name (first contact in the list)."""
        if self.contacts:
            return self.contacts[0].name.formatted_name
        return "Unknown Contact"

    @property
    def contact_phone(self) -> str | None:
        """Get the primary contact's first phone number."""
        if self.contacts and self.contacts[0].phones:
            return self.contacts[0].phones[0].phone
        return None

    @property
    def contact_data(self) -> dict[str, Any]:
        return {
            "contacts": [contact.model_dump() for contact in self.contacts],
            "primary_contact": self.get_primary_contact().model_dump(),
            "contact_count": self.contact_count,
        }

    @classmethod
    def from_platform_data(
        cls, data: dict[str, Any], **kwargs
    ) -> "WhatsAppContactMessage":
        return cls.model_validate(data)
