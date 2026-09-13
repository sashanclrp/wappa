"""
External event model for non-messaging-platform webhooks (payments, CRM, etc.).
"""

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


class ExternalEvent(BaseModel):
    """
    Typed event produced by an IWebhookProcessor from a raw HTTP request.

    Example:
        event = ExternalEvent(
            source="mercadopago",
            event_type="payment.approved",
            webhook_id="merchant_123",
            payload={"payment_id": "12345", "amount": 99.99},
        )
    """

    # Source identity
    source: str  # e.g. "mercadopago", "stripe", "hubspot"
    event_type: str  # dot-notation, e.g. "payment.approved"

    # Optional transport routing identity. This is never an Inbox identifier.
    webhook_id: str | None = Field(
        default=None,
        description="Opaque webhook route identifier supplied by Wappa",
    )

    # Payload
    payload: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    # Metadata
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    raw_data: dict[str, Any] | None = Field(default=None, exclude=True)

    model_config = {"extra": "forbid"}
