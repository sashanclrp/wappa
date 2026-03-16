"""
Cron event model for scheduled background task triggers.

Follows Interface Segregation - separate from webhook and external event models
since cron events originate from the scheduler, not from external HTTP requests.
"""

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


class CronEvent(BaseModel):
    """
    Event model for scheduled cron job triggers.

    Example:
        event = CronEvent(
            cron_id="send_daily_report",
            cron_expr="0 9 * * *",
            tenant_id="acme",
            user_id="5551234567",
            payload={"report_type": "summary"},
        )
    """

    # Cron identification
    cron_id: str = Field(
        ...,
        description="Unique job name assigned at add_cron() — primary dispatch key",
    )
    cron_expr: str = Field(
        ...,
        description="Cron expression that triggered (e.g., '0 9 * * *')",
    )
    tags: list[str] = Field(
        default_factory=list,
        description="Tags assigned at registration for secondary filtering",
    )

    # Tenant and user context (optional — crons can be system-wide)
    tenant_id: str | None = Field(
        default=None,
        description="Tenant identifier — if set, full context (messenger, cache, db) available",
    )
    user_id: str | None = Field(
        default=None,
        description="User identifier — for messenger/cache scoping",
    )

    # Event data
    payload: dict[str, Any] = Field(
        default_factory=dict,
        description="Static config data attached at registration time",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Runtime info (actual_time, scheduled_time, etc.)",
    )

    # Event metadata
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_config = {"extra": "forbid"}
