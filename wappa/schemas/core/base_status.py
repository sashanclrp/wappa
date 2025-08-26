"""
Base status abstractions for platform-agnostic status handling.

This module defines the abstract base classes for message status updates
that provide consistent interfaces regardless of the messaging platform.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .types import MessageStatus, PlatformType, UniversalMessageData


class BaseMessageStatus(BaseModel, ABC):
    """
    Platform-agnostic message status base class.

    Represents delivery status updates for sent messages across all platforms.
    """

    model_config = ConfigDict(
        extra="forbid", str_strip_whitespace=True, validate_assignment=True
    )

    # Universal fields
    processed_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When the status update was processed by our system",
    )

    @property
    @abstractmethod
    def platform(self) -> PlatformType:
        """Get the platform this status update came from."""
        pass

    @property
    @abstractmethod
    def message_id(self) -> str:
        """Get the ID of the message this status refers to."""
        pass

    @property
    @abstractmethod
    def status(self) -> MessageStatus:
        """Get the universal message status."""
        pass

    @property
    @abstractmethod
    def recipient_id(self) -> str:
        """Get the recipient's universal identifier."""
        pass

    @property
    @abstractmethod
    def timestamp(self) -> int:
        """Get the status timestamp as Unix timestamp."""
        pass

    @property
    @abstractmethod
    def conversation_id(self) -> str:
        """Get the conversation/chat identifier."""
        pass

    @abstractmethod
    def is_delivered(self) -> bool:
        """Check if the message was delivered."""
        pass

    @abstractmethod
    def is_read(self) -> bool:
        """Check if the message was read."""
        pass

    @abstractmethod
    def is_failed(self) -> bool:
        """Check if the message delivery failed."""
        pass

    @abstractmethod
    def get_error_info(self) -> dict[str, Any] | None:
        """
        Get error information if the message failed.

        Returns:
            Dictionary with error details, or None if no error.
        """
        pass

    @abstractmethod
    def get_delivery_info(self) -> dict[str, Any]:
        """
        Get detailed delivery information.

        Returns:
            Dictionary with platform-specific delivery details.
        """
        pass

    @abstractmethod
    def to_universal_dict(self) -> UniversalMessageData:
        """
        Convert to platform-agnostic dictionary representation.

        Returns:
            Dictionary with standardized status data structure.
        """
        pass

    @abstractmethod
    def get_platform_data(self) -> dict[str, Any]:
        """
        Get platform-specific data for advanced processing.

        Returns:
            Dictionary with platform-specific status fields.
        """
        pass

    def get_status_summary(self) -> dict[str, Any]:
        """
        Get a summary of the status update for logging and analytics.

        Returns:
            Dictionary with key status information.
        """
        return {
            "message_id": self.message_id,
            "platform": self.platform.value,
            "status": self.status.value,
            "recipient_id": self.recipient_id,
            "conversation_id": self.conversation_id,
            "timestamp": self.timestamp,
            "processed_at": self.processed_at.isoformat(),
            "is_delivered": self.is_delivered(),
            "is_read": self.is_read(),
            "is_failed": self.is_failed(),
        }

    @classmethod
    @abstractmethod
    def from_platform_data(cls, data: dict[str, Any], **kwargs) -> "BaseMessageStatus":
        """
        Create status instance from platform-specific data.

        Args:
            data: Raw status data from platform webhook
            **kwargs: Additional platform-specific parameters

        Returns:
            Validated status instance
        """
        pass


class BaseConversationInfo(BaseModel, ABC):
    """
    Platform-agnostic conversation information base class.

    Contains metadata about the conversation where the message was sent.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @property
    @abstractmethod
    def conversation_id(self) -> str:
        """Get the conversation identifier."""
        pass

    @property
    @abstractmethod
    def conversation_type(self) -> str:
        """Get the conversation type (business, personal, etc.)."""
        pass

    @property
    @abstractmethod
    def platform(self) -> PlatformType:
        """Get the platform this conversation belongs to."""
        pass

    @abstractmethod
    def to_universal_dict(self) -> dict[str, Any]:
        """Convert to platform-agnostic dictionary representation."""
        pass


class BasePricingInfo(BaseModel, ABC):
    """
    Platform-agnostic pricing information base class.

    Contains cost information for sent messages where applicable.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @property
    @abstractmethod
    def billable(self) -> bool:
        """Check if this message was billable."""
        pass

    @property
    @abstractmethod
    def pricing_model(self) -> str:
        """Get the pricing model used."""
        pass

    @property
    @abstractmethod
    def platform(self) -> PlatformType:
        """Get the platform this pricing belongs to."""
        pass

    @abstractmethod
    def get_cost_info(self) -> dict[str, Any]:
        """
        Get detailed cost information.

        Returns:
            Dictionary with cost details (amount, currency, etc.).
        """
        pass

    @abstractmethod
    def to_universal_dict(self) -> dict[str, Any]:
        """Convert to platform-agnostic dictionary representation."""
        pass


class BaseStatusWebhook(BaseModel, ABC):
    """
    Platform-agnostic status webhook base class.

    Represents a webhook specifically containing status updates.
    """

    model_config = ConfigDict(
        extra="forbid", str_strip_whitespace=True, validate_assignment=True
    )

    # Universal fields
    received_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When the status webhook was received",
    )

    @property
    @abstractmethod
    def platform(self) -> PlatformType:
        """Get the platform this webhook came from."""
        pass

    @property
    @abstractmethod
    def business_id(self) -> str:
        """Get the business/account identifier."""
        pass

    @property
    @abstractmethod
    def source_id(self) -> str:
        """Get the webhook source identifier."""
        pass

    @abstractmethod
    def get_raw_statuses(self) -> list[dict[str, Any]]:
        """
        Get raw status data for parsing.

        Returns:
            List of raw status dictionaries.
        """
        pass

    @abstractmethod
    def get_status_count(self) -> int:
        """Get the number of status updates in this webhook."""
        pass

    @abstractmethod
    def to_universal_dict(self) -> dict[str, Any]:
        """Convert to platform-agnostic dictionary representation."""
        pass

    def get_webhook_summary(self) -> dict[str, Any]:
        """
        Get a summary of the status webhook for logging.

        Returns:
            Dictionary with key webhook information.
        """
        return {
            "platform": self.platform.value,
            "business_id": self.business_id,
            "source_id": self.source_id,
            "received_at": self.received_at.isoformat(),
            "status_count": self.get_status_count(),
        }

    @classmethod
    @abstractmethod
    def from_platform_payload(
        cls, payload: dict[str, Any], **kwargs
    ) -> "BaseStatusWebhook":
        """
        Create status webhook instance from platform-specific payload.

        Args:
            payload: Raw webhook payload from the platform
            **kwargs: Additional platform-specific parameters

        Returns:
            Validated status webhook instance
        """
        pass
