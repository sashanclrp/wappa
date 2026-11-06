"""Universal call webhook: connected, terminated and status call events."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from wappa.schemas.core.types import PlatformType
from wappa.webhooks.core.webhook_interfaces.base_components import (
    InboxBase,
    UserBase,
)


class CallWebhook(BaseModel):
    """Universal Model for connected, terminated, and status call events."""

    model_config = ConfigDict(
        extra="forbid", str_strip_whitespace=True, validate_assignment=True
    )

    inbox: InboxBase
    user: UserBase | None = None
    call_id: str
    event: str
    direction: str
    timestamp: datetime
    status: str | None = None
    duration: int | None = None
    phone_number: str | None = None
    bsuid: str | None = None
    parent_bsuid: str | None = None
    business_opaque_data: str | None = None
    session: dict | None = None
    platform: PlatformType
    webhook_id: str
    raw_call: dict = Field(default_factory=dict)
    raw_webhook_data: dict | None = Field(default=None, exclude=True)

    @property
    def user_id(self) -> str:
        if self.user:
            return self.user.user_id
        return self.bsuid or self.phone_number or ""

    def set_raw_webhook_data(self, raw_data: dict) -> None:
        self.raw_webhook_data = raw_data
