"""
WhatsApp interactive message schema.

This module contains Pydantic models for processing WhatsApp interactive
message replies, including button replies and list selection replies.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from wappa.webhooks.core.base_message import BaseInteractiveMessage, BaseMessageContext
from wappa.webhooks.core.types import (
    ConversationType,
    InteractiveType,
    PlatformType,
    UniversalMessageData,
)
from wappa.webhooks.whatsapp.base_models import MessageContext


class ButtonReply(BaseModel):
    """Reply data from an interactive button."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str = Field(..., description="Button ID (set when creating the button)")
    title: str = Field(..., description="Button label text displayed to user")

    @field_validator("id", "title")
    @classmethod
    def validate_not_empty(cls, v: str) -> str:
        """Validate button fields are not empty."""
        if not v.strip():
            raise ValueError("Button ID and title cannot be empty")
        return v.strip()

    @field_validator("title")
    @classmethod
    def validate_title_length(cls, v: str) -> str:
        """Validate button title length (WhatsApp limit is 20 characters)."""
        if len(v) > 20:
            raise ValueError("Button title cannot exceed 20 characters")
        return v


class ListReply(BaseModel):
    """Reply data from an interactive list selection."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str = Field(..., description="Row ID (set when creating the list row)")
    title: str = Field(..., description="Row title displayed to user")
    description: str = Field(..., description="Row description displayed to user")

    @field_validator("id", "title", "description")
    @classmethod
    def validate_not_empty(cls, v: str) -> str:
        """Validate list fields are not empty."""
        if not v.strip():
            raise ValueError("List row fields cannot be empty")
        return v.strip()

    @field_validator("title")
    @classmethod
    def validate_title_length(cls, v: str) -> str:
        """Validate list title length (WhatsApp limit is 24 characters)."""
        if len(v) > 24:
            raise ValueError("List row title cannot exceed 24 characters")
        return v

    @field_validator("description")
    @classmethod
    def validate_description_length(cls, v: str) -> str:
        """Validate list description length (WhatsApp limit is 72 characters)."""
        if len(v) > 72:
            raise ValueError("List row description cannot exceed 72 characters")
        return v


class InteractiveContent(BaseModel):
    """
    Interactive message content.

    Contains either button_reply or list_reply based on the interaction type.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    type: Literal["button_reply", "list_reply"] = Field(
        ..., description="Type of interactive reply"
    )
    button_reply: ButtonReply | None = Field(
        None, description="Button reply data (only if type='button_reply')"
    )
    list_reply: ListReply | None = Field(
        None, description="List reply data (only if type='list_reply')"
    )

    @model_validator(mode="after")
    def validate_interactive_content(self):
        """Validate that the correct reply type is present."""
        if self.type == "button_reply":
            if self.button_reply is None:
                raise ValueError("button_reply is required when type='button_reply'")
            if self.list_reply is not None:
                raise ValueError("list_reply must be None when type='button_reply'")
        elif self.type == "list_reply":
            if self.list_reply is None:
                raise ValueError("list_reply is required when type='list_reply'")
            if self.button_reply is not None:
                raise ValueError("button_reply must be None when type='list_reply'")

        return self


