"""
WhatsApp system message schema.

This module contains Pydantic models for processing WhatsApp system messages,
which are generated when system events occur (e.g., user changes phone number).
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from wappa.schemas.core.recipient import looks_like_bsuid
from wappa.schemas.core.types import (
    MessageType,
    UniversalMessageData,
)
from wappa.webhooks.core.base_message import BaseMessage, BaseMessageContext
from wappa.webhooks.whatsapp.models.base import MessageContext

from ._base import WhatsAppMessageBase


class SystemContent(BaseModel):
    """System message content with BSUID support (v24.0+)."""

    model_config = ConfigDict(extra="allow", str_strip_whitespace=True)

    body: str = Field(..., description="System message text describing the event")
    wa_id: str | None = Field(
        None, description="New WhatsApp ID (for user_changed_number events)"
    )
    user_id: str | None = Field(
        None,
        description="Business Scoped User ID (BSUID) - for user_changed_user_id events",
    )
    previous_user_id: str | None = Field(
        None,
        description="Previous BSUID before the change (observed on user_changed_user_id events)",
    )
    parent_user_id: str | None = Field(
        None,
        description="Parent BSUID for a user_changed_user_id event when enabled",
    )
    type: Literal["user_changed_number", "user_changed_user_id"] = Field(
        ...,
        description="Type of system event (user_changed_number or user_changed_user_id)",
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

    @field_validator("user_id", "previous_user_id", "parent_user_id")
    @classmethod
    def validate_user_id(cls, v: str | None) -> str | None:
        """Validate BSUID if present."""
        if v is not None:
            v = v.strip()
            if not v:
                return None
            if not looks_like_bsuid(v):
                raise ValueError(
                    "User ID must use Meta's CC.<id> or CC.ENT.<id> format"
                )
        return v


class WhatsAppSystemMessage(WhatsAppMessageBase, BaseMessage):
    """
    WhatsApp system message model.

    Represents system-generated messages for events like:
    - User changing their phone number
    - Other system notifications

    Note: System messages don't include contact information unlike regular messages.
    """

    model_config = ConfigDict(
        extra="allow", str_strip_whitespace=True, validate_assignment=True
    )

    # Standard message fields (BSUID support v24.0+)
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
    def is_user_id_change(self) -> bool:
        """Check if this is a BSUID change event (v24.0+)."""
        return self.system.type == "user_changed_user_id"

    @property
    def new_user_id(self) -> str | None:
        """Get the new BSUID (for user_changed_user_id events)."""
        return self.system.user_id

    @property
    def previous_user_id(self) -> str | None:
        """Get the previous BSUID (for user_changed_user_id events)."""
        return self.system.previous_user_id

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

    def to_summary_dict(self) -> dict[str, str | bool | int | None]:
        """
        Create a summary dictionary for logging and analysis.

        Returns:
            Dictionary with key message information for structured logging.
        """
        old_number, new_number = self.extract_phone_numbers()

        return {
            "message_id": self.id,
            "sender": self.sender_phone,
            "sender_id": self.sender_id,
            "timestamp": self.unix_timestamp,
            "type": self.type,
            "system_event_type": self.system_event_type,
            "system_message": self.system_message,
            "is_number_change": self.is_number_change,
            "is_user_id_change": self.is_user_id_change,
            "old_phone_number": old_number,
            "new_phone_number": new_number,
            "new_wa_id": self.new_wa_id,
            "new_user_id": self.new_user_id,
            "user_name": self.extract_user_name(),
        }

    # Implement abstract methods from BaseMessage

    @property
    def message_type(self) -> MessageType:
        return MessageType.SYSTEM

    def has_context(self) -> bool:
        return self.context is not None

    def get_context(self) -> BaseMessageContext | None:
        from .context import WhatsAppMessageContext

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
            "is_user_id_change": self.is_user_id_change,
            "old_phone_number": old_number,
            "new_phone_number": new_number,
            "new_user_id": self.new_user_id,
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
                "is_user_id_change": self.is_user_id_change,
                "extracted_user_name": self.extract_user_name(),
                "phone_numbers": self.extract_phone_numbers(),
                "new_user_id": self.new_user_id,
            },
        }

    @classmethod
    def from_platform_data(
        cls, data: dict[str, Any], **kwargs: Any
    ) -> "WhatsAppSystemMessage":
        return cls.model_validate(data)
