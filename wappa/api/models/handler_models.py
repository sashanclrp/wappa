from typing import Any

from pydantic import BaseModel, Field

from wappa.schemas.core.recipient import RecipientRequest


class HandlerStateConfig(BaseModel):
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


class SetHandlerStateRequest(RecipientRequest):
    handler_config: HandlerStateConfig = Field(
        ..., description="Handler state configuration"
    )


class HandlerStateResponse(BaseModel):
    success: bool
    message: str
    recipient: str
    handler_value: str
    cache_key: str
    expires_at: str  # ISO timestamp