class WhatsAppInteractiveMessage(BaseInteractiveMessage):
    """
    WhatsApp interactive message reply model.

    Handles replies from interactive buttons and list selections.
    These messages are always responses to interactive content sent by the business.
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
        ..., alias="timestamp", description="Unix timestamp when the reply was sent"
    )
    type: Literal["interactive"] = Field(
        ..., description="Message type, always 'interactive' for interactive replies"
    )

    # Interactive content
    interactive: InteractiveContent = Field(
        ..., description="Interactive reply content"
    )

    # Context is required for interactive messages (references original message)
    context: MessageContext = Field(
        ..., description="Context referencing the original interactive message"
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

    @model_validator(mode="after")
    def validate_context_required(self):
        """Validate that context is properly set for interactive messages."""
        if not self.context.id:
            raise ValueError(
                "Interactive messages must reference the original message ID in context"
            )
        if not self.context.from_:
            raise ValueError(
                "Interactive messages must reference the original sender in context"
            )

        # Interactive messages should not have forwarding or product context
        if self.context.forwarded or self.context.frequently_forwarded:
            raise ValueError("Interactive messages cannot be forwarded")
        if self.context.referred_product:
            raise ValueError("Interactive messages should not have product context")

        return self

    @property
    def is_button_reply(self) -> bool:
        """Check if this is a button reply."""
        return self.interactive.type == "button_reply"

    @property
    def is_list_reply(self) -> bool:
        """Check if this is a list selection reply."""
        return self.interactive.type == "list_reply"

    @property
    def sender_phone(self) -> str:
        """Get the sender's phone number (clean accessor)."""
        return self.from_

    @property
    def unix_timestamp(self) -> int:
        """Get the timestamp as an integer."""
        return self.timestamp

    @property
    def original_message_id(self) -> str:
        """Get the ID of the original interactive message."""
        return self.context.id

    @property
    def original_sender(self) -> str:
        """Get the sender of the original interactive message (business number)."""
        return self.context.from_

    def get_button_data(self) -> tuple[str | None, str | None]:
        """
        Get button reply data.

        Returns:
            Tuple of (button_id, button_title) if this is a button reply,
            (None, None) otherwise.
        """
        if self.is_button_reply and self.interactive.button_reply:
            reply = self.interactive.button_reply
            return (reply.id, reply.title)
        return (None, None)

    def get_list_data(self) -> tuple[str | None, str | None, str | None]:
        """
        Get list selection data.

        Returns:
            Tuple of (row_id, row_title, row_description) if this is a list reply,
            (None, None, None) otherwise.
        """
        if self.is_list_reply and self.interactive.list_reply:
            reply = self.interactive.list_reply
            return (reply.id, reply.title, reply.description)
        return (None, None, None)

    def get_selected_option_id(self) -> str | None:
        """
        Get the ID of the selected option (works for both buttons and lists).

        Returns:
            The button ID or list row ID, depending on the interaction type.
        """
        if self.is_button_reply and self.interactive.button_reply:
            return self.interactive.button_reply.id
        elif self.is_list_reply and self.interactive.list_reply:
            return self.interactive.list_reply.id
        return None

    def get_selected_option_title(self) -> str | None:
        """
        Get the title of the selected option (works for both buttons and lists).

        Returns:
            The button title or list row title, depending on the interaction type.
        """
        if self.is_button_reply and self.interactive.button_reply:
            return self.interactive.button_reply.title
        elif self.is_list_reply and self.interactive.list_reply:
            return self.interactive.list_reply.title
        return None

    def to_summary_dict(self) -> dict[str, str | bool | int]:
        """
        Create a summary dictionary for logging and analysis.

        Returns:
            Dictionary with key message information for structured logging.
        """
        summary = {
            "message_id": self.id,
            "sender": self.sender_phone,
            "timestamp": self.unix_timestamp,
            "type": self.type,
            "interactive_type": self.interactive.type,
            "original_message_id": self.original_message_id,
            "original_sender": self.original_sender,
            "selected_option_id": self.get_selected_option_id(),
            "selected_option_title": self.get_selected_option_title(),
            "is_button_reply": self.is_button_reply,
            "is_list_reply": self.is_list_reply,
        }

        # Add type-specific data
        if self.is_list_reply:
            _, _, description = self.get_list_data()
            summary["list_description"] = description

        return summary

    # Implement abstract methods from BaseMessage

    @property
    def platform(self) -> PlatformType:
        """Get the platform this message came from."""
        return PlatformType.WHATSAPP

    @property
    def message_id(self) -> str:
        """Get the unique message identifier."""
        return self.id

    @property
    def timestamp(self) -> int:
        """Get the message timestamp as Unix timestamp."""
        return int(self.timestamp_str)

    @property
    def conversation_id(self) -> str:
        """Get the conversation/chat identifier."""
        return self.from_

    @property
    def conversation_type(self) -> ConversationType:
        """Get the type of conversation."""
        return ConversationType.PRIVATE

    def has_context(self) -> bool:
        """Check if this message has context."""
        return True  # Interactive messages always have context

    def get_context(self) -> BaseMessageContext | None:
        """Get message context if available."""
        # Import here to avoid circular imports
        from .text import WhatsAppMessageContext

        return WhatsAppMessageContext(self.context)

    def to_universal_dict(self) -> UniversalMessageData:
        """Convert to platform-agnostic dictionary representation."""
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
            "interactive_type": self.interactive_type.value,
            "selected_option_id": self.selected_option_id,
            "selected_option_title": self.selected_option_title,
            "original_message_id": self.original_message_id,
            "is_button_reply": self.is_button_reply(),
            "is_list_reply": self.is_list_reply(),
            "context": self.get_context().to_universal_dict()
            if self.has_context()
            else None,
            "whatsapp_data": {
                "whatsapp_id": self.id,
                "from": self.from_,
                "timestamp_str": self.timestamp_str,
                "type": self.type,
                "interactive_content": self.interactive.model_dump(),
                "context": self.context.model_dump(),
            },
        }

    def get_platform_data(self) -> dict[str, Any]:
        """Get platform-specific data for advanced processing."""
        return {
            "whatsapp_message_id": self.id,
            "from_phone": self.from_,
            "timestamp_str": self.timestamp_str,
            "message_type": self.type,
            "interactive_content": self.interactive.model_dump(),
            "context": self.context.model_dump(),
            "button_data": self.get_button_data(),
            "list_data": self.get_list_data(),
        }

    # Implement abstract methods from BaseInteractiveMessage

    @property
    def interactive_type(self) -> InteractiveType:
        """Get the type of interactive element."""
        if self.interactive.type == "button_reply":
            return InteractiveType.BUTTON_REPLY
        elif self.interactive.type == "list_reply":
            return InteractiveType.LIST_REPLY
        else:
            return InteractiveType.BUTTON_REPLY  # Default fallback

    @property
    def selected_option_id(self) -> str:
        """Get the ID of the selected option."""
        return self.get_selected_option_id() or ""

    @property
    def selected_option_title(self) -> str:
        """Get the title/text of the selected option."""
        return self.get_selected_option_title() or ""

    @classmethod
    def from_platform_data(
        cls, data: dict[str, Any], **kwargs
    ) -> "WhatsAppInteractiveMessage":
        """Create message instance from WhatsApp-specific data."""
        return cls.model_validate(data)
