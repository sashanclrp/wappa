"""Message and message-context base classes shared by every message type."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from wappa.schemas.core.types import (
    ConversationType,
    MessageType,
    PlatformType,
    UniversalMessageData,
)


class BaseMessageContext(BaseModel, ABC):
    """
    Platform-agnostic message context base class.

    Represents context information for replies, forwards, and threaded messages.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @property
    @abstractmethod
    def original_message_id(self) -> str | None:
        """Get the ID of the original message being replied to or forwarded."""
        pass

    @property
    @abstractmethod
    def original_sender_id(self) -> str | None:
        """Get the sender ID of the original message."""
        pass

    @property
    @abstractmethod
    def is_reply(self) -> bool:
        """Check if this represents a reply context."""
        pass

    @property
    @abstractmethod
    def is_forward(self) -> bool:
        """Check if this represents a forward context."""
        pass

    @abstractmethod
    def to_universal_dict(self) -> dict[str, Any]:
        """Convert to platform-agnostic dictionary representation."""
        pass


class BaseMessage(BaseModel, ABC):
    """
    Platform-agnostic message base class.

    All platform-specific message models must inherit from this class
    to provide a consistent interface for message processing.
    """

    model_config = ConfigDict(
        extra="forbid", str_strip_whitespace=True, validate_assignment=True
    )

    # Universal fields
    processed_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="When the message was processed by our system",
    )

    @property
    @abstractmethod
    def platform(self) -> PlatformType:
        """Get the platform this message came from."""
        pass

    @property
    @abstractmethod
    def message_type(self) -> MessageType:
        """Get the universal message type."""
        pass

    @property
    @abstractmethod
    def message_id(self) -> str:
        """Get the unique message identifier."""
        pass

    @property
    @abstractmethod
    def sender_id(self) -> str:
        """Get the sender's universal identifier."""
        pass

    @property
    @abstractmethod
    def timestamp(self) -> int:
        """Get the message timestamp as Unix timestamp."""
        pass

    @property
    @abstractmethod
    def conversation_id(self) -> str:
        """Get the conversation/chat identifier."""
        pass

    @property
    def conversation_type(self) -> ConversationType:
        """Get the type of conversation (private, group, channel)."""
        return ConversationType.PRIVATE  # Default implementation

    @abstractmethod
    def has_context(self) -> bool:
        """Check if this message has context (reply, forward, etc.)."""
        pass

    @abstractmethod
    def get_context(self) -> BaseMessageContext | None:
        """Get message context if available."""
        pass

    @abstractmethod
    def to_universal_dict(self) -> UniversalMessageData:
        """
        Convert to platform-agnostic dictionary representation.

        This method should return a standardized dictionary structure
        that can be used across all platforms for Symphony AI processing.
        """
        pass

    @abstractmethod
    def get_platform_data(self) -> dict[str, Any]:
        """
        Get platform-specific data for advanced processing.

        This returns platform-specific fields that don't have
        universal equivalents but may be needed for specialized logic.
        """
        pass

    def get_message_summary(self) -> dict[str, Any]:
        """
        Get a summary of the message for logging and analytics.

        Returns:
            Dictionary with key message information.
        """
        return {
            "message_id": self.message_id,
            "platform": self.platform.value,
            "message_type": self.message_type.value,
            "sender_id": self.sender_id,
            "conversation_id": self.conversation_id,
            "conversation_type": self.conversation_type.value,
            "timestamp": self.timestamp,
            "processed_at": self.processed_at.isoformat(),
            "has_context": self.has_context(),
        }

    @classmethod
    @abstractmethod
    def from_platform_data(cls, data: dict[str, Any], **kwargs: Any) -> BaseMessage:
        """
        Create message instance from platform-specific data.

        Args:
            data: Raw message data from platform webhook
            **kwargs: Additional platform-specific parameters

        Returns:
            Validated message instance
        """
        pass
