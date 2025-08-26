"""
Base webhook abstraction for platform-agnostic webhook handling.

This module defines the abstract base classes that all platform-specific
webhook implementations must inherit from to ensure consistent interfaces.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .types import PlatformType, WebhookType


class BaseContact(BaseModel, ABC):
    """
    Platform-agnostic contact information base class.

    All platform-specific contact models must inherit from this class
    to provide a consistent interface for contact data.
    """

    model_config = ConfigDict(
        extra="forbid", str_strip_whitespace=True, validate_assignment=True
    )

    @property
    @abstractmethod
    def user_id(self) -> str:
        """Get the universal user identifier."""
        pass

    @property
    @abstractmethod
    def display_name(self) -> str | None:
        """Get the user's display name if available."""
        pass

    @property
    @abstractmethod
    def platform(self) -> PlatformType:
        """Get the platform this contact belongs to."""
        pass

    @abstractmethod
    def to_universal_dict(self) -> dict[str, Any]:
        """Convert to platform-agnostic dictionary representation."""
        pass


class BaseWebhookMetadata(BaseModel, ABC):
    """
    Platform-agnostic webhook metadata base class.

    Contains platform-specific metadata about the webhook source.
    """

    model_config = ConfigDict(
        extra="forbid", str_strip_whitespace=True, validate_assignment=True
    )

    @property
    @abstractmethod
    def business_id(self) -> str:
        """Get the business/bot identifier."""
        pass

    @property
    @abstractmethod
    def webhook_source_id(self) -> str:
        """Get the webhook source identifier (phone number, bot token, etc.)."""
        pass

    @property
    @abstractmethod
    def platform(self) -> PlatformType:
        """Get the platform type."""
        pass

    @abstractmethod
    def to_universal_dict(self) -> dict[str, Any]:
        """Convert to platform-agnostic dictionary representation."""
        pass


class BaseWebhook(BaseModel, ABC):
    """
    Platform-agnostic webhook base class.

    All platform-specific webhook models must inherit from this class
    to provide a consistent interface for webhook processing.
    """

    model_config = ConfigDict(
        extra="forbid", str_strip_whitespace=True, validate_assignment=True
    )

    # Universal fields that all webhooks should have
    received_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When the webhook was received by our system",
    )

    @property
    @abstractmethod
    def platform(self) -> PlatformType:
        """Get the platform type this webhook came from."""
        pass

    @property
    @abstractmethod
    def webhook_type(self) -> WebhookType:
        """Get the type of webhook (messages, status updates, errors, etc.)."""
        pass

    @property
    @abstractmethod
    def business_id(self) -> str:
        """Get the business/account identifier."""
        pass

    @property
    @abstractmethod
    def source_id(self) -> str:
        """Get the webhook source identifier (phone number ID, bot token, etc.)."""
        pass

    @abstractmethod
    def is_incoming_message(self) -> bool:
        """Check if this webhook contains incoming messages."""
        pass

    @abstractmethod
    def is_status_update(self) -> bool:
        """Check if this webhook contains message status updates."""
        pass

    @abstractmethod
    def has_errors(self) -> bool:
        """Check if this webhook contains error information."""
        pass

    @abstractmethod
    def get_raw_messages(self) -> list[dict[str, Any]]:
        """
        Get raw message data for parsing with platform-specific schemas.

        Returns:
            List of raw message dictionaries ready for platform-specific parsing.
        """
        pass

    @abstractmethod
    def get_raw_statuses(self) -> list[dict[str, Any]]:
        """
        Get raw status data for parsing with platform-specific schemas.

        Returns:
            List of raw status dictionaries ready for platform-specific parsing.
        """
        pass

    @abstractmethod
    def get_contacts(self) -> list[BaseContact]:
        """
        Get contact information from the webhook.

        Returns:
            List of contact objects with universal interface.
        """
        pass

    @abstractmethod
    def get_metadata(self) -> BaseWebhookMetadata:
        """
        Get webhook metadata with universal interface.

        Returns:
            Metadata object with platform-agnostic interface.
        """
        pass

    @abstractmethod
    def to_universal_dict(self) -> dict[str, Any]:
        """
        Convert webhook to platform-agnostic dictionary representation.

        This method should return a dictionary with standardized keys
        that can be used across all platforms for logging, analytics, etc.

        Returns:
            Dictionary with universal webhook data structure.
        """
        pass

    @abstractmethod
    def get_processing_context(self) -> dict[str, Any]:
        """
        Get context information needed for message processing.

        This includes tenant information, routing data, and other
        metadata required for Symphony AI integration.

        Returns:
            Dictionary with processing context data.
        """
        pass

    def get_webhook_id(self) -> str:
        """
        Generate a unique identifier for this webhook.

        This can be used for deduplication, logging, and tracking.
        """
        import hashlib
        import json

        # Create deterministic ID based on platform, business_id, and timestamp
        data = {
            "platform": self.platform.value,
            "business_id": self.business_id,
            "source_id": self.source_id,
            "received_at": self.received_at.isoformat(),
            "webhook_type": self.webhook_type.value,
        }

        content = json.dumps(data, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def get_summary(self) -> dict[str, Any]:
        """
        Get a summary of the webhook for logging and monitoring.

        Returns:
            Dictionary with key webhook information for structured logging.
        """
        return {
            "webhook_id": self.get_webhook_id(),
            "platform": self.platform.value,
            "webhook_type": self.webhook_type.value,
            "business_id": self.business_id,
            "source_id": self.source_id,
            "received_at": self.received_at.isoformat(),
            "has_messages": self.is_incoming_message(),
            "has_statuses": self.is_status_update(),
            "has_errors": self.has_errors(),
            "message_count": len(self.get_raw_messages()),
            "status_count": len(self.get_raw_statuses()),
            "contact_count": len(self.get_contacts()),
        }

    @classmethod
    @abstractmethod
    def from_platform_payload(cls, payload: dict[str, Any], **kwargs) -> "BaseWebhook":
        """
        Create webhook instance from platform-specific payload.

        This factory method should handle platform-specific validation
        and transformation of the raw webhook payload.

        Args:
            payload: Raw webhook payload from the platform
            **kwargs: Additional platform-specific parameters

        Returns:
            Validated webhook instance

        Raises:
            ValidationError: If payload is invalid
            PlatformError: If platform-specific validation fails
        """
        pass


class BaseWebhookError(BaseModel, ABC):
    """
    Platform-agnostic webhook error base class.

    Represents errors that occur during webhook processing.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @property
    @abstractmethod
    def error_code(self) -> str:
        """Get the platform-specific error code."""
        pass

    @property
    @abstractmethod
    def error_message(self) -> str:
        """Get the human-readable error message."""
        pass

    @property
    @abstractmethod
    def platform(self) -> PlatformType:
        """Get the platform this error originated from."""
        pass

    @abstractmethod
    def is_retryable(self) -> bool:
        """Check if this error condition is retryable."""
        pass

    @abstractmethod
    def to_universal_dict(self) -> dict[str, Any]:
        """Convert to platform-agnostic dictionary representation."""
        pass
