"""
External event model for non-messaging-platform webhooks.

Follows Interface Segregation - separate from webhook and API event models
since external events have different context (provider-originated vs platform-originated).
"""

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


class ExternalEvent(BaseModel):
    """
    Event model for external webhook providers (payments, CRM, etc.).

    Example:
        event = ExternalEvent(
            source="mercadopago",
            event_type="payment.approved",
            tenant_id="acme_corp",
            payload={"payment_id": "12345", "amount": 99.99},
        )
    """

    # Provider identification
    source: str = Field(
        ...,
        description="Provider name (e.g., 'mercadopago', 'stripe', 'hubspot')",
    )
    event_type: str = Field(
        ...,
        description="Dot-notation event type (e.g., 'payment.approved')",
    )

    # Tenant and user context
    tenant_id: str = Field(
        ...,
        description="Tenant identifier extracted from URL path",
    )
    user_id: str | None = Field(
        default=None,
        description="User identifier resolved by processor (e.g., phone number)",
    )

    # Event data
    payload: dict[str, Any] = Field(
        default_factory=dict,
        description="Validated webhook payload data",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional context (headers, signature status, etc.)",
    )

    # Event metadata
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    raw_data: dict[str, Any] | None = Field(
        default=None,
        description="Original raw webhook body for debugging",
        exclude=True,
    )

    model_config = {"extra": "forbid"}
