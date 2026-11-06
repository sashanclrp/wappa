"""
WhatsApp message status schema.

This module contains Pydantic models for processing WhatsApp message status
updates including delivery receipts, read receipts, and failure notifications.
"""

from __future__ import annotations

from typing import Any, Literal, Self

from pydantic import ConfigDict, Field, field_validator, model_validator

from wappa.schemas.core.types import MessageStatus, PlatformType
from wappa.webhooks.core.base_status import BaseMessageStatus
from wappa.webhooks.whatsapp.models.base import Conversation, MessageError, Pricing
from wappa.webhooks.whatsapp.models.status_reports import StatusReports

KNOWN_WHATSAPP_STATUSES = frozenset({"sent", "delivered", "read", "played", "failed"})
"""``played``: the User played a voice note (Meta, observed 2026-11-05)."""


class WhatsAppMessageStatus(StatusReports, BaseMessageStatus):
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
        extra="allow", str_strip_whitespace=True, validate_assignment=True
    )

    # Core status fields
    id: str = Field(..., description="WhatsApp message ID that this status refers to")
    wa_status: Literal["sent", "delivered", "read", "played", "failed"] = Field(
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
    recipient_parent_bsuid: str | None = Field(
        None,
        alias="recipient_parent_user_id",
        description="Parent BSUID of the recipient when enabled",
    )
    recipient_type: Literal["individual", "group"] | None = Field(
        None, description="Recipient type for individual or group messages"
    )
    recipient_participant_id: str | None = Field(
        None, description="Group participant phone number when available"
    )
    recipient_participant_bsuid: str | None = Field(
        None,
        alias="recipient_participant_user_id",
        description="Group participant BSUID",
    )
    recipient_participant_parent_bsuid: str | None = Field(
        None,
        alias="recipient_participant_parent_user_id",
        description="Group participant parent BSUID when enabled",
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
    def validate_status_consistency(self) -> Self:
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
        return self.wa_status in ["sent", "delivered", "read", "played"]

    @property
    def unix_timestamp(self) -> int:
        """Get the timestamp as an integer."""
        return int(self.wa_timestamp)

    @property
    def conversation_id(self) -> str | None:
        """Get conversation ID from status data."""
        return self.conversation.id if self.conversation else None

    @property
    def message_id(self) -> str:
        """Get the message ID this status refers to."""
        return self.id

    @property
    def platform(self) -> PlatformType:
        """Get the platform name."""
        return PlatformType.WHATSAPP

    @classmethod
    def from_platform_data(
        cls, data: dict[str, Any], **kwargs: Any
    ) -> WhatsAppMessageStatus:
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

    def get_all_errors(self) -> list[dict[str, Any]]:
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
                "details": error.error_data.details if error.error_data else "",
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
        return self.get_error_info()

    def to_summary_dict(self) -> dict[str, Any]:
        """
        Create a summary dictionary for logging and analysis.

        Returns:
            Dictionary with key status information for structured logging.
        """
        summary: dict[str, Any] = {
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
