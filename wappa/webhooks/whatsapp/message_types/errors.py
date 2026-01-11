"""
WhatsApp webhook error schema.

This module contains Pydantic models for processing WhatsApp webhook-level errors,
which occur when the system cannot process requests due to system, app, or account issues.

Note: These are webhook-level errors, not message-level errors. They appear in the
webhook value's "errors" field rather than within individual messages.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from wappa.webhooks.whatsapp.base_models import MessageError


class WhatsAppWebhookError(BaseModel):
    """
    WhatsApp webhook error model.

    Represents system-level errors that prevent webhook processing, such as:
    - System-level problems (server issues, maintenance)
    - App-level problems (configuration issues, permissions)
    - Account-level problems (rate limits, quota exceeded)

    Note: These errors appear at the webhook value level, not within individual messages.
    They indicate problems with the webhook processing itself.
    """

    model_config = ConfigDict(
        extra="forbid", str_strip_whitespace=True, validate_assignment=True
    )

    # Error information (uses the same structure as message errors)
    errors: list[MessageError] = Field(..., description="List of webhook-level errors")

    @field_validator("errors")
    @classmethod
    def validate_errors(cls, v: list[MessageError]) -> list[MessageError]:
        """Validate errors list is not empty."""
        if not v or len(v) == 0:
            raise ValueError("Webhook errors must include error information")
        return v

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
    def error_titles(self) -> list[str]:
        """Get list of all error titles."""
        return [error.title for error in self.errors]

    def has_error_code(self, code: int) -> bool:
        """Check if a specific error code is present."""
        return code in self.error_codes

    def get_error_by_code(self, code: int) -> MessageError | None:
        """Get the first error with the specified code."""
        for error in self.errors:
            if error.code == code:
                return error
        return None

    def is_rate_limit_error(self) -> bool:
        """Check if this is a rate limit error (code 130429)."""
        return self.has_error_code(130429)

    def is_bsuid_auth_error(self) -> bool:
        """Check if this is a BSUID authentication message error (code 131062).

        Error 131062 occurs when attempting to send authentication messages
        to a user's BSUID instead of their phone number. Authentication messages
        must be sent to phone numbers only.
        """
        return self.has_error_code(131062)

    def is_system_error(self) -> bool:
        """
        Check if this is a system-level error.

        System errors typically have codes in certain ranges.
        This is a heuristic and may need adjustment based on documentation.
        """
        # System errors often start with 1, API errors with other digits
        return any(100000 <= code <= 199999 for code in self.error_codes)

    def is_app_error(self) -> bool:
        """
        Check if this is an app-level error.

        App errors typically relate to configuration or permissions.
        """
        # App/permission errors often in different ranges
        return any(200000 <= code <= 299999 for code in self.error_codes)

    def is_account_error(self) -> bool:
        """
        Check if this is an account-level error.

        Account errors typically relate to quotas, limits, or account status.
        """
        # Account errors often in different ranges
        return any(300000 <= code <= 399999 for code in self.error_codes)

    def get_error_severity(self) -> str:
        """
        Estimate error severity based on error codes and types.

        Returns:
            'critical', 'high', 'medium', or 'low'
        """
        # Rate limits are typically high severity
        if self.is_rate_limit_error():
            return "high"

        # System errors are often critical
        if self.is_system_error():
            return "critical"

        # App/account errors vary
        if self.is_app_error() or self.is_account_error():
            return "medium"

        # Default for unknown error types
        return "low"

    def get_primary_error_details(self) -> str:
        """Get detailed information about the primary error."""
        error = self.primary_error
        return error.error_data.details

    def get_documentation_url(self) -> str:
        """Get the URL to error documentation."""
        return self.primary_error.href

    def to_summary_dict(self) -> dict[str, str | bool | int | list]:
        """
        Create a summary dictionary for logging and analysis.

        Returns:
            Dictionary with key error information for structured logging.
        """
        return {
            "error_count": self.error_count,
            "error_codes": self.error_codes,
            "error_messages": self.error_messages,
            "error_titles": self.error_titles,
            "primary_error_code": self.primary_error.code,
            "primary_error_message": self.primary_error.message,
            "primary_error_title": self.primary_error.title,
            "primary_error_details": self.get_primary_error_details(),
            "documentation_url": self.get_documentation_url(),
            "is_rate_limit_error": self.is_rate_limit_error(),
            "is_bsuid_auth_error": self.is_bsuid_auth_error(),
            "is_system_error": self.is_system_error(),
            "is_app_error": self.is_app_error(),
            "is_account_error": self.is_account_error(),
            "error_severity": self.get_error_severity(),
        }


# Helper function to create webhook error from raw data
def create_webhook_error_from_raw(
    raw_errors: list[dict[str, Any]],
) -> WhatsAppWebhookError:
    """
    Create a WhatsAppWebhookError from raw webhook error data.

    Args:
        raw_errors: List of raw error dictionaries from webhook payload

    Returns:
        WhatsAppWebhookError instance
    """
    # Convert raw errors to MessageError instances
    message_errors = [MessageError(**error_data) for error_data in raw_errors]

    return WhatsAppWebhookError(errors=message_errors)
