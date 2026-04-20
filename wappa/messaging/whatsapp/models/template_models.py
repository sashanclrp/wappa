"""WhatsApp template message models."""

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from wappa.schemas.core.recipient import RecipientRequest


class WhatsAppTemplateMediaType(str, Enum):
    IMAGE = "image"
    VIDEO = "video"
    DOCUMENT = "document"


class TemplateParameterType(str, Enum):
    TEXT = "text"
    CURRENCY = "currency"
    DATE_TIME = "date_time"
    IMAGE = "image"
    VIDEO = "video"
    DOCUMENT = "document"
    LOCATION = "location"


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
    def validate_text_required_for_text_type(cls, v, info):
        if info.data.get("type") == TemplateParameterType.TEXT and not v:
            raise ValueError("Text content is required for text type parameters")
        return v


class TemplateComponent(BaseModel):
    type: str = Field(..., description="Component type (header, body, footer, button)")
    parameters: list[TemplateParameter] | None = Field(
        None, description="Component parameters"
    )


def _ensure_text_body_parameters(
    params: list[TemplateParameter] | None,
) -> list[TemplateParameter] | None:
    """Ensure all body parameters are of text type (shared across template messages)."""
    if params and any(p.type != TemplateParameterType.TEXT for p in params):
        raise ValueError("Template body parameters must be of type 'text'")
    return params


def _validate_coordinate(value: str, label: str, limit: int) -> str:
    """Validate a coordinate string falls within [-limit, limit]."""
    try:
        parsed = float(value)
    except (TypeError, ValueError) as e:
        raise ValueError(f"{label} must be a valid number") from e
    if not -limit <= parsed <= limit:
        raise ValueError(f"{label} must be between -{limit} and {limit} degrees")
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


class TextTemplateMetadata(BaseModel):
    text_content: str | None = Field(
        None,
        max_length=4096,
        description=(
            "Optional text content summary for AI context. "
            "NOT sent to WhatsApp - internal context only."
        ),
    )
    system_message: str | None = Field(
        None,
        max_length=8192,
        description=(
            "Optional system message for AI agent context. "
            "NOT sent to WhatsApp - internal AI context only."
        ),
    )
    metadata: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Optional free-form metadata dict for analytics/tracing. "
            "NOT sent to WhatsApp - internal context only."
        ),
    )


class MediaTemplateMetadata(BaseModel):
    text_content: str | None = Field(
        None,
        max_length=4096,
        description=(
            "Optional text content summary for AI context. "
            "NOT sent to WhatsApp - internal context only."
        ),
    )
    media_description: str | None = Field(
        None,
        max_length=2048,
        description=(
            "Optional media description for AI context. "
            "NOT sent to WhatsApp - internal context only."
        ),
    )
    media_transcript: str | None = Field(
        None,
        max_length=10000,
        description=(
            "Optional transcript for video/audio media. "
            "NOT sent to WhatsApp - internal context only. "
            "Only valid for video and audio media types."
        ),
    )
    system_message: str | None = Field(
        None,
        max_length=8192,
        description=(
            "Optional system message for AI agent context. "
            "NOT sent to WhatsApp - internal AI context only."
        ),
    )
    metadata: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Optional free-form metadata dict for analytics/tracing. "
            "NOT sent to WhatsApp - internal context only."
        ),
    )


class LocationTemplateMetadata(BaseModel):
    text_content: str | None = Field(
        None,
        max_length=4096,
        description=(
            "Optional text content summary for AI context. "
            "NOT sent to WhatsApp - internal context only."
        ),
    )
    system_message: str | None = Field(
        None,
        max_length=8192,
        description=(
            "Optional system message for AI agent context. "
            "NOT sent to WhatsApp - internal AI context only."
        ),
    )
    metadata: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Optional free-form metadata dict for analytics/tracing. "
            "NOT sent to WhatsApp - internal context only."
        ),
    )


class TemplateLanguage(BaseModel):
    code: str = Field(default="es", description="BCP-47 language code")

    @field_validator("code")
    @classmethod
    def validate_language_code(cls, v):
        common_codes = {
            "es", "en", "en_US", "pt_BR", "fr", "de", "it", "ja", "ko", "zh",
            "ar", "hi", "ru", "tr", "nl", "sv", "da", "no", "pl", "cs", "hu",
        }
        if v not in common_codes and not v.replace("_", "").replace("-", "").isalpha():
            raise ValueError(f"Invalid language code format: {v}")
        return v


