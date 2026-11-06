"""Universal error detail component."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ErrorDetailBase(BaseModel):
    """
    Universal error detail component.

    Represents structured error information from messaging platforms.
    Based on WhatsApp's error structure but designed to be universal.
    """

    model_config = ConfigDict(
        extra="forbid", str_strip_whitespace=True, validate_assignment=True
    )

    # Core error identification
    error_code: int = Field(description="Numeric error code")
    error_title: str = Field(description="Human-readable error title")
    error_message: str = Field(description="Detailed error message")

    # Additional error context
    error_details: str | None = Field(
        default=None, description="Extended error details"
    )
    documentation_url: str | None = Field(
        default=None, description="URL to error code documentation"
    )

    # Error categorization
    error_type: str | None = Field(
        default=None, description="Type of error (system, validation, rate_limit, etc.)"
    )
    is_retryable: bool | None = Field(
        default=None, description="Whether this error condition can be retried"
    )

    # Timestamp
    occurred_at: datetime | None = Field(
        default=None, description="When this error occurred"
    )

    def is_temporary_error(self) -> bool:
        """Check if this is likely a temporary error that could be retried."""
        temporary_codes = [429, 500, 502, 503, 504]  # Rate limits and server errors
        return self.error_code in temporary_codes or self.is_retryable is True

    def get_error_summary(self) -> str:
        """Get a concise error summary for logging."""
        return f"Error {self.error_code}: {self.error_title}"
