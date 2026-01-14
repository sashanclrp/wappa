"""
WhatsApp template message models.

Provides Pydantic v2 validation models for WhatsApp template operations:
- TextTemplateMessage: Text-only template messages
- MediaTemplateMessage: Template messages with media headers
- LocationTemplateMessage: Template messages with location headers

Based on WhatsApp Cloud API 2025 template message specifications.
"""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class MediaType(str, Enum):
    """Media types supported in template headers."""

    IMAGE = "image"
    VIDEO = "video"
    DOCUMENT = "document"


class TemplateParameterType(str, Enum):
    """Template parameter types."""

    TEXT = "text"
    CURRENCY = "currency"
    DATE_TIME = "date_time"
    IMAGE = "image"
    VIDEO = "video"
    DOCUMENT = "document"
    LOCATION = "location"


class TemplateParameter(BaseModel):
    """Template parameter for dynamic content replacement."""

    type: TemplateParameterType = Field(..., description="Parameter type")
    text: str | None = Field(
        None, max_length=1024, description="Text content for text parameters"
    )

    @field_validator("text")
    @classmethod
    def validate_text_required_for_text_type(cls, v, info):
        """Validate that text is provided for text type parameters."""
        if info.data.get("type") == TemplateParameterType.TEXT and not v:
            raise ValueError("Text content is required for text type parameters")
        return v


class TemplateComponent(BaseModel):
    """Template component (header, body, footer, button)."""

    type: str = Field(..., description="Component type (header, body, footer, button)")
    parameters: list[TemplateParameter] | None = Field(
        None, description="Component parameters"
    )


class TemplateStateConfig(BaseModel):
    """Configuration for template-triggered state management.

    When a template is sent with state_config, the system creates a
    user-scoped cache entry that can be retrieved when the user responds.
    This enables routing subsequent user responses to specific handlers.

    Example:
        Send a template with state_config:
        {
            "state_value": "reschedule_flow",
            "ttl_seconds": 3600,
            "initial_context": {"appointment_id": "apt-123"}
        }

        When user responds, the handler can check for state:
        state = await cache.get_state("template-reschedule_flow")
    """

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

    model_config = {"extra": "forbid"}


class TextTemplateMetadata(BaseModel):
    """Metadata for text template messages (internal AI context only).

    This metadata is NOT sent to WhatsApp API - used for internal AI agent
    context only to provide additional information about template content.
    """

    text_content: str | None = Field(
        None,
        max_length=4096,
        description=(
            "Optional text content summary for AI context. "
            "Describes the template content for AI agents. "
            "NOT sent to WhatsApp - internal context only."
        ),
    )


class MediaTemplateMetadata(BaseModel):
    """Metadata for media template messages (internal AI context only).

    This metadata is NOT sent to WhatsApp API - used for internal AI agent
    context only to provide additional information about template content.
    """

    text_content: str | None = Field(
        None,
        max_length=4096,
        description=(
            "Optional text content summary for AI context. "
            "Describes the template content for AI agents. "
            "NOT sent to WhatsApp - internal context only."
        ),
    )
    media_description: str | None = Field(
        None,
        max_length=2048,
        description=(
            "Optional media description for AI context. "
            "Describes the media content for AI agents. "
            "NOT sent to WhatsApp - internal context only."
        ),
    )
    media_transcript: str | None = Field(
        None,
        max_length=10000,
        description=(
            "Optional transcript for video/audio media. "
            "Provides text transcription of media audio for AI agents. "
            "NOT sent to WhatsApp - internal context only. "
            "Only valid for video and audio media types."
        ),
    )


class LocationTemplateMetadata(BaseModel):
    """Metadata for location template messages (internal AI context only).

    This metadata is NOT sent to WhatsApp API - used for internal AI agent
    context only to provide additional information about template content.
    """

    text_content: str | None = Field(
        None,
        max_length=4096,
        description=(
            "Optional text content summary for AI context. "
            "Describes the template content for AI agents. "
            "NOT sent to WhatsApp - internal context only."
        ),
    )