class BaseTemplateMessage(RecipientRequest):
    template_name: str = Field(
        ..., min_length=1, max_length=512, description="Template name"
    )
    language: TemplateLanguage = Field(
        default_factory=TemplateLanguage, description="Template language"
    )


class TextTemplateMessage(BaseTemplateMessage):
    body_parameters: list[TemplateParameter] | None = Field(
        None, max_length=10, description="Body parameters for text replacement"
    )
    state_config: TemplateStateConfig | None = Field(
        default=None,
        description="Optional state configuration for response routing",
    )
    template_metadata: TextTemplateMetadata | None = Field(
        default=None,
        description="Optional metadata for AI context (internal use only, not sent to WhatsApp)",
    )

    @field_validator("body_parameters")
    @classmethod
    def _validate_body_parameters(cls, v):
        return _ensure_text_body_parameters(v)


class MediaTemplateMessage(BaseTemplateMessage):
    media_type: WhatsAppTemplateMediaType = Field(..., description="Media type for header")
    media_id: str | None = Field(None, min_length=1, description="Uploaded media ID")
    media_url: str | None = Field(None, pattern=r"^https?://", description="Media URL")
    body_parameters: list[TemplateParameter] | None = Field(
        None, max_length=10, description="Body parameters for text replacement"
    )
    state_config: TemplateStateConfig | None = Field(
        default=None,
        description="Optional state configuration for response routing",
    )
    template_metadata: MediaTemplateMetadata | None = Field(
        default=None,
        description="Optional metadata for AI context (internal use only, not sent to WhatsApp)",
    )

    @model_validator(mode="after")
    def validate_media_source(self):
        if bool(self.media_id) == bool(self.media_url):
            raise ValueError(
                "Either media_id or media_url must be provided, but not both"
            )
        return self

    @field_validator("body_parameters")
    @classmethod
    def _validate_body_parameters(cls, v):
        return _ensure_text_body_parameters(v)

    @field_validator("template_metadata")
    @classmethod
    def validate_transcript_for_media_type(cls, v, info):
        if v and v.media_transcript and info.data.get("media_type") == WhatsAppTemplateMediaType.IMAGE:
            raise ValueError(
                "media_transcript field is not supported for image media type. "
                "Transcript is only valid for video and audio media types."
            )
        return v


class LocationTemplateMessage(BaseTemplateMessage):
    latitude: str = Field(..., description="Location latitude as string")
    longitude: str = Field(..., description="Location longitude as string")
    name: str = Field(..., min_length=1, max_length=100, description="Location name")
    address: str = Field(
        ..., min_length=1, max_length=1000, description="Location address"
    )
    body_parameters: list[TemplateParameter] | None = Field(
        None, max_length=10, description="Body parameters for text replacement"
    )
    state_config: TemplateStateConfig | None = Field(
        default=None,
        description="Optional state configuration for response routing",
    )
    template_metadata: LocationTemplateMetadata | None = Field(
        default=None,
        description="Optional metadata for AI context (internal use only, not sent to WhatsApp)",
    )

    @field_validator("latitude")
    @classmethod
    def validate_latitude(cls, v):
        return _validate_coordinate(v, "Latitude", 90)

    @field_validator("longitude")
    @classmethod
    def validate_longitude(cls, v):
        return _validate_coordinate(v, "Longitude", 180)

    @field_validator("body_parameters")
    @classmethod
    def _validate_body_parameters(cls, v):
        return _ensure_text_body_parameters(v)


class TemplateMessageStatus(BaseModel):
    template_name: str = Field(..., description="Template name")
    status: str = Field(..., description="Template status")
    language: str = Field(..., description="Template language")
    category: str | None = Field(None, description="Template category")
    components: list[dict] | None = Field(None, description="Template components")


class TemplateValidationResult(BaseModel):
    valid: bool = Field(..., description="Whether template is valid")
    template_name: str = Field(..., description="Template name")
    errors: list[str] | None = Field(None, description="Validation errors")
    warnings: list[str] | None = Field(None, description="Validation warnings")
