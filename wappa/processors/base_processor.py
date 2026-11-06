"""
Base processor abstraction for platform-agnostic webhook processing.

This module defines the abstract base classes that all platform-specific
webhook processors must inherit from to ensure consistent interfaces.
"""

from abc import ABC, abstractmethod
from collections.abc import Callable
from datetime import datetime
from typing import Any

from wappa.core.logging.logger import get_logger
from wappa.schemas.core.types import ErrorCode, MessageType, PlatformType
from wappa.webhooks.core.base_message import BaseMessage
from wappa.webhooks.core.base_status import BaseMessageStatus
from wappa.webhooks.core.base_webhook import BaseWebhook
from wappa.webhooks.core.webhook_interfaces.universal_webhooks import UniversalWebhook


class BaseWebhookProcessor(ABC):
    """
    Platform-agnostic webhook processor base class.

    All platform-specific processors must inherit from this class
    to provide a consistent interface for webhook processing.
    """

    def __init__(self) -> None:
        self.logger = get_logger(__name__)

        # Message type handlers - subclasses should populate this
        self._message_type_handlers: dict[str, Callable[..., BaseMessage]] = {}

        # Processing statistics
        self._processed_count = 0
        self._error_count = 0
        self._last_processed: datetime | None = None

    @property
    @abstractmethod
    def platform(self) -> PlatformType:
        """Get the platform this processor handles."""
        pass

    @abstractmethod
    async def create_universal_webhook(
        self, payload: dict[str, Any], **kwargs: Any
    ) -> UniversalWebhook:
        """Convert a provider payload to Wappa's universal webhook contract."""
        pass

    @abstractmethod
    def parse_webhook_container(
        self, payload: dict[str, Any], **kwargs: Any
    ) -> BaseWebhook:
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
        self,
        message_data: dict[str, Any],
        message_type: MessageType,
        **kwargs: Any,
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
        self, status_data: dict[str, Any], **kwargs: Any
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

    def register_message_handler(
        self, message_type: str, handler: Callable[..., BaseMessage]
    ) -> None:
        """Register a handler for a specific message type."""
        self._message_type_handlers[message_type] = handler

    def get_message_handler(self, message_type: str) -> Callable | None:
        """Get the handler for a specific message type."""
        return self._message_type_handlers.get(message_type)

    def get_processing_stats(self) -> dict[str, Any]:
        """
        Get processing statistics for monitoring and analysis.

        Returns:
            Dictionary with processing statistics
        """
        return {
            "platform": self.platform.value,
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
