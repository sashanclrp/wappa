"""
API message event model for outgoing message tracking.

Follows Interface Segregation - separate from webhook models
since API events have different context (outgoing vs incoming).
"""

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class APIMessageEvent(BaseModel):
    """
    Event model for API-sent messages.

    This model captures the full context of an outgoing message sent via
    the REST API, enabling developers to track messages, update databases,
    and trigger workflows.

    Example:
        When a message is sent via POST /api/whatsapp/messages/send-text,
        an APIMessageEvent is created with:
        - message_type: "text"
        - recipient: "1234567890"
        - request_payload: {"message": "Hello", "recipient": "1234567890"}
        - response_success: True
        - message_id: "wamid.xxx"
    """

    # Event metadata
    event_type: Literal["api_message_sent"] = "api_message_sent"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # Message details
    message_type: str = Field(
        ...,
        description="Type of message sent (text, image, template, button, etc.)",
    )
    message_id: str | None = Field(
        default=None,
        description="WhatsApp message ID from Meta API response",
    )
    recipient: str = Field(
        ...,
        description="Recipient phone number",
    )

    # Request context
    request_payload: dict[str, Any] = Field(
        ...,
        description="Original API request body",
    )

    # Response context
    response_success: bool = Field(
        ...,
        description="Whether the message was sent successfully",
    )
    response_error: str | None = Field(
        default=None,
        description="Error message if send failed",
    )
    meta_response: dict[str, Any] | None = Field(
        default=None,
        description="Raw Meta API response (if available)",
    )

    # Tenant context
    tenant_id: str = Field(
        ...,
        description="Tenant identifier for multi-tenant support",
    )
    owner_id: str | None = Field(
        default=None,
        description="Owner identifier (if available)",
    )

    model_config = {"extra": "forbid"}
