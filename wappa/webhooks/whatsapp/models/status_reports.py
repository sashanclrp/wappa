"""The dict views of a WhatsApp status: errors, delivery, platform data, summary."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from wappa.webhooks.whatsapp.models.base import Conversation, MessageError, Pricing


class StatusReports:
    """Read-only reports over the fields ``WhatsAppMessageStatus`` declares."""

    if TYPE_CHECKING:
        id: str
        wa_status: str
        wa_timestamp: str
        wa_recipient_id: str | None
        recipient_type: str | None
        recipient_bsuid: str | None
        recipient_identity_key_hash: str | None
        recipient_parent_bsuid: str | None
        recipient_participant_id: str | None
        recipient_participant_bsuid: str | None
        recipient_participant_parent_bsuid: str | None
        biz_opaque_callback_data: str | None
        conversation: Conversation | None
        pricing: Pricing | None
        errors: list[MessageError] | None

        @property
        def recipient_id(self) -> str: ...
        @property
        def timestamp(self) -> int: ...
        @property
        def has_recipient_phone(self) -> bool: ...
        @property
        def is_failed(self) -> bool: ...
        @property
        def is_successful(self) -> bool: ...

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
            "recipient_parent_bsuid": self.recipient_parent_bsuid,
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
                "subtype": self.pricing.subtype,
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
            "recipient_parent_bsuid": self.recipient_parent_bsuid,
            "recipient_type": self.recipient_type,
            "recipient_participant_id": self.recipient_participant_id,
            "recipient_participant_bsuid": self.recipient_participant_bsuid,
            "recipient_participant_parent_bsuid": self.recipient_participant_parent_bsuid,
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
