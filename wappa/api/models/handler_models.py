"""
Pydantic models for state handler API endpoints.

This module defines request/response models for the state handler assignment API,
which allows assigning cache-based state handlers to users after any message type
has been sent.
"""

from typing import Any

from pydantic import BaseModel, Field


class HandlerStateConfig(BaseModel):
    """Configuration for assigning a cache state handler to a user."""

    handler_value: str = Field(
        ...,
        description="Unique identifier for the handler state",
        min_length=1,
        max_length=100,
    )

    ttl_seconds: int = Field(
        ...,
        description="Time-to-live in seconds for the state handler",
        ge=60,
        le=86400,  # 1 minute to 24 hours
    )

    initial_context: dict[str, Any] | None = Field(
        default=None,
        description="Optional context data to initialize the handler with",
    )


class SetHandlerStateRequest(BaseModel):
    """Request to assign a state handler to a user."""

    recipient: str = Field(
        ...,
        description="User phone number (recipient)",
        pattern=r"^\+?[1-9]\d{1,14}$",  # E.164 format
    )

    handler_config: HandlerStateConfig = Field(
        ..., description="Handler state configuration"
    )


class HandlerStateResponse(BaseModel):
    """Response after setting handler state."""

    success: bool
    message: str
    recipient: str
    handler_value: str
    cache_key: str
    expires_at: str  # ISO timestamp
