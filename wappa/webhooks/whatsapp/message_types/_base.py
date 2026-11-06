"""Shared base of the WhatsApp message models: sender identity, ids and timestamps."""

from __future__ import annotations

from pydantic import Field, field_validator

from wappa.schemas.core.types import ConversationType, PlatformType
from wappa.webhooks.whatsapp.models.base import WhatsAppMessageIdentity


class WhatsAppMessageBase(WhatsAppMessageIdentity):
    """The members every WhatsApp message model shares.

    Message classes inherit it ahead of their Universal base. A class that needs
    a different definition of a member redefines it.
    """

    # Standard message fields
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

    @property
    def sender_phone(self) -> str:
        """Get the sender's phone number (clean accessor)."""
        return self.from_

    @property
    def unix_timestamp(self) -> int:
        """Get the timestamp as an integer."""
        return self.timestamp

    @property
    def platform(self) -> PlatformType:
        return PlatformType.WHATSAPP

    @property
    def message_id(self) -> str:
        return self.id

    @property
    def sender_id(self) -> str:
        """Get the recommended sender identifier (BSUID if available, else phone)."""
        if self.from_bsuid and self.from_bsuid.strip():
            return self.from_bsuid.strip()
        return self.from_

    @property
    def timestamp(self) -> int:
        return int(self.timestamp_str)

    @property
    def conversation_id(self) -> str:
        return self.group_id or self.sender_id

    @property
    def conversation_type(self) -> ConversationType:
        return ConversationType.GROUP if self.group_id else ConversationType.PRIVATE
