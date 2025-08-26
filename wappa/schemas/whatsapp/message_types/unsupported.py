"""
WhatsApp unsupported message schema.

This module contains Pydantic models for processing WhatsApp unsupported messages,
which are sent when users send message types not supported by the Cloud API.
"""

from typing import Any, Literal

from pydantic import ConfigDict, Field, field_validator

from wappa.schemas.core.base_message import BaseMessage, BaseMessageContext
from wappa.schemas.core.types import (
    ConversationType,
    MessageType,
    PlatformType,
    UniversalMessageData,
)
from wappa.schemas.whatsapp.base_models import MessageContext, MessageError


class WhatsAppUnsupportedMessage(BaseMessage):
    """
    WhatsApp unsupported message model.

    Represents messages that are not supported by the WhatsApp Cloud API, such as:
    - New message types not yet supported
    - Messages sent to numbers already in use with the API
    - Other unsupported content types

    These messages include error information explaining why they're unsupported.
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
    type: Literal["unsupported"] = Field(
        ..., description="Message type, always 'unsupported' for unsupported messages"
    )

    # Error information
    errors: list[MessageError] = Field(
        ..., description="List of errors explaining why the message is unsupported"
    )

    # Context field
    context: MessageContext | None = Field(
        None, description="Context for unsupported messages (rare)"
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

    @field_validator("errors")
    @classmethod
    def validate_errors(cls, v: list[MessageError]) -> list[MessageError]:
        """Validate errors list is not empty."""
        if not v or len(v) == 0:
            raise ValueError("Unsupported messages must include error information")
        return v

    @property
    def sender_phone(self) -> str:
        """Get the sender's phone number (clean accessor)."""
        return self.from_

    @property
    def error_count(self) -> int:
        """Get the number of errors."""
        return len(self.errors)

    @property
    def primary_error(self) -> MessageError:
        """Get the first (primary) error."""
        return self.errors[0]

    @property
    def error_codes(self) -> list[int]:
        """Get list of all error codes."""
        return [error.code for error in self.errors]

    @property
    def error_messages(self) -> list[str]:
        """Get list of all error messages."""
        return [error.message for error in self.errors]

    @property
    def unix_timestamp(self) -> int:
        """Get the timestamp as an integer."""
        return self.timestamp

    def has_error_code(self, code: int) -> bool:
        """Check if a specific error code is present."""
        return code in self.error_codes

    def get_error_by_code(self, code: int) -> MessageError | None:
        """Get the first error with the specified code."""
        for error in self.errors:
            if error.code == code:
                return error
        return None

    def is_unknown_message_type(self) -> bool:
        """Check if this is an unknown message type error (code 131051)."""
        return self.has_error_code(131051)

    def is_duplicate_phone_usage(self) -> bool:
        """
        Check if this error is due to sending to a number already in use.

        Note: This is based on the trigger description and may need adjustment
        based on actual error codes for this scenario.
        """
        # This would need to be updated with the actual error code
        # for duplicate phone number usage once documented
        return False

    def get_unsupported_reason(self) -> str:
        """
        Get a human-readable reason why the message is unsupported.

        Returns:
            Primary error message explaining the unsupported reason.
        """
        return self.primary_error.message

    def to_summary_dict(self) -> dict[str, str | bool | int | list]:
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
            "error_count": self.error_count,
            "error_codes": self.error_codes,
            "error_messages": self.error_messages,
            "primary_error_code": self.primary_error.code,
            "primary_error_message": self.primary_error.message,
            "is_unknown_message_type": self.is_unknown_message_type(),
            "unsupported_reason": self.get_unsupported_reason(),
        }

    # Implement abstract methods from BaseMessage

    @property
    def platform(self) -> PlatformType:
        return PlatformType.WHATSAPP

    @property
    def message_type(self) -> MessageType:
        return MessageType.UNSUPPORTED

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
            "error_count": self.error_count,
            "error_codes": self.error_codes,
            "primary_error_code": self.primary_error.code,
            "primary_error_message": self.primary_error.message,
            "unsupported_reason": self.get_unsupported_reason(),
            "whatsapp_data": {
                "whatsapp_id": self.id,
                "from": self.from_,
                "timestamp_str": self.timestamp_str,
                "type": self.type,
                "errors": [error.model_dump() for error in self.errors],
                "context": self.context.model_dump() if self.context else None,
            },
        }

    def get_platform_data(self) -> dict[str, Any]:
        return {
            "whatsapp_message_id": self.id,
            "from_phone": self.from_,
            "timestamp_str": self.timestamp_str,
            "message_type": self.type,
            "errors": [error.model_dump() for error in self.errors],
            "context": self.context.model_dump() if self.context else None,
            "error_analysis": {
                "error_count": self.error_count,
                "is_unknown_message_type": self.is_unknown_message_type(),
                "is_duplicate_phone_usage": self.is_duplicate_phone_usage(),
                "primary_error": self.primary_error.model_dump(),
            },
        }

    @classmethod
    def from_platform_data(
        cls, data: dict[str, Any], **kwargs
    ) -> "WhatsAppUnsupportedMessage":
        return cls.model_validate(data)
