"""
WhatsApp message status schema.

This module contains Pydantic models for processing WhatsApp message status
updates including delivery receipts, read receipts, and failure notifications.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from wappa.webhooks.core.base_status import BaseMessageStatus
from wappa.webhooks.core.types import MessageStatus
from wappa.webhooks.whatsapp.base_models import Conversation, MessageError, Pricing


class WhatsAppMessageStatus(BaseMessageStatus):
    """
    WhatsApp message status model.

    Represents status updates for messages sent by the business to WhatsApp users.
    Status updates include sent, delivered, read, or failed notifications.

    BSUID Support (v24.0+):
    - recipient_bsuid: Business Scoped User ID (stable identifier)
    - wa_recipient_id: Phone number (may be empty for username-only users)
    - Use recipient_id property for the recommended identifier
    """

    model_config = ConfigDict(
        extra="forbid", str_strip_whitespace=True, validate_assignment=True
    )

    # Core status fields
    id: str = Field(..., description="WhatsApp message ID that this status refers to")
    wa_status: Literal["sent", "delivered", "read", "failed"] = Field(
        ..., alias="status", description="Message delivery status"
    )
    wa_timestamp: str = Field(
        ...,
        alias="timestamp",
        description="Unix timestamp when the status event occurred",
    )
    wa_recipient_id: str = Field(
        default="",
        alias="recipient_id",
        description="WhatsApp user phone number (may be empty for username-only users)",
    )
    # BSUID support (v24.0+)
    recipient_bsuid: str | None = Field(
        None,
        alias="recipient_user_id",
        description="Business Scoped User ID (BSUID) - stable recipient identifier from webhook",
    )

    # Optional fields
    recipient_identity_key_hash: str | None = Field(
        None, description="Identity key hash (only if identity change check enabled)"
    )
    biz_opaque_callback_data: str | None = Field(
        None, description="Business opaque data (only if set when sending message)"
    )

    # Pricing and conversation info (present for sent and first delivered/read)
    conversation: Conversation | None = Field(
        None,
        description="Conversation information (omitted in v24.0+ unless free entry point)",
    )
    pricing: Pricing | None = Field(
        None,
        description="Pricing information (present with sent and first delivered/read)",
    )

    # Error information (only for failed status)
    errors: list[MessageError] | None = Field(
        None, description="Error details (only present if status='failed')"
    )

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

    @field_validator("wa_timestamp")
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
    def has_recipient_bsuid(self) -> bool:
        """Check if this status has a recipient BSUID set."""
        return bool(self.recipient_bsuid and self.recipient_bsuid.strip())

    @property
    def has_recipient_phone(self) -> bool:
        """Check if this status has a recipient phone number set."""
        return bool(self.wa_recipient_id and self.wa_recipient_id.strip())

    @model_validator(mode="after")
    def validate_status_consistency(self):
        """Validate status-specific field consistency."""
        # Failed status must have errors, others should not
        if self.wa_status == "failed":
            if not self.errors or len(self.errors) == 0:
                raise ValueError("Failed status must include error information")
        else:
            if self.errors and len(self.errors) > 0:
                raise ValueError(
                    f"Status '{self.wa_status}' should not have error information"
                )

        # Pricing information is typically present for sent and first delivered/read
        # but we won't enforce this as it can vary based on WhatsApp API version

        return self

    # Abstract property implementations
    @property
    def status(self) -> MessageStatus:
        """Get the universal message status."""
        return MessageStatus(self.wa_status)

    @property
    def timestamp(self) -> int:
        """Get the status timestamp as Unix timestamp."""
        return int(self.wa_timestamp)

    @property
    def recipient_id(self) -> str:
        """
        Get the recommended recipient identifier for caching, storage, and messaging.

        Returns:
            BSUID if available, otherwise phone number (wa_recipient_id).
        """
        if self.recipient_bsuid and self.recipient_bsuid.strip():
            return self.recipient_bsuid.strip()
        return self.wa_recipient_id

    @property
    def is_sent(self) -> bool:
        """Check if message was sent."""
        return self.wa_status == "sent"

    @property
    def is_delivered(self) -> bool:
        """Check if message was delivered."""
        return self.wa_status == "delivered"

    @property
    def is_read(self) -> bool:
        """Check if message was read."""
        return self.wa_status == "read"

    @property
    def is_failed(self) -> bool:
        """Check if message failed."""
        return self.wa_status == "failed"

    @property
    def is_successful(self) -> bool:
        """Check if message was successfully processed (sent, delivered, or read)."""
        return self.wa_status in ["sent", "delivered", "read"]

    @property
    def unix_timestamp(self) -> int:
        """Get the timestamp as an integer."""
        return int(self.wa_timestamp)

    def get_error_info(self) -> dict[str, Any] | None:
        """Get error information if the message failed."""
        if not self.is_failed or not self.errors:
            return None

        # Return the first error (WhatsApp typically sends one error per status)
        error = self.errors[0] if self.errors else None
        if not error:
            return None

        return {
            "code": error.code,
            "title": error.title,
            "message": error.message,
            "details": error.error_data.details if error.error_data else None,
            "href": error.href,
        }

    def get_delivery_info(self) -> dict[str, Any]:
        """Get detailed delivery information."""
        info: dict[str, Any] = {
            "status": self.wa_status,
            "timestamp": self.timestamp,
            "recipient_id": self.recipient_id,
            "recipient_phone": self.wa_recipient_id
            if self.has_recipient_phone
            else None,
            "recipient_bsuid": self.recipient_bsuid,
            "message_id": self.id,
        }

        # Add conversation info if present
        if self.conversation:
            info["conversation"] = {
                "id": self.conversation.id,
                "type": self.conversation.origin.type,
                "expiration_timestamp": self.conversation.expiration_timestamp,
            }

        # Add pricing info if present
        if self.pricing:
            info["pricing"] = {
                "billable": self.pricing.billable,
                "pricing_model": self.pricing.pricing_model,
                "category": self.pricing.category,
                "type": self.pricing.type,
            }

        return info

    def to_universal_dict(self) -> dict[str, Any]:
        """Convert to platform-agnostic dictionary representation."""
        return {
            "platform": "whatsapp",
            "message_id": self.id,
            "status": self.wa_status,
            "timestamp": self.timestamp,
            "recipient_id": self.recipient_id,
            "recipient_bsuid": self.recipient_bsuid,
            "recipient_phone": self.wa_recipient_id
            if self.has_recipient_phone
            else None,
            "is_successful": self.is_successful,
            "error_info": self.get_error_info(),
            "delivery_info": self.get_delivery_info(),
        }

    def get_platform_data(self) -> dict[str, Any]:
        """Get platform-specific data for advanced processing."""
        return {
            "whatsapp_message_id": self.id,
            "wa_recipient_id": self.wa_recipient_id,
            "recipient_bsuid": self.recipient_bsuid,
            "recipient_id": self.recipient_id,
            "recipient_identity_key_hash": self.recipient_identity_key_hash,
            "biz_opaque_callback_data": self.biz_opaque_callback_data,
            "conversation": self.conversation.model_dump()
            if self.conversation
            else None,
            "pricing": self.pricing.model_dump() if self.pricing else None,
            "errors": [error.model_dump() for error in self.errors]
            if self.errors
            else None,
        }

    def get_status_summary(self) -> dict[str, Any]:
        """Get a summary of the status update for logging and analytics."""
        summary: dict[str, Any] = {
            "message_id": self.id,
            "status": self.wa_status,
            "recipient": self.recipient_id,
            "recipient_bsuid": self.recipient_bsuid,
            "recipient_phone": self.wa_recipient_id
            if self.has_recipient_phone
            else None,
            "timestamp": self.timestamp,
        }

        # Add conversation type if available (useful for template/utility messages)
        if self.conversation and self.conversation.origin:
            summary["conversation_type"] = self.conversation.origin.type

        # Add pricing category if available
        if self.pricing:
            summary["pricing_category"] = self.pricing.category
            summary["billable"] = self.pricing.billable

        # Add error summary if failed
        if self.is_failed and self.errors:
            error = self.errors[0]
            summary["error_code"] = error.code
            summary["error_title"] = error.title

        return summary

    @property
    def conversation_id(self) -> str | None:
        """Get conversation ID from status data."""
        return self.conversation.id if self.conversation else None

    @property
    def message_id(self) -> str:
        """Get the message ID this status refers to."""
        return self.id

    @property
    def platform(self) -> str:
        """Get the platform name."""
        return "whatsapp"

    @classmethod
    def from_platform_data(
        cls, data: dict[str, Any], **kwargs
    ) -> "WhatsAppMessageStatus":
        """Create instance from platform-specific data."""
        return cls.model_validate(data)

    @property
    def has_billing_info(self) -> bool:
        """Check if this status includes billing/pricing information."""
        return self.pricing is not None

    @property
    def is_billable(self) -> bool:
        """Check if this message is billable (if pricing info available)."""
        if self.pricing:
            return self.pricing.billable
        return False

    def get_conversation_info(self) -> tuple[str | None, str | None]:
        """
        Get conversation information.

        Returns:
            Tuple of (conversation_id, conversation_category) if available,
            (None, None) otherwise.
        """
        if self.conversation:
            return (self.conversation.id, self.conversation.origin.type)
        return (None, None)

    def get_pricing_info(self) -> tuple[bool | None, str | None, str | None]:
        """
        Get pricing information.

        Returns:
            Tuple of (is_billable, pricing_model, pricing_category) if available,
            (None, None, None) otherwise.
        """
        if self.pricing:
            return (
                self.pricing.billable,
                self.pricing.pricing_model,
                self.pricing.category,
            )
        return (None, None, None)

    def get_all_errors(self) -> list[dict[str, str | int]]:
        """
        Get all error information for failed messages.

        Returns:
            List of error dictionaries with code, title, message, and details.
            Empty list if no errors.
        """
        if not self.errors:
            return []

        return [
            {
                "code": error.code,
                "title": error.title,
                "message": error.message,
                "details": error.error_data.details,
                "docs_url": error.href,
            }
            for error in self.errors
        ]

    def get_primary_error(self) -> dict[str, str | int] | None:
        """
        Get the primary (first) error for failed messages.

        Returns:
            Error dictionary or None if no errors.
        """
        errors = self.get_error_info()
        return errors[0] if errors else None

    def to_summary_dict(self) -> dict[str, str | bool | int | None]:
        """
        Create a summary dictionary for logging and analysis.

        Returns:
            Dictionary with key status information for structured logging.
        """
        summary: dict[str, str | bool | int | None] = {
            "message_id": self.id,
            "status": self.status.value,
            "timestamp": self.unix_timestamp,
            "recipient_id": self.recipient_id,
            "recipient_bsuid": self.recipient_bsuid,
            "has_recipient_bsuid": self.has_recipient_bsuid,
            "is_successful": self.is_successful,
            "is_billable": self.is_billable,
            "has_callback_data": self.biz_opaque_callback_data is not None,
            "has_identity_check": self.recipient_identity_key_hash is not None,
        }

        # Add conversation info if available
        conv_id, conv_category = self.get_conversation_info()
        if conv_id:
            summary["conversation_id"] = conv_id
            summary["conversation_category"] = conv_category

        # Add pricing info if available
        is_billable, pricing_model, pricing_category = self.get_pricing_info()
        if pricing_model:
            summary["pricing_model"] = pricing_model
            summary["pricing_category"] = pricing_category

        # Add error info for failed messages
        if self.is_failed:
            primary_error = self.get_primary_error()
            if primary_error:
                summary["error_code"] = primary_error["code"]
                summary["error_title"] = primary_error["title"]

        return summary


class WhatsAppStatusWebhook(BaseModel):
    """
    Container for WhatsApp status webhook data.

    Convenience model for handling status-only webhooks.
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    statuses: list[WhatsAppMessageStatus] = Field(
        ..., description="Array of message status updates"
    )

    @field_validator("statuses")
    @classmethod
    def validate_statuses_not_empty(
        cls, v: list[WhatsAppMessageStatus]
    ) -> list[WhatsAppMessageStatus]:
        """Validate statuses array is not empty."""
        if not v or len(v) == 0:
            raise ValueError("Status webhook must contain at least one status")
        return v

    @property
    def status_count(self) -> int:
        """Get the number of status updates."""
        return len(self.statuses)

    def get_statuses_by_type(self, status_type: str) -> list[WhatsAppMessageStatus]:
        """
        Get statuses filtered by type.

        Args:
            status_type: One of 'sent', 'delivered', 'read', 'failed'

        Returns:
            List of statuses matching the specified type.
        """
        return [status for status in self.statuses if status.status == status_type]

    def get_failed_statuses(self) -> list[WhatsAppMessageStatus]:
        """Get all failed message statuses."""
        return self.get_statuses_by_type("failed")

    def get_successful_statuses(self) -> list[WhatsAppMessageStatus]:
        """Get all successful message statuses (sent, delivered, read)."""
        return [status for status in self.statuses if status.is_successful]

    def has_failures(self) -> bool:
        """Check if any messages failed."""
        return any(status.is_failed for status in self.statuses)

    def to_summary_dict(self) -> dict[str, int | bool | list]:
        """
        Create a summary dictionary for the entire status webhook.

        Returns:
            Dictionary with aggregate status information.
        """
        status_counts = {
            "sent": len(self.get_statuses_by_type("sent")),
            "delivered": len(self.get_statuses_by_type("delivered")),
            "read": len(self.get_statuses_by_type("read")),
            "failed": len(self.get_statuses_by_type("failed")),
        }

        return {
            "total_statuses": self.status_count,
            "status_counts": status_counts,
            "has_failures": self.has_failures(),
            "success_rate": (
                (
                    status_counts["sent"]
                    + status_counts["delivered"]
                    + status_counts["read"]
                )
                / self.status_count
                * 100
            )
            if self.status_count > 0
            else 0,
            "failed_message_ids": [status.id for status in self.get_failed_statuses()],
        }


# Type aliases for convenience
StatusType = MessageStatus

# Status class aliases for compatibility
DeliveryStatus = WhatsAppMessageStatus
ReadStatus = WhatsAppMessageStatus
SentStatus = WhatsAppMessageStatus
FailedStatus = WhatsAppMessageStatus
