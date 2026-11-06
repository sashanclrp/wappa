"""Universal system webhook: Platform-level account, identity, group and sync events."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from wappa.schemas.core.types import PlatformType
from wappa.webhooks.core.webhook_interfaces.base_components import (
    InboxBase,
    SystemEventDetail,
    UserBase,
)


class SystemEventType(StrEnum):
    """Types of platform-level system events."""

    NUMBER_CHANGE = "number_change"
    USER_ID_CHANGE = "user_id_change"
    MARKETING_PREFERENCE = "marketing_preference"
    BUSINESS_USERNAME_UPDATE = "business_username_update"
    GROUP_PARTICIPANTS_UPDATE = "group_participants_update"
    SMB_APP_STATE_SYNC = "smb_app_state_sync"
    # User interaction events (e.g. marketing message link clicks).
    USER_ACTION = "user_action"
    # Standalone entry-point context (e.g. Instagram messaging_referral).
    REFERRAL = "referral"
    UNSUPPORTED_EVENT = "unsupported_event"


class SystemWebhook(BaseModel):
    """
    Universal interface for platform-level account and identity events.

    This interface represents system events that are NOT user messages:
    - Phone number changes (user_changed_number)
    - BSUID changes (user_changed_user_id, user_id_update)
    - Marketing preference changes (user_preferences)
    - Group, business username, account, and Coexistence sync events

    All platforms must transform their system webhooks to this format.
    """

    model_config = ConfigDict(
        extra="forbid", str_strip_whitespace=True, validate_assignment=True
    )

    # Core identification
    inbox: InboxBase = Field(description="Business inbox identification")

    # System event information
    system_event_type: SystemEventType = Field(description="Type of system event")
    event_detail: SystemEventDetail = Field(
        description="Platform-agnostic event details"
    )

    # User context (when available from contacts array)
    user: UserBase | None = Field(
        default=None,
        description="User identification (from contacts if available)",
    )

    # Universal metadata
    timestamp: datetime = Field(description="When the system event occurred")
    platform: PlatformType = Field(description="Source messaging platform")
    webhook_id: str = Field(description="Unique identifier for this webhook event")

    # Raw webhook data (for debugging and inspection)
    raw_webhook_data: dict | None = Field(
        default=None,
        description="Original raw webhook JSON payload",
        exclude=True,
    )

    @property
    def is_number_change(self) -> bool:
        """Check if this is a phone number change event."""
        return self.system_event_type == SystemEventType.NUMBER_CHANGE

    @property
    def is_user_id_change(self) -> bool:
        """Check if this is a BSUID change event."""
        return self.system_event_type == SystemEventType.USER_ID_CHANGE

    @property
    def is_marketing_preference(self) -> bool:
        """Check if this is a marketing preference change event."""
        return self.system_event_type == SystemEventType.MARKETING_PREFERENCE

    def get_summary(self) -> dict[str, Any]:
        """Get a summary of this webhook for logging and monitoring."""
        return {
            "webhook_type": "system",
            "platform": self.platform.value,
            "system_event_type": self.system_event_type.value,
            "wa_id": self.event_detail.wa_id,
            "user_id": self.event_detail.user_id,
            "inbox": self.inbox.get_inbox_key(),
            "timestamp": self.timestamp.isoformat(),
        }

    def get_raw_webhook_data(self) -> dict | None:
        """Get the original raw webhook JSON payload."""
        return self.raw_webhook_data

    def set_raw_webhook_data(self, raw_data: dict) -> None:
        """Set the original raw webhook JSON payload."""
        self.raw_webhook_data = raw_data
