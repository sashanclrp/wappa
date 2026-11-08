"""WhatsApp Cloud API send-response models and their ``MessageResult`` builders.

The neutral HTTP request models live in ``wappa.schemas.requests``.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from wappa.domain.inbox.identity import InboxRef
from wappa.domain.results import MessageResult
from wappa.messaging.whatsapp.identity import whatsapp_identity
from wappa.schemas.core.types import PlatformType


class ResponseProfile(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str | None = None
    username: str | None = None


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
    parent_bsuid: str | None = Field(default=None, alias="parent_user_id")
    username: str | None = None
    profile: ResponseProfile | None = None

    @property
    def resolved_username(self) -> str | None:
        return self.username or (self.profile.username if self.profile else None)

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


def message_result_from_api_response(
    response: WhatsAppAPIResponse,
    *,
    success: bool = True,
    inbox_id: str | None = None,
    error: str | None = None,
    error_code: str | None = None,
    raw: dict[str, Any] | None = None,
) -> MessageResult:
    """Build the neutral ``MessageResult`` from a parsed Cloud API response.

    ``raw`` is the native response body; when absent, the parsed response is
    dumped so ``platform_response`` always carries the native evidence.
    """
    contact = response.primary_contact
    return MessageResult(
        success=success,
        platform=PlatformType.WHATSAPP,
        message_id=response.message_id,
        recipient=contact.recipient_id if contact else None,
        recipient_bsuid=contact.bsuid if contact else None,
        recipient_phone=contact.wa_id if contact and contact.wa_id else None,
        recipient_parent_bsuid=contact.parent_bsuid if contact else None,
        recipient_username=contact.resolved_username if contact else None,
        inbox_id=inbox_id,
        error=error,
        error_code=error_code,
        platform_response=(
            raw if raw is not None else response.model_dump(by_alias=True)
        ),
    )


def message_result_from_payload(
    response_payload: dict[str, Any],
    *,
    inbox_id: str | None = None,
    fallback_recipient: str | None = None,
) -> MessageResult:
    """Build the neutral ``MessageResult`` from a raw Cloud API send response."""
    response = WhatsAppAPIResponse.model_validate(response_payload)
    result = message_result_from_api_response(
        response, inbox_id=inbox_id, raw=response_payload
    )
    if result.recipient is None:
        result.recipient = fallback_recipient
        if fallback_recipient and inbox_id:
            identity = whatsapp_identity(
                InboxRef.whatsapp(inbox_id), fallback_recipient, (fallback_recipient,)
            )
            result.recipient_phone = identity.phone_number
            result.recipient_bsuid = identity.bsuid
            result.recipient_parent_bsuid = identity.parent_bsuid
    return result
