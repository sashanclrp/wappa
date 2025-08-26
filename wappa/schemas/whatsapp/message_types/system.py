"""
WhatsApp system message schema.

This module contains Pydantic models for processing WhatsApp system messages,
which are generated when system events occur (e.g., user changes phone number).
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from wappa.schemas.core.base_message import BaseMessage, BaseMessageContext
from wappa.schemas.core.types import (
    ConversationType,
    MessageType,
    PlatformType,
    UniversalMessageData,
)
from wappa.schemas.whatsapp.base_models import MessageContext


class SystemContent(BaseModel):
    """System message content."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    body: str = Field(..., description="System message text describing the event")
    wa_id: str | None = Field(
        None, description="New WhatsApp ID (for user_changed_number events)"
    )
    type: Literal["user_changed_number"] = Field(
        ..., description="Type of system event"
    )

    @field_validator("body")
    @classmethod
    def validate_body(cls, v: str) -> str:
        """Validate system message body."""
        if not v.strip():
            raise ValueError("System message body cannot be empty")
        return v.strip()

    @field_validator("wa_id")
    @classmethod
    def validate_wa_id(cls, v: str | None) -> str | None:
        """Validate WhatsApp ID if present."""
        if v is not None:
            v = v.strip()
            if not v:
                return None
            if len(v) < 8:
                raise ValueError("WhatsApp ID must be at least 8 characters")
        return v


class WhatsAppSystemMessage(BaseMessage):
    """
    WhatsApp system message model.

    Represents system-generated messages for events like:
    - User changing their phone number
    - Other system notifications

    Note: System messages don't include contact information unlike regular messages.
    """

    model_config = ConfigDict(
        extra="forbid", str_strip_whitespace=True, validate_assignment=True
    )

    # Standard message fields
    from_: str = Field(
        ...,
        alias="from",
        description="WhatsApp user phone number (old number for number changes)",
    )
    id: str = Field(..., description="Unique WhatsApp message ID")
    timestamp_str: str = Field(
        ...,
        alias="timestamp",
        description="Unix timestamp when the system event occurred",
    )
    type: Literal["system"] = Field(
        ..., description="Message type, always 'system' for system messages"
    )

    # System content
    system: SystemContent = Field(..., description="System event details")

    # Context field (though system messages typically don't have context)
    context: MessageContext | None = Field(
        None, description="Context for system messages (rare)"
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

    @property
    def sender_phone(self) -> str:
        """Get the sender's phone number (old number for number changes)."""
        return self.from_

    @property
    def system_event_type(self) -> str:
        """Get the type of system event."""
        return self.system.type

    @property
    def system_message(self) -> str:
        """Get the system message text."""
        return self.system.body

    @property
    def new_wa_id(self) -> str | None:
        """Get the new WhatsApp ID (for number change events)."""
        return self.system.wa_id

    @property
    def is_number_change(self) -> bool:
        """Check if this is a phone number change event."""
        return self.system.type == "user_changed_number"

    @property
    def unix_timestamp(self) -> int:
        """Get the timestamp as an integer."""
        return self.timestamp

    def extract_phone_numbers(self) -> tuple[str | None, str | None]:
        """
        Extract old and new phone numbers from number change message.

        Returns:
            Tuple of (old_number, new_number) for number change events,
            (None, None) for other system events.
        """
        if not self.is_number_change:
            return (None, None)

        # The old number is in the 'from' field
        old_number = self.sender_phone

        # Try to extract new number from the message body
        # Format: "User <name> changed from <old> to <new>"
        try:
            message = self.system_message
            if " changed from " in message and " to " in message:
                parts = message.split(" to ")
                if len(parts) >= 2:
                    # Extract the new number (last part, cleaned)
                    new_number = parts[-1].strip()
                    return (old_number, new_number)
        except Exception:
            pass

        return (old_number, None)

    def extract_user_name(self) -> str | None:
        """
        Extract user name from system message.

        Returns:
            User name if found in message, None otherwise.
        """
        try:
            message = self.system_message
            if message.startswith("User ") and " changed from " in message:
                # Format: "User <name> changed from <old> to <new>"
                parts = message.split(" changed from ")
                if len(parts) >= 1:
                    user_part = parts[0].replace("User ", "", 1).strip()
                    return user_part
        except Exception:
            pass

        return None

    def to_summary_dict(self) -> dict[str, str | bool | int]:
        """
        Create a summary dictionary for logging and analysis.

        Returns:
            Dictionary with key message information for structured logging.
        """
        old_number, new_number = self.extract_phone_numbers()

        return {
            "message_id": self.id,
            "sender": self.sender_phone,
            "timestamp": self.unix_timestamp,
            "type": self.type,
            "system_event_type": self.system_event_type,
            "system_message": self.system_message,
            "is_number_change": self.is_number_change,
            "old_phone_number": old_number,
            "new_phone_number": new_number,
            "new_wa_id": self.new_wa_id,
            "user_name": self.extract_user_name(),
        }

    # Implement abstract methods from BaseMessage

    @property
    def platform(self) -> PlatformType:
        return PlatformType.WHATSAPP

    @property
    def message_type(self) -> MessageType:
        return MessageType.SYSTEM

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
        return self.context is not None

    def get_context(self) -> BaseMessageContext | None:
        from .text import WhatsAppMessageContext

        return WhatsAppMessageContext(self.context) if self.context else None

    def to_universal_dict(self) -> UniversalMessageData:
        old_number, new_number = self.extract_phone_numbers()
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
            "system_event_type": self.system_event_type,
            "system_message": self.system_message,
            "is_number_change": self.is_number_change,
            "old_phone_number": old_number,
            "new_phone_number": new_number,
            "whatsapp_data": {
                "whatsapp_id": self.id,
                "from": self.from_,
                "timestamp_str": self.timestamp_str,
                "type": self.type,
                "system_content": self.system.model_dump(),
                "context": self.context.model_dump() if self.context else None,
            },
        }

    def get_platform_data(self) -> dict[str, Any]:
        return {
            "whatsapp_message_id": self.id,
            "from_phone": self.from_,
            "timestamp_str": self.timestamp_str,
            "message_type": self.type,
            "system_content": self.system.model_dump(),
            "context": self.context.model_dump() if self.context else None,
            "system_analysis": {
                "event_type": self.system_event_type,
                "is_number_change": self.is_number_change,
                "extracted_user_name": self.extract_user_name(),
                "phone_numbers": self.extract_phone_numbers(),
            },
        }

    @classmethod
    def from_platform_data(
        cls, data: dict[str, Any], **kwargs
    ) -> "WhatsAppSystemMessage":
        return cls.model_validate(data)
