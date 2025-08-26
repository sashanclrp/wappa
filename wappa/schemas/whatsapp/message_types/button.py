"""
WhatsApp button message schema.

This module contains Pydantic models for processing WhatsApp button reply messages,
which are sent when users tap quick-reply buttons in template messages.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from wappa.schemas.core.base_message import BaseMessage, BaseMessageContext
from wappa.schemas.core.types import (
    ConversationType,
    MessageType,
    PlatformType,
    UniversalMessageData,
)
from wappa.schemas.whatsapp.base_models import MessageContext


class ButtonContent(BaseModel):
    """Button reply content."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    payload: str = Field(..., description="Button payload data")
    text: str = Field(
        ..., description="Button label text that was displayed to the user"
    )

    @field_validator("payload", "text")
    @classmethod
    def validate_button_fields(cls, v: str) -> str:
        """Validate button fields are not empty."""
        if not v.strip():
            raise ValueError("Button payload and text cannot be empty")
        return v.strip()


class WhatsAppButtonMessage(BaseMessage):
    """
    WhatsApp button message model.

    Represents a user's response to tapping a quick-reply button in a template message.
    These messages always include context information linking to the original message.
    """

    model_config = ConfigDict(
        extra="forbid", str_strip_whitespace=True, validate_assignment=True
    )

    # Standard message fields
    from_: str = Field(
        ..., alias="from", description="WhatsApp user phone number who sent the message"
    )
    id: str = Field(..., description="Unique WhatsApp message ID")
    timestamp_str: str = Field(
        ..., alias="timestamp", description="Unix timestamp when the message was sent"
    )
    type: Literal["button"] = Field(
        ..., description="Message type, always 'button' for button messages"
    )

    # Button content
    button: ButtonContent = Field(..., description="Button reply content and metadata")

    # Required context (button messages always have context)
    context: MessageContext = Field(
        ..., description="Context linking to the original message with the button"
    )

    @field_validator("from_")
    @classmethod
    def validate_from_phone(cls, v: str) -> str:
        """Validate sender phone number format."""
        if not v or len(v) < 8:
            raise ValueError("Sender phone number must be at least 8 characters")
        # Remove common prefixes and validate numeric
        phone = v.replace("+", "").replace("-", "").replace(" ", "")
        if not phone.isdigit():
            raise ValueError("Phone number must contain only digits (and +)")
        return v

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

    @model_validator(mode="after")
    def validate_button_message_context(self):
        """Validate button message has proper context."""
        # Button messages must have context with message ID and sender
        if not self.context.id:
            raise ValueError(
                "Button messages must have context with original message ID"
            )

        if not self.context.from_:
            raise ValueError("Button messages must have context with original sender")

        # Button messages should not have forwarding or product context
        if self.context.forwarded or self.context.frequently_forwarded:
            raise ValueError("Button messages cannot be forwarded")

        if self.context.referred_product:
            raise ValueError("Button messages should not have product context")

        return self

    @property
    def sender_phone(self) -> str:
        """Get the sender's phone number (clean accessor)."""
        return self.from_

    @property
    def button_text(self) -> str:
        """Get the button label text."""
        return self.button.text

    @property
    def button_payload(self) -> str:
        """Get the button payload data."""
        return self.button.payload

    @property
    def original_message_id(self) -> str:
        """Get the ID of the original message that contained the button."""
        return self.context.id

    @property
    def business_phone(self) -> str:
        """Get the business phone number that sent the original message."""
        return self.context.from_

    @property
    def unix_timestamp(self) -> int:
        """Get the timestamp as an integer."""
        return self.timestamp

    def get_button_context(self) -> tuple[str, str]:
        """
        Get button context information.

        Returns:
            Tuple of (business_phone, original_message_id) for the button interaction.
        """
        return (self.business_phone, self.original_message_id)

    def to_summary_dict(self) -> dict[str, str | bool | int]:
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
            "button_text": self.button_text,
            "button_payload": self.button_payload,
            "original_message_id": self.original_message_id,
            "business_phone": self.business_phone,
        }

    # Implement abstract methods from BaseMessage

    @property
    def platform(self) -> PlatformType:
        return PlatformType.WHATSAPP

    @property
    def message_type(self) -> MessageType:
        return MessageType.BUTTON

    @property
    def message_id(self) -> str:
        return self.id

    @property
    def sender_id(self) -> str:
        return self.from_

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
        return True  # Button messages always have context

    def get_context(self) -> BaseMessageContext | None:
        from .text import WhatsAppMessageContext

        return WhatsAppMessageContext(self.context)

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
            "button_text": self.button_text,
            "button_payload": self.button_payload,
            "original_message_id": self.original_message_id,
            "whatsapp_data": {
                "whatsapp_id": self.id,
                "from": self.from_,
                "timestamp_str": self.timestamp_str,
                "type": self.type,
                "button_content": self.button.model_dump(),
                "context": self.context.model_dump(),
            },
        }

    def get_platform_data(self) -> dict[str, Any]:
        return {
            "whatsapp_message_id": self.id,
            "from_phone": self.from_,
            "timestamp_str": self.timestamp_str,
            "message_type": self.type,
            "button_content": self.button.model_dump(),
            "context": self.context.model_dump(),
            "interaction_details": {
                "button_text": self.button_text,
                "button_payload": self.button_payload,
                "business_phone": self.business_phone,
            },
        }

    @classmethod
    def from_platform_data(
        cls, data: dict[str, Any], **kwargs
    ) -> "WhatsAppButtonMessage":
        return cls.model_validate(data)
