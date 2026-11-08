"""The event every Scheduled Task reaches the Host handler with.

One model for every trigger: a Redis expiry, a built-in static cron, or a Host
scheduler (APScheduler, Celery, custom). Scheduling, recurrence, retries and
history stay with the engine; the optional fields here only carry its facts.
"""

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from wappa.domain.inbox.identity import InboxRef

SOURCE_REDIS_EXPIRY = "redis_expiry"
SOURCE_STATIC_CRON = "static_cron"


def _as_utc(value: datetime | None) -> datetime | None:
    """Normalize to UTC; a naive timestamp has no knowable instant, so refuse it."""
    if value is None:
        return None
    if value.tzinfo is None:
        raise ValueError("Scheduled Event timestamps must be timezone-aware")
    return value.astimezone(UTC)


class ScheduledEvent(BaseModel):
    """One Scheduled Task invocation.

    The scope is explicit: ``inbox_ref`` and ``user_id`` for User work,
    ``inbox_ref`` alone for Inbox work, neither for System work. Callers supply
    the subject identifier they know; ``Scheduling.dispatch`` replaces
    ``user_id`` with the canonical User before the Host hook runs.

    Example:
        event = ScheduledEvent(
            action="appointment_reminder",
            source="apscheduler",
            inbox_ref=InboxRef.whatsapp("1234567890"),
            user_id="5551234567",
            payload={"appointment_id": "A-17"},
            execution_id="job-42:2026-11-06T14:00:00Z",
        )
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    action: str = Field(..., min_length=1, description="Host routing key.")
    source: str = Field(
        ...,
        min_length=1,
        description="What fired it: redis_expiry, static_cron, or the Host's engine.",
    )
    inbox_ref: InboxRef | None = Field(
        default=None, description="Qualified Inbox; absent for System work."
    )
    user_id: str | None = Field(
        default=None,
        min_length=1,
        description="Subject User, canonical once dispatched. Requires inbox_ref.",
    )
    identifier: str | None = Field(
        default=None,
        description="Opaque task identifier, such as an Expiry Key's identifier. "
        "Wappa never treats it as a User.",
    )
    payload: dict[str, Any] = Field(
        default_factory=dict, description="Host data for this invocation."
    )
    scheduled_for: datetime | None = Field(
        default=None, description="Intended fire time, in UTC, when the engine knows."
    )
    dispatched_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="UTC time of dispatch. Wappa stamps it when dispatching.",
    )
    execution_id: str | None = Field(
        default=None,
        description="The engine's job or occurrence ID, for correlation only. "
        "Indexed Redis expiry retains the pending generation here; this is not an exactly-once guarantee.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Opaque engine facts: cron expression, retry attempt, tags.",
    )

    @field_validator("scheduled_for", "dispatched_at")
    @classmethod
    def _timestamps_are_utc(cls, value: datetime | None) -> datetime | None:
        return _as_utc(value)

    @model_validator(mode="after")
    def _user_scope_requires_an_inbox(self) -> "ScheduledEvent":
        if self.user_id is not None and self.inbox_ref is None:
            raise ValueError("A User-scoped Scheduled Event requires inbox_ref")
        return self
