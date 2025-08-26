"""
Basic message models for WhatsApp messaging.

Pydantic schemas for basic messaging operations: send_text and mark_as_read.
"""

from datetime import datetime

from pydantic import BaseModel, Field

from wappa.schemas.core.types import PlatformType


class MessageResult(BaseModel):
    """Result of a messaging operation.

    Standard response model for all messaging operations across platforms.
    """

    success: bool
    platform: PlatformType = PlatformType.WHATSAPP
    message_id: str | None = None
    recipient: str | None = None
    error: str | None = None
    error_code: str | None = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    tenant_id: str | None = None  # phone_number_id in WhatsApp context

    class Config:
        use_enum_values = True


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