class TemplateLanguage(BaseModel):
    """Template language configuration."""

    code: str = Field(default="es", description="BCP-47 language code")

    @field_validator("code")
    @classmethod
    def validate_language_code(cls, v):
        """Validate BCP-47 language code format."""
        # Basic validation for common language codes
        common_codes = [
            "es",
            "en",
            "en_US",
            "pt_BR",
            "fr",
            "de",
            "it",
            "ja",
            "ko",
            "zh",
            "ar",
            "hi",
            "ru",
            "tr",
            "nl",
            "sv",
            "da",
            "no",
            "pl",
            "cs",
            "hu",
        ]

        if v not in common_codes and not v.replace("_", "").replace("-", "").isalpha():
            raise ValueError(f"Invalid language code format: {v}")
        return v


class BaseTemplateMessage(BaseModel):
    """Base template message with common fields."""

    recipient: str = Field(
        ..., pattern=r"^\d{10,15}$", description="Recipient phone number"
    )
    template_name: str = Field(
        ..., min_length=1, max_length=512, description="Template name"
    )
    language: TemplateLanguage = Field(
        default_factory=lambda: TemplateLanguage(), description="Template language"
    )


class TextTemplateMessage(BaseTemplateMessage):
    """Text-only template message."""

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
    def validate_body_parameters(cls, v):
        """Validate body parameters are text type."""
        if v:
            for param in v:
                if param.type != TemplateParameterType.TEXT:
                    raise ValueError(
                        "Text template body parameters must be of type 'text'"
                    )
        return v


class MediaTemplateMessage(BaseTemplateMessage):
    """Template message with media header."""

    media_type: MediaType = Field(..., description="Media type for header")
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

    @field_validator("media_id", "media_url")
    @classmethod
    def validate_media_source(cls, v, info):
        """Validate that either media_id or media_url is provided, but not both."""
        values = info.data
        media_id = values.get("media_id")
        media_url = values.get("media_url")

        if (media_id and media_url) or (not media_id and not media_url):
            raise ValueError(
                "Either media_id or media_url must be provided, but not both"
            )
        return v

    @field_validator("body_parameters")
    @classmethod
    def validate_body_parameters(cls, v):
        """Validate body parameters are text type."""
        if v:
            for param in v:
                if param.type != TemplateParameterType.TEXT:
                    raise ValueError(
                        "Media template body parameters must be of type 'text'"
                    )
        return v

    @field_validator("template_metadata")
    @classmethod
    def validate_transcript_for_media_type(cls, v, info):
        """Validate that media_transcript is only provided for video/audio media types."""
        if v and v.media_transcript:
            media_type = info.data.get("media_type")
            if media_type == MediaType.IMAGE:
                raise ValueError(
                    "media_transcript field is not supported for image media type. "
                    "Transcript is only valid for video and audio media types."
                )
        return v


class LocationTemplateMessage(BaseTemplateMessage):
    """Template message with location header."""

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
        """Validate latitude range (-90 to 90)."""
        try:
            lat = float(v)
            if not -90 <= lat <= 90:
                raise ValueError("Latitude must be between -90 and 90 degrees")
        except ValueError as e:
            if "could not convert" in str(e):
                raise ValueError("Latitude must be a valid number") from e
            raise
        return v

    @field_validator("longitude")
    @classmethod
    def validate_longitude(cls, v):
        """Validate longitude range (-180 to 180)."""
        try:
            lon = float(v)
            if not -180 <= lon <= 180:
                raise ValueError("Longitude must be between -180 and 180 degrees")
        except ValueError as e:
            if "could not convert" in str(e):
                raise ValueError("Longitude must be a valid number") from e
            raise
        return v

    @field_validator("body_parameters")
    @classmethod
    def validate_body_parameters(cls, v):
        """Validate body parameters are text type."""
        if v:
            for param in v:
                if param.type != TemplateParameterType.TEXT:
                    raise ValueError(
                        "Location template body parameters must be of type 'text'"
                    )
        return v


class TemplateMessageStatus(BaseModel):
    """Template message delivery status."""

    template_name: str = Field(..., description="Template name")
    status: str = Field(..., description="Template status")
    language: str = Field(..., description="Template language")
    category: str | None = Field(None, description="Template category")
    components: list[dict] | None = Field(None, description="Template components")


class TemplateValidationResult(BaseModel):
    """Template validation result."""

    valid: bool = Field(..., description="Whether template is valid")
    template_name: str = Field(..., description="Template name")
    errors: list[str] | None = Field(None, description="Validation errors")
    warnings: list[str] | None = Field(None, description="Validation warnings")
