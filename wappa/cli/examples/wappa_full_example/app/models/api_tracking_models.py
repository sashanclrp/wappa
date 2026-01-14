"""Models for tracking API message activity in Redis."""

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class APIMessageHistoryEntry(BaseModel):
    """Individual API message event."""

    entry_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    message_type: str  # text, image, button, text_template, etc.
    recipient: str
    message_id: str | None
    success: bool
    error: str | None = None
    request_payload: dict[str, Any]
    tenant_id: str
    owner_id: str | None = None

    model_config = {"extra": "forbid"}

    @field_validator("recipient", "tenant_id", "owner_id", mode="before")
    @classmethod
    def convert_int_to_str(cls, v):
        """Convert int to str for ID fields (Redis numeric string issue)."""
        if isinstance(v, int):
            return str(v)
        return v


class APIMessageStatistics(BaseModel):
    """Global API message statistics."""

    total_messages_sent: int = 0
    successful_sends: int = 0
    failed_sends: int = 0

    # Message type breakdown (all types)
    message_type_counts: dict[str, int] = Field(default_factory=dict)

    # Metrics
    success_rate: float = 0.0
    total_recipients: int = 0

    # Timestamps
    first_message_sent: datetime | None = None
    last_message_sent: datetime | None = None
    last_updated: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_config = {"extra": "forbid"}

    def update_from_event(
        self,
        message_type: str,
        success: bool,
        recipient: str,
        unique_recipients: set[str],
    ) -> None:
        """Update statistics from API event."""
        now = datetime.now(UTC)

        self.total_messages_sent += 1
        if success:
            self.successful_sends += 1
        else:
            self.failed_sends += 1

        # Update type breakdown
        self.message_type_counts[message_type] = (
            self.message_type_counts.get(message_type, 0) + 1
        )

        # Update metrics
        if self.total_messages_sent > 0:
            self.success_rate = (self.successful_sends / self.total_messages_sent) * 100

        self.total_recipients = len(unique_recipients)

        # Update timestamps
        if self.first_message_sent is None:
            self.first_message_sent = now
        self.last_message_sent = now
        self.last_updated = now


class UserAPIActivity(BaseModel):
    """Per-user API activity log."""

    user_id: str
    messages_received: int = 0

    # Type breakdown
    message_type_counts: dict[str, int] = Field(default_factory=dict)

    # Timestamps
    first_message_received: datetime | None = None
    last_message_received: datetime | None = None
    last_updated: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # Recent history (last 10)
    recent_messages: list[dict[str, Any]] = Field(default_factory=list)

    model_config = {"extra": "forbid"}

    @field_validator("user_id", mode="before")
    @classmethod
    def convert_int_to_str(cls, v):
        """Convert int to str for user_id field (Redis numeric string issue)."""
        if isinstance(v, int):
            return str(v)
        return v

    def add_message_event(
        self,
        message_type: str,
        message_id: str | None,
        success: bool,
    ) -> None:
        """Record a new message received event."""
        now = datetime.now(UTC)

        self.messages_received += 1
        self.message_type_counts[message_type] = (
            self.message_type_counts.get(message_type, 0) + 1
        )

        if self.first_message_received is None:
            self.first_message_received = now
        self.last_message_received = now
        self.last_updated = now

        # Keep last 10 messages
        self.recent_messages.append(
            {
                "timestamp": now.isoformat(),
                "message_type": message_type,
                "message_id": message_id,
                "success": success,
            }
        )
        if len(self.recent_messages) > 10:
            self.recent_messages = self.recent_messages[-10:]
