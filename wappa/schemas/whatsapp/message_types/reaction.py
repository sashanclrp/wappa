"""
WhatsApp reaction message schema.

This module contains Pydantic models for processing WhatsApp reaction messages,
which are sent when users react to or remove reactions from business messages.
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


class ReactionContent(BaseModel):
    """Reaction message content."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    message_id: str = Field(..., description="ID of the message being reacted to")
    emoji: str | None = Field(
        None, description="Emoji Unicode (None if reaction is being removed)"
    )

    @field_validator("message_id")
    @classmethod
    def validate_message_id(cls, v: str) -> str:
        """Validate message ID format."""
        if not v.strip():
            raise ValueError("Message ID cannot be empty")
        # WhatsApp message IDs typically start with 'wamid.'
        if not v.startswith("wamid."):
            raise ValueError("Message ID should start with 'wamid.'")
        return v.strip()

    @field_validator("emoji")
    @classmethod
    def validate_emoji(cls, v: str | None) -> str | None:
        """Validate emoji format if present."""
        if v is not None:
            v = v.strip()
            if not v:
                return None
            # Basic validation - emoji should be reasonably short
            if len(v) > 20:  # Unicode representations can be long
                raise ValueError("Emoji representation too long")
        return v


class WhatsAppReactionMessage(BaseMessage):
    """
    WhatsApp reaction message model.

    Represents user reactions to business messages including:
    - Adding emoji reactions to messages
    - Removing emoji reactions from messages
    - Reactions to messages sent within the last 30 days
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
        ..., alias="timestamp", description="Unix timestamp when the reaction was sent"
    )
    type: Literal["reaction"] = Field(
        ..., description="Message type, always 'reaction' for reaction messages"
    )

    # Reaction content
    reaction: ReactionContent = Field(
        ..., description="Reaction details including target message and emoji"
    )

    # Context field
    context: MessageContext | None = Field(
        None, description="Context for reactions (rare)"
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
        """Get the sender's phone number (clean accessor)."""
        return self.from_

    @property
    def target_message_id(self) -> str:
        """Get the ID of the message being reacted to."""
        return self.reaction.message_id

    @property
    def emoji(self) -> str | None:
        """Get the reaction emoji."""
        return self.reaction.emoji

    @property
    def is_adding_reaction(self) -> bool:
        """Check if this is adding a reaction (emoji present)."""
        return self.reaction.emoji is not None

    @property
    def is_removing_reaction(self) -> bool:
        """Check if this is removing a reaction (no emoji)."""
        return self.reaction.emoji is None

    @property
    def unix_timestamp(self) -> int:
        """Get the timestamp as an integer."""
        return self.timestamp

    def get_emoji_display(self) -> str:
        """
        Get a display-friendly emoji representation.

        Returns:
            The emoji if present, or "[removed]" if reaction was removed.
        """
        if self.is_adding_reaction:
            return self.emoji
        return "[removed]"

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
            "target_message_id": self.target_message_id,
            "emoji": self.emoji,
            "emoji_display": self.get_emoji_display(),
            "is_adding_reaction": self.is_adding_reaction,
            "is_removing_reaction": self.is_removing_reaction,
        }

    # Implement abstract methods from BaseMessage

    @property
    def platform(self) -> PlatformType:
        return PlatformType.WHATSAPP

    @property
    def message_type(self) -> MessageType:
        return MessageType.REACTION

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
            "target_message_id": self.target_message_id,
            "emoji": self.emoji,
            "is_adding_reaction": self.is_adding_reaction,
            "is_removing_reaction": self.is_removing_reaction,
            "whatsapp_data": {
                "whatsapp_id": self.id,
                "from": self.from_,
                "timestamp_str": self.timestamp_str,
                "type": self.type,
                "reaction_content": self.reaction.model_dump(),
                "context": self.context.model_dump() if self.context else None,
            },
        }

    def get_platform_data(self) -> dict[str, Any]:
        return {
            "whatsapp_message_id": self.id,
            "from_phone": self.from_,
            "timestamp_str": self.timestamp_str,
            "message_type": self.type,
            "reaction_content": self.reaction.model_dump(),
            "context": self.context.model_dump() if self.context else None,
            "reaction_details": {
                "target_message_id": self.target_message_id,
                "emoji_display": self.get_emoji_display(),
                "is_adding": self.is_adding_reaction,
                "is_removing": self.is_removing_reaction,
            },
        }

    @classmethod
    def from_platform_data(
        cls, data: dict[str, Any], **kwargs
    ) -> "WhatsAppReactionMessage":
        return cls.model_validate(data)
