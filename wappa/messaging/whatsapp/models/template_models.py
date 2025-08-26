"""
WhatsApp template message models.

Provides Pydantic v2 validation models for WhatsApp template operations:
- TextTemplateMessage: Text-only template messages
- MediaTemplateMessage: Template messages with media headers
- LocationTemplateMessage: Template messages with location headers

Based on WhatsApp Cloud API 2025 template message specifications.
"""

from enum import Enum

from pydantic import BaseModel, Field, field_validator


class TemplateType(str, Enum):
    """Template message types supported by WhatsApp."""

    TEXT = "text"
    MEDIA = "media"
    LOCATION = "location"


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
    template_type: TemplateType = Field(..., description="Type of template message")


class TextTemplateMessage(BaseTemplateMessage):
    """Text-only template message."""

    template_type: TemplateType = Field(
        default=TemplateType.TEXT, description="Template type"
    )
    body_parameters: list[TemplateParameter] | None = Field(
        None, max_length=10, description="Body parameters for text replacement"
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

    template_type: TemplateType = Field(
        default=TemplateType.MEDIA, description="Template type"
    )
    media_type: MediaType = Field(..., description="Media type for header")
    media_id: str | None = Field(None, min_length=1, description="Uploaded media ID")
    media_url: str | None = Field(None, pattern=r"^https?://", description="Media URL")
    body_parameters: list[TemplateParameter] | None = Field(
        None, max_length=10, description="Body parameters for text replacement"
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


class LocationTemplateMessage(BaseTemplateMessage):
    """Template message with location header."""

    template_type: TemplateType = Field(
        default=TemplateType.LOCATION, description="Template type"
    )
    latitude: str = Field(..., description="Location latitude as string")
    longitude: str = Field(..., description="Location longitude as string")
    name: str = Field(..., min_length=1, max_length=100, description="Location name")
    address: str = Field(
        ..., min_length=1, max_length=1000, description="Location address"
    )
    body_parameters: list[TemplateParameter] | None = Field(
        None, max_length=10, description="Body parameters for text replacement"
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
                raise ValueError("Latitude must be a valid number")
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
                raise ValueError("Longitude must be a valid number")
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
