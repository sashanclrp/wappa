"""
Base processor abstraction for platform-agnostic webhook processing.

This module defines the abstract base classes that all platform-specific
webhook processors must inherit from to ensure consistent interfaces.
"""

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

from wappa.core.logging.logger import get_logger
from wappa.schemas.core.base_message import BaseMessage
from wappa.schemas.core.base_status import BaseMessageStatus
from wappa.schemas.core.base_webhook import BaseWebhook
from wappa.schemas.core.types import ErrorCode, MessageType, PlatformType

# Legacy ProcessingResult class removed - Universal Webhook Interface is now the ONLY way
# Use processor.create_universal_webhook() method instead for type-safe webhook handling


class ProcessorCapabilities:
    """
    Represents the capabilities of a platform processor.

    This allows the system to understand what each processor can handle
    and route webhooks appropriately.
    """

    def __init__(
        self,
        platform: PlatformType,
        supported_message_types: set[MessageType],
        supports_status_updates: bool = True,
        supports_signature_validation: bool = True,
        supports_error_webhooks: bool = True,
        max_payload_size: int | None = None,
        rate_limit_per_minute: int | None = None,
    ):
        self.platform = platform
        self.supported_message_types = supported_message_types
        self.supports_status_updates = supports_status_updates
        self.supports_signature_validation = supports_signature_validation
        self.supports_error_webhooks = supports_error_webhooks
        self.max_payload_size = max_payload_size
        self.rate_limit_per_minute = rate_limit_per_minute

    def can_handle_message_type(self, message_type: MessageType) -> bool:
        """Check if processor can handle a specific message type."""
        return message_type in self.supported_message_types

    def to_dict(self) -> dict[str, Any]:
        """Convert capabilities to dictionary."""
        return {
            "platform": self.platform.value,
            "supported_message_types": [
                mt.value for mt in self.supported_message_types
            ],
            "supports_status_updates": self.supports_status_updates,
            "supports_signature_validation": self.supports_signature_validation,
            "supports_error_webhooks": self.supports_error_webhooks,
            "max_payload_size": self.max_payload_size,
            "rate_limit_per_minute": self.rate_limit_per_minute,
        }


class BaseWebhookProcessor(ABC):
    """
    Platform-agnostic webhook processor base class.

    All platform-specific processors must inherit from this class
    to provide a consistent interface for webhook processing.
    """

    def __init__(self):
        self.logger = get_logger(__name__)

        # Message type handlers - subclasses should populate this
        self._message_type_handlers: dict[str, callable] = {}

        # Processing statistics
        self._processed_count = 0
        self._error_count = 0
        self._last_processed = None

    @property
    @abstractmethod
    def platform(self) -> PlatformType:
        """Get the platform this processor handles."""
        pass

    @property
    @abstractmethod
    def capabilities(self) -> ProcessorCapabilities:
        """Get the capabilities of this processor."""
        pass

    # Legacy process_webhook abstract method removed - Universal Webhook Interface is the ONLY way
    # All processors must implement create_universal_webhook() method instead

    @abstractmethod
    def validate_webhook_signature(
        self, payload: bytes, signature: str, **kwargs
    ) -> bool:
        """
        Validate webhook signature for security.

        Args:
            payload: Raw webhook payload bytes
            signature: Platform-specific signature header
            **kwargs: Additional validation parameters

        Returns:
            True if signature is valid, False otherwise
        """
        pass

    @abstractmethod
    def parse_webhook_container(self, payload: dict[str, Any], **kwargs) -> BaseWebhook:
        """
        Parse the top-level webhook structure.

        Args:
            payload: Raw webhook payload
            **kwargs: Additional parsing parameters

        Returns:
            Parsed webhook container with universal interface

        Raises:
            ValidationError: If webhook structure is invalid
        """
        pass

    @abstractmethod
    def get_supported_message_types(self) -> set[MessageType]:
        """Get the set of message types this processor supports."""
        pass

    @abstractmethod
    def create_message_from_data(
        self, message_data: dict[str, Any], message_type: MessageType, **kwargs
    ) -> BaseMessage:
        """
        Create a message instance from raw data.

        Args:
            message_data: Raw message data from webhook
            message_type: The type of message to create
            **kwargs: Additional creation parameters

        Returns:
            Parsed message with universal interface

        Raises:
            ValidationError: If message data is invalid
            UnsupportedMessageType: If message type is not supported
        """
        pass

    @abstractmethod
    def create_status_from_data(
        self, status_data: dict[str, Any], **kwargs
    ) -> BaseMessageStatus:
        """
        Create a status instance from raw data.

        Args:
            status_data: Raw status data from webhook
            **kwargs: Additional creation parameters

        Returns:
            Parsed status with universal interface

        Raises:
            ValidationError: If status data is invalid
        """
        pass

    def is_supported_platform(self, platform: str) -> bool:
        """Check if the platform string matches this processor."""
        return platform.lower() == self.platform.value.lower()

    def register_message_handler(self, message_type: str, handler: Callable) -> None:
        """Register a handler for a specific message type."""
        self._message_type_handlers[message_type] = handler

    def get_message_handler(self, message_type: str) -> Callable | None:
        """Get the handler for a specific message type."""
        return self._message_type_handlers.get(message_type)

    # Legacy _process_incoming_messages method removed - Universal Webhook Interface handles this via IncomingMessageWebhook

    # Legacy _process_status_updates method removed - Universal Webhook Interface handles this via StatusWebhook

    def get_processing_stats(self) -> dict[str, Any]:
        """
        Get processing statistics for monitoring and analysis.

        Returns:
            Dictionary with processing statistics
        """
        return {
            "platform": self.platform.value,
            "capabilities": self.capabilities.to_dict(),
            "processed_count": self._processed_count,
            "error_count": self._error_count,
            "error_rate": self._error_count / max(self._processed_count, 1),
            "last_processed": self._last_processed.isoformat()
            if self._last_processed
            else None,
            "supported_message_types": [
                mt.value for mt in self.get_supported_message_types()
            ],
        }

    # Legacy create_error_result method removed - Universal Webhook Interface handles errors via ErrorWebhook

    def __str__(self) -> str:
        """String representation of the processor."""
        return f"{self.__class__.__name__}(platform={self.platform.value})"

    def __repr__(self) -> str:
        """Detailed string representation of the processor."""
        return (
            f"{self.__class__.__name__}("
            f"platform={self.platform.value}, "
            f"processed={self._processed_count}, "
            f"errors={self._error_count})"
        )


class ProcessorError(Exception):
    """Base exception for processor-related errors."""

    def __init__(self, message: str, error_code: ErrorCode, platform: PlatformType):
        self.message = message
        self.error_code = error_code
        self.platform = platform
        super().__init__(message)


class UnsupportedMessageTypeError(ProcessorError):
    """Raised when a processor encounters an unsupported message type."""

    def __init__(self, message_type: str, platform: PlatformType):
        super().__init__(
            f"Message type '{message_type}' not supported by {platform.value} processor",
            ErrorCode.UNKNOWN_MESSAGE_TYPE,
            platform,
        )


class SignatureValidationError(ProcessorError):
    """Raised when webhook signature validation fails."""

    def __init__(self, platform: PlatformType):
        super().__init__(
            f"Webhook signature validation failed for {platform.value}",
            ErrorCode.SIGNATURE_VALIDATION_FAILED,
            platform,
        )
