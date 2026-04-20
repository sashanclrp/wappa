"""Basic message models for WhatsApp messaging."""

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

from wappa.schemas.core.recipient import RecipientRequest
from wappa.schemas.core.types import PlatformType


def _utc_now() -> datetime:
    return datetime.now(UTC)


class ResponseContact(BaseModel):
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
        if self.bsuid and self.bsuid.strip():
            return self.bsuid.strip()
        return self.wa_id or self.input

    @property
    def has_bsuid(self) -> bool:
        return bool(self.bsuid and self.bsuid.strip())

    @property
    def was_sent_to_bsuid(self) -> bool:
        return self.has_bsuid and not self.wa_id


class ResponseMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(..., description="WhatsApp message ID")
    message_status: str | None = Field(
        None, description="Message status (e.g., 'accepted')"
    )


class WhatsAppAPIResponse(BaseModel):
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
        return self.messages[0].id if self.messages else None

    @property
    def primary_contact(self) -> ResponseContact | None:
        return self.contacts[0] if self.contacts else None

    @property
    def recipient_id(self) -> str | None:
        contact = self.primary_contact
        return contact.recipient_id if contact else None


class MessageResult(BaseModel):
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
        exclude=True,
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

    @classmethod
    def from_response_payload(
        cls,
        response_payload: dict,
        *,
        tenant_id: str | None = None,
        fallback_recipient: str | None = None,
    ) -> "MessageResult":
        response = WhatsAppAPIResponse.model_validate(response_payload)
        result = cls.from_api_response(response, tenant_id=tenant_id)
        if result.recipient is None:
            result.recipient = fallback_recipient
        return result


class BasicTextMessage(RecipientRequest):
    text: str = Field(
        ..., min_length=1, max_length=4096, description="Text content of the message"
    )
    reply_to_message_id: str | None = Field(
        None, description="Message ID to reply to (creates a thread)"
    )
    disable_preview: bool = Field(
        False, description="Disable URL preview for links in the message"
    )


class ReadStatusMessage(BaseModel):
    message_id: str = Field(
        ..., min_length=1, description="WhatsApp message ID to mark as read"
    )
    typing: bool = Field(
        False, description="Show typing indicator when marking as read"
    )
