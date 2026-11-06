"""Universal error webhook: system, app and account-level errors."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from wappa.schemas.core.types import PlatformType
from wappa.webhooks.core.webhook_interfaces.base_components import (
    ErrorDetailBase,
    InboxBase,
)


class ErrorWebhook(BaseModel):
    """
    Universal interface for system, app, and account-level errors.

    This interface represents errors that occur at the platform level,
    not related to specific message delivery (those are in StatusWebhook).

    All platforms must transform their error webhooks to this format.
    """

    model_config = ConfigDict(
        extra="forbid", str_strip_whitespace=True, validate_assignment=True
    )

    # Core identification
    inbox: InboxBase = Field(description="Business inbox identification")

    # Error information
    errors: list[ErrorDetailBase] = Field(description="Detailed error information")
    timestamp: datetime = Field(description="When these errors occurred")

    # Error context
    error_level: str = Field(
        default="system", description="Level of error (system, app, account, webhook)"
    )

    # Universal metadata
    platform: PlatformType = Field(description="Source messaging platform")
    webhook_id: str = Field(description="Unique identifier for this webhook event")

    # Raw webhook data (for debugging and inspection)
    raw_webhook_data: dict | None = Field(
        default=None,
        description="Original raw webhook JSON payload",
        exclude=True,  # Don't include in serialization by default
    )

    def get_primary_error(self) -> ErrorDetailBase:
        """Get the primary (first) error."""
        return self.errors[0]

    def get_error_count(self) -> int:
        """Get total number of errors in this webhook."""
        return len(self.errors)

    def has_critical_errors(self) -> bool:
        """Check if any errors are likely critical (5xx codes)."""
        return any(500 <= error.error_code < 600 for error in self.errors)

    def has_retryable_errors(self) -> bool:
        """Check if any errors are potentially retryable."""
        return any(error.is_temporary_error() for error in self.errors)

    def get_error_codes(self) -> list[int]:
        """Get list of all error codes in this webhook."""
        return [error.error_code for error in self.errors]

    def get_summary(self) -> dict[str, Any]:
        """
        Get a summary of this webhook for logging and monitoring.

        Returns:
            Dictionary with key information about this webhook
        """
        return {
            "webhook_type": "error",
            "platform": self.platform.value,
            "error_level": self.error_level,
            "error_count": self.get_error_count(),
            "error_codes": self.get_error_codes(),
            "inbox": self.inbox.get_inbox_key(),
            "has_critical_errors": self.has_critical_errors(),
            "has_retryable_errors": self.has_retryable_errors(),
            "timestamp": self.timestamp.isoformat(),
        }

    def get_raw_webhook_data(self) -> dict | None:
        """
        Get the original raw webhook JSON payload.

        This is useful for debugging, logging, or accessing platform-specific
        fields that aren't included in the universal interface.

        Returns:
            Original webhook JSON dict or None if not available
        """
        return self.raw_webhook_data

    def set_raw_webhook_data(self, raw_data: dict) -> None:
        """
        Set the original raw webhook JSON payload.

        This should be called by webhook processors when creating
        UniversalWebhook instances.

        Args:
            raw_data: Original webhook JSON payload
        """
        self.raw_webhook_data = raw_data
