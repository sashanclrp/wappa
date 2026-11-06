"""
WhatsApp button message schema.

This module contains Pydantic models for processing WhatsApp button reply messages,
which are sent when users tap quick-reply buttons in template messages.
"""

from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from wappa.schemas.core.types import (
    InteractiveType,
    MessageType,
    UniversalMessageData,
)
from wappa.webhooks.core.base_message import BaseMessage, BaseMessageContext
from wappa.webhooks.whatsapp.models.base import MessageContext

from ._base import WhatsAppMessageBase


class ButtonContent(BaseModel):
    """Button reply content."""

    model_config = ConfigDict(extra="allow", str_strip_whitespace=True)

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


class WhatsAppButtonMessage(WhatsAppMessageBase, BaseMessage):
    """
    WhatsApp button message model.

    Represents a user's response to tapping a quick-reply button in a template message.
    These messages always include context information linking to the original message.
    """

    model_config = ConfigDict(
        extra="allow", str_strip_whitespace=True, validate_assignment=True
    )

    # Standard message fields (BSUID support v24.0+)
    type: Literal["button"] = Field(
        ..., description="Message type, always 'button' for button messages"
    )

    # Button content
    button: ButtonContent = Field(..., description="Button reply content and metadata")

    # Optional context: Meta omits it for template quick-reply taps
    context: MessageContext | None = Field(
        None,
        description=(
            "Context linking to the original message with the button. "
            "Absent for quick-reply taps on template messages."
        ),
    )

    @model_validator(mode="after")
    def validate_button_message_context(self) -> Self:
        """Validate button message context when Meta includes one."""
        # Template quick-reply taps arrive without a context block at all
        if self.context is None:
            return self

        # Button messages should not have forwarding or product context
        if self.context.forwarded or self.context.frequently_forwarded:
            raise ValueError("Button messages cannot be forwarded")

        if self.context.referred_product:
            raise ValueError("Button messages should not have product context")

        return self

    @property
    def button_text(self) -> str:
        """Get the button label text."""
        return self.button.text

    @property
    def button_payload(self) -> str:
        """Get the button payload data."""
        return self.button.payload

    @property
    def interactive_type(self) -> InteractiveType:
        """A carousel or Template quick-reply tap is a quick-reply selection."""
        return InteractiveType.QUICK_REPLY

    @property
    def text_content(self) -> str:
        """Expose the button label as text so universal text accessors work."""
        return self.button.text

    @property
    def original_message_id(self) -> str | None:
        """Get the ID of the original message that contained the button."""
        return self.context.id if self.context else None

    @property
    def business_phone(self) -> str | None:
        """Get the business phone number that sent the original message."""
        return self.context.from_ if self.context else None

    def get_button_context(self) -> tuple[str | None, str | None]:
        """
        Get button context information.

        Returns:
            Tuple of (business_phone, original_message_id) for the button interaction,
            with None entries when Meta omits the context block.
        """
        return (self.business_phone, self.original_message_id)

    def to_summary_dict(self) -> dict[str, str | bool | int | None]:
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
    def message_type(self) -> MessageType:
        return MessageType.BUTTON

    def has_context(self) -> bool:
        return self.context is not None

    def get_context(self) -> BaseMessageContext | None:
        from .context import WhatsAppMessageContext

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
                "context": self.context.model_dump() if self.context else None,
            },
        }

    def get_platform_data(self) -> dict[str, Any]:
        return {
            "whatsapp_message_id": self.id,
            "from_phone": self.from_,
            "timestamp_str": self.timestamp_str,
            "message_type": self.type,
            "button_content": self.button.model_dump(),
            "context": self.context.model_dump() if self.context else None,
            "interaction_details": {
                "button_text": self.button_text,
                "button_payload": self.button_payload,
                "business_phone": self.business_phone,
            },
        }

    @classmethod
    def from_platform_data(
        cls, data: dict[str, Any], **kwargs: Any
    ) -> "WhatsAppButtonMessage":
        return cls.model_validate(data)
