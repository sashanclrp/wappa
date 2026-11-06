"""Universal custom webhook: envelope for app-registered event payloads."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from wappa.schemas.core.types import PlatformType
from wappa.webhooks.core.webhook_interfaces.base_components import (
    InboxBase,
)


class CustomWebhook(BaseModel):
    """
    Universal interface for app-registered Meta webhook field values.

    Apps register a typed ``(parser, handler)`` for each Meta field value the
    framework does not natively understand (e.g. ``message_template_status_update``,
    ``account_update``, ``phone_number_quality_update``). The processor builds
    a ``CustomWebhook`` whose ``parsed`` attribute is the parser's output —
    typed, never a raw dict — and the dispatcher routes it to the registered
    async handler.

    The original ``value`` dict from Meta is preserved in ``raw_value`` so
    handlers can inspect fields the parser may have ignored.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
        arbitrary_types_allowed=True,
    )

    inbox: InboxBase = Field(description="Business inbox identification")

    field_name: str = Field(
        description="The Meta webhook field value (e.g. 'message_template_status_update')"
    )
    parsed: BaseModel = Field(
        description="App-supplied Pydantic model parsed from the raw value dict"
    )
    raw_value: dict = Field(
        description="Original Meta 'value' dict, preserved for fields the parser may have ignored"
    )

    timestamp: datetime = Field(description="When the webhook was received")
    platform: PlatformType = Field(description="Source messaging platform")
    webhook_id: str = Field(description="Unique identifier for this webhook event")

    raw_webhook_data: dict | None = Field(
        default=None,
        description="Original raw webhook JSON payload",
        exclude=True,
    )

    def get_summary(self) -> dict[str, Any]:
        """Get a summary of this webhook for logging and monitoring."""
        return {
            "webhook_type": "custom",
            "platform": self.platform.value,
            "field_name": self.field_name,
            "inbox": self.inbox.get_inbox_key(),
            "timestamp": self.timestamp.isoformat(),
        }

    def get_raw_webhook_data(self) -> dict | None:
        """Get the original raw webhook JSON payload."""
        return self.raw_webhook_data

    def set_raw_webhook_data(self, raw_data: dict) -> None:
        """Set the original raw webhook JSON payload."""
        self.raw_webhook_data = raw_data
