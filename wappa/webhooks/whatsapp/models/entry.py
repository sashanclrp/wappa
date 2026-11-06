"""One webhook entry: the WABA id and its changes."""

from __future__ import annotations

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)

from wappa.webhooks.whatsapp.models.change import WebhookChange


class WebhookEntry(BaseModel):
    """
    Entry object for WhatsApp Business Account webhook.

    Contains the business account ID and the changes that occurred.
    """

    model_config = ConfigDict(extra="allow", str_strip_whitespace=True)

    id: str = Field(..., description="WhatsApp Business Account ID")
    time: int | None = Field(
        None,
        description="Webhook trigger timestamp used by account-scoped fields",
    )
    changes: list[WebhookChange] = Field(
        ..., description="Array of changes (typically contains one change)"
    )

    @field_validator("id")
    @classmethod
    def validate_business_account_id(cls, v: str) -> str:
        """Validate business account ID format."""
        if not v or not v.isdigit():
            raise ValueError("Business account ID must be numeric")
        if len(v) < 10:
            raise ValueError("Business account ID must be at least 10 digits")
        return v

    @field_validator("changes")
    @classmethod
    def validate_changes_not_empty(cls, v: list[WebhookChange]) -> list[WebhookChange]:
        """Validate changes array is not empty."""
        if not v or len(v) == 0:
            raise ValueError("Changes array cannot be empty")
        return v
