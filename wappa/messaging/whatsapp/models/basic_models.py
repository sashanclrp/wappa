"""
Basic message models for WhatsApp messaging.

Pydantic schemas for basic messaging operations: send_text and mark_as_read.

BSUID Support (v24.0+):
- ResponseContact includes user_id (BSUID) field
- wa_id may be empty when sending to BSUID
- input field reflects what was sent (phone or BSUID)
"""

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

from wappa.schemas.core.types import PlatformType


def _utc_now() -> datetime:
    """Return current UTC datetime."""
    return datetime.now(UTC)


class ResponseContact(BaseModel):
    """Contact information from WhatsApp API response.

    Represents a contact in the API response after sending a message.

    BSUID Support (v24.0+):
    - input: Returns BSUID if sent to BSUID, otherwise phone number
    - wa_id: Empty string if sent to BSUID, otherwise phone number
    - bsuid: BSUID if sent to BSUID, otherwise None/omitted
    - recipient_id: Property that returns BSUID if available, else wa_id
    """

    model_config = ConfigDict(extra="ignore")

    input: str = Field(
        ...,
        description="The recipient identifier that was sent (phone number or BSUID)",
    )
    wa_id: str = Field(
        default="",
        description="WhatsApp ID (phone number). Empty if sent to BSUID.",
    )
    bsuid: str | None = Field(
        None,
        alias="user_id",
        description="Business Scoped User ID (BSUID). Present if sent to BSUID.",
    )

    @property
    def recipient_id(self) -> str:
        """Get the recommended recipient identifier (BSUID if available, else wa_id)."""
        if self.bsuid and self.bsuid.strip():
            return self.bsuid.strip()
        return self.wa_id or self.input

    @property
    def has_bsuid(self) -> bool:
        """Check if response contains a BSUID."""
        return bool(self.bsuid and self.bsuid.strip())

    @property
    def was_sent_to_bsuid(self) -> bool:
        """Check if the message was sent to a BSUID (not phone number)."""
        return self.has_bsuid and not self.wa_id


class ResponseMessage(BaseModel):
    """Message information from WhatsApp API response."""

    model_config = ConfigDict(extra="ignore")

    id: str = Field(..., description="WhatsApp message ID")
    message_status: str | None = Field(
        None, description="Message status (e.g., 'accepted')"
    )


class WhatsAppAPIResponse(BaseModel):
    """Full WhatsApp API response for send message requests.

    This model captures the complete API response structure including
    contacts with BSUID support (v24.0+).
    """

    model_config = ConfigDict(extra="ignore")

    messaging_product: str = Field(default="whatsapp")
    contacts: list[ResponseContact] = Field(
        default_factory=list,
        description="Contact information for recipients",
    )
    messages: list[ResponseMessage] = Field(
        default_factory=list,
        description="Message IDs for sent messages",
    )

    @property
    def message_id(self) -> str | None:
        """Get the first message ID from the response."""
        return self.messages[0].id if self.messages else None

    @property
    def primary_contact(self) -> ResponseContact | None:
        """Get the primary (first) contact from the response."""
        return self.contacts[0] if self.contacts else None

    @property
    def recipient_id(self) -> str | None:
        """Get the recipient identifier (BSUID if available, else wa_id)."""
        contact = self.primary_contact
        return contact.recipient_id if contact else None


class MessageResult(BaseModel):
    """Result of a messaging operation.

    Standard response model for all messaging operations across platforms.

    BSUID Support (v24.0+):
    - recipient_bsuid: BSUID if message was sent to BSUID
    - recipient_phone: Phone number (may be empty if sent to BSUID)
    - recipient: Recommended identifier (BSUID if available, else phone)
    - api_response: Full API response with contacts array
    """

    model_config = ConfigDict(use_enum_values=True)

    success: bool
    platform: PlatformType = PlatformType.WHATSAPP
    message_id: str | None = None
    recipient: str | None = Field(
        None,
        description="Recipient identifier (BSUID if available, else phone number)",
    )
    recipient_bsuid: str | None = Field(
        None,
        description="Business Scoped User ID if message was sent to BSUID",
    )
    recipient_phone: str | None = Field(
        None,
        description="Recipient phone number (may be empty if sent to BSUID)",
    )
    error: str | None = None
    error_code: str | None = None
    timestamp: datetime = Field(default_factory=_utc_now)
    tenant_id: str | None = None  # phone_number_id in WhatsApp context
    api_response: WhatsAppAPIResponse | None = Field(
        None,
        description="Full API response (for advanced use cases)",
        exclude=True,  # Don't include in default serialization
    )

    @classmethod
    def from_api_response(
        cls,
        response: WhatsAppAPIResponse,
        *,
        success: bool = True,
        tenant_id: str | None = None,
        error: str | None = None,
        error_code: str | None = None,
    ) -> "MessageResult":
        """Create MessageResult from WhatsApp API response.

        Args:
            response: The parsed WhatsApp API response
            success: Whether the operation was successful
            tenant_id: The business phone number ID
            error: Error message if any
            error_code: Error code if any

        Returns:
            MessageResult with BSUID-aware recipient fields
        """
        contact = response.primary_contact
        return cls(
            success=success,
            message_id=response.message_id,
            recipient=contact.recipient_id if contact else None,
            recipient_bsuid=contact.bsuid if contact else None,
            recipient_phone=contact.wa_id if contact and contact.wa_id else None,
            tenant_id=tenant_id,
            error=error,
            error_code=error_code,
            api_response=response,
        )


class BasicTextMessage(BaseModel):
    """Basic text message schema for send_text operations.

    Schema for sending text messages with optional reply and preview control.
    """

    text: str = Field(
        ..., min_length=1, max_length=4096, description="Text content of the message"
    )
    recipient: str = Field(
        ..., min_length=1, description="Recipient phone number or user identifier"
    )
    reply_to_message_id: str | None = Field(
        None, description="Message ID to reply to (creates a thread)"
    )
    disable_preview: bool = Field(
        False, description="Disable URL preview for links in the message"
    )


class ReadStatusMessage(BaseModel):
    """Read status message schema for mark_as_read operations.

    Schema for marking messages as read with optional typing indicator.
    Key requirement: typing boolean parameter for showing typing indicator.
    """

    message_id: str = Field(
        ..., min_length=1, description="WhatsApp message ID to mark as read"
    )
    typing: bool = Field(
        False, description="Show typing indicator when marking as read"
    )
