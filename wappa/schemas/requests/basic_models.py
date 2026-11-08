"""Neutral HTTP request models for text sends and read receipts.

``text`` keeps WhatsApp's limit (``TEXT_MAX``); Instagram splits a longer
text into several messages (ADR-0028 rule 3).
"""

from pydantic import BaseModel, Field

from wappa.domain.interactive import TEXT_MAX
from wappa.schemas.core.recipient import DeliveryRequest, OpaqueAddress


class BasicTextMessage(DeliveryRequest):
    text: str = Field(
        ...,
        min_length=1,
        max_length=TEXT_MAX,
        description="Text content of the message",
    )
    reply_to_message_id: str | None = Field(
        None, description="Message ID to reply to (creates a thread)"
    )
    disable_preview: bool = Field(
        False, description="Disable URL preview for links in the message"
    )


class ReadStatusMessage(BaseModel):
    message_id: str = Field(..., min_length=1, description="Message ID to mark as read")
    recipient: OpaqueAddress = Field(
        ...,
        min_length=1,
        description=(
            "The User who sent the message; Instagram marks this User's thread "
            "seen, WhatsApp checks it against the Inbox"
        ),
    )
    typing: bool = Field(
        False, description="Show typing indicator when marking as read"
    )
