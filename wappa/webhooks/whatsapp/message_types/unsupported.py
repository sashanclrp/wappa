"""
WhatsApp unsupported message schema.

Pydantic model for WhatsApp unsupported message webhooks — sent when a user
sends a message type not supported by the Cloud API (e.g. unknown subtypes,
numbers already in use with the API). The payload always includes one or more
error objects explaining the cause.
"""

from typing import Any, Literal

from pydantic import ConfigDict, Field, field_validator

from wappa.schemas.core.types import (
    ConversationType,
    MessageType,
    PlatformType,
    UniversalMessageData,
)
from wappa.webhooks.core.base_message import BaseMessage, BaseMessageContext
from wappa.webhooks.whatsapp.base_models import (
    MessageContext,
    MessageError,
    WhatsAppMessageIdentity,
)

# WhatsApp error code for unknown/unsupported message subtypes.
_UNKNOWN_TYPE_ERROR_CODE = 131051


class WhatsAppUnsupportedMessage(WhatsAppMessageIdentity, BaseMessage):
    """
    WhatsApp unsupported message model.

    Represents messages rejected by the WhatsApp Cloud API with error
    information that explains why the content could not be delivered.
    The ``unsupported`` field carries the provider sub-payload WhatsApp
    attaches alongside ``"type": "unsupported"`` (v24.0+).
    """

    model_config = ConfigDict(
        extra="forbid", str_strip_whitespace=True, validate_assignment=True
    )

    # Standard identity fields (BSUID support v24.0+)
    from_: str = Field(
        default="",
        alias="from",
        description="Sender phone number (may be empty for username-only users)",
    )
    from_bsuid: str | None = Field(
        None,
        alias="from_user_id",
        description="Business Scoped User ID — stable sender identifier (v24.0+)",
    )
    id: str = Field(..., description="Unique WhatsApp message ID")
    timestamp_str: str = Field(
        ..., alias="timestamp", description="Unix timestamp when the message was sent"
    )
    type: Literal["unsupported"] = Field(..., description="Always 'unsupported'")

    # Provider sub-payload attached alongside the type discriminator.
    unsupported: dict[str, Any] | None = Field(
        None, description="Provider payload describing the unsupported message subtype"
    )

    errors: list[MessageError] = Field(
        ..., description="One or more errors explaining why the message is unsupported"
    )
    context: MessageContext | None = Field(
        None, description="Reply/forward context (rare for unsupported messages)"
    )

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------

    @field_validator("id")
    @classmethod
    def validate_message_id(cls, v: str) -> str:
        if not v or len(v) < 10:
            raise ValueError("WhatsApp message ID must be at least 10 characters")
        if not v.startswith("wamid."):
            raise ValueError("WhatsApp message ID should start with 'wamid.'")
        return v

    @field_validator("timestamp_str")
    @classmethod
    def validate_timestamp(cls, v: str) -> str:
        if not v.isdigit():
            raise ValueError("Timestamp must be numeric")
        ts = int(v)
        if ts < 1577836800 or ts > 4102444800:
            raise ValueError("Timestamp must be a valid Unix timestamp")
        return v

    @field_validator("errors")
    @classmethod
    def validate_errors(cls, v: list[MessageError]) -> list[MessageError]:
        if not v:
            raise ValueError("Unsupported messages must include error information")
        return v

    # ------------------------------------------------------------------
    # Identity helpers
    # ------------------------------------------------------------------

    @property
    def sender_id(self) -> str:
        """BSUID when available, otherwise the sender phone number."""
        if self.from_bsuid and self.from_bsuid.strip():
            return self.from_bsuid.strip()
        return self.from_

    @property
    def has_bsuid(self) -> bool:
        return bool(self.from_bsuid and self.from_bsuid.strip())

    @property
    def sender_phone(self) -> str:
        return self.from_

    # ------------------------------------------------------------------
    # Error helpers
    # ------------------------------------------------------------------

    @property
    def primary_error(self) -> MessageError:
        return self.errors[0]

    @property
    def error_codes(self) -> list[int]:
        return [error.code for error in self.errors]

    @property
    def error_messages(self) -> list[str]:
        return [error.message for error in self.errors]

    def has_error_code(self, code: int) -> bool:
        return code in self.error_codes

    def get_error_by_code(self, code: int) -> MessageError | None:
        return next((e for e in self.errors if e.code == code), None)

    def is_unknown_message_type(self) -> bool:
        """Return True when the error indicates an unknown message subtype (131051)."""
        return self.has_error_code(_UNKNOWN_TYPE_ERROR_CODE)

    def get_unsupported_reason(self) -> str:
        """Human-readable reason from the primary error."""
        return self.primary_error.message

    # ------------------------------------------------------------------
    # BaseMessage abstract implementations
    # ------------------------------------------------------------------

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
    def timestamp(self) -> int:
        return int(self.timestamp_str)

    @property
    def conversation_id(self) -> str:
        return self.group_id or self.sender_id

    @property
    def conversation_type(self) -> ConversationType:
        return ConversationType.GROUP if self.group_id else ConversationType.PRIVATE

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
            "error_count": len(self.errors),
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
                "error_count": len(self.errors),
                "is_unknown_message_type": self.is_unknown_message_type(),
                "primary_error": self.primary_error.model_dump(),
            },
        }

    @classmethod
    def from_platform_data(
        cls, data: dict[str, Any], **kwargs
    ) -> "WhatsAppUnsupportedMessage":
        return cls.model_validate(data)
