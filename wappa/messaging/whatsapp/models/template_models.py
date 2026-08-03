"""WhatsApp template message models."""

from enum import StrEnum
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
)


class WhatsAppTemplateMediaType(StrEnum):
    IMAGE = "image"
    VIDEO = "video"
    DOCUMENT = "document"


class TemplateParameterType(StrEnum):
    TEXT = "text"
    CURRENCY = "currency"
    DATE_TIME = "date_time"
    IMAGE = "image"
    VIDEO = "video"
    DOCUMENT = "document"
    LOCATION = "location"


class WhatsAppTemplateType(StrEnum):
    MARKETING = "marketing"
    UTILITY = "utility"
    AUTHENTICATION = "authentication"


class TemplateParameter(BaseModel):
    type: TemplateParameterType = Field(..., description="Parameter type")
    text: str | None = Field(
        None, max_length=1024, description="Text content for text parameters"
    )
    parameter_name: str | None = Field(
        None,
        max_length=128,
        pattern=r"^[a-zA-Z][a-zA-Z0-9_]*$",
        description=(
            "Optional named parameter identifier for explicit binding to template "
            "variables. Must start with a letter, alphanumeric and underscores only."
        ),
    )

    @field_validator("text")
    @classmethod
    def validate_text_required_for_text_type(
        cls,
        value: str | None,
        info: ValidationInfo,
    ) -> str | None:
        if info.data.get("type") == TemplateParameterType.TEXT and not value:
            raise ValueError("Text content is required for text type parameters")
        return value


class TemplateStateConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state_value: str = Field(
        ...,
        min_length=1,
        max_length=128,
        pattern=r"^[a-zA-Z0-9_-]+$",
        description="State identifier. Creates cache key: template-{state_value}",
    )
    ttl_seconds: int = Field(
        default=3600,
        ge=60,
        le=86400,
        description="State time-to-live in seconds (1 minute to 24 hours)",
    )
    initial_context: dict[str, Any] | None = Field(
        default=None,
        description="Optional context data to store with the state",
    )
    user_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=256,
        description=(
            "Optional canonical user id for cache scoping. When provided, "
            "Wappa keys the template state cache under this id directly, "
            "bypassing the configured IIdentityResolver. Use this when the "
            "caller has already resolved identity upstream (e.g. mapped a "
            "phone number to an internal account id)."
        ),
    )


class TemplateMessageStatus(BaseModel):
    """Current platform status for a configured Template."""

    template_name: str = Field(..., description="Template name")
    status: str = Field(..., description="Template status")
    language: str = Field(..., description="Template language")
    category: str | None = Field(None, description="Template category")
    components: list[dict] | None = Field(None, description="Template components")
