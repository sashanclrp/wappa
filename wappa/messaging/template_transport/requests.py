"""Template transport request values and their cross-field validation."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .values import (
    BsuidTemplateRecipient,
    TemplateAuthenticationMethod,
    TemplateCategory,
    TemplateMediaType,
    TemplateRoutingPolicy,
    TemplateTransportRecipient,
)


class TemplateTransportParameter(BaseModel):
    """One named or positional text substitution value."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["text"] = "text"
    text: str = Field(min_length=1, max_length=1024)
    parameter_name: str | None = Field(
        default=None,
        max_length=128,
        pattern=r"^[a-zA-Z][a-zA-Z0-9_]*$",
    )


class TemplateTransportMediaHeader(BaseModel):
    """Provider-facing media header selection."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    media_type: TemplateMediaType
    media_id: str | None = Field(default=None, min_length=1)
    media_url: str | None = Field(default=None, pattern=r"^https?://")

    @model_validator(mode="after")
    def validate_source(self) -> TemplateTransportMediaHeader:
        if bool(self.media_id) == bool(self.media_url):
            raise ValueError("Exactly one of media_id or media_url is required")
        return self


class TemplateTransportLocationHeader(BaseModel):
    """Provider-facing location header values."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    latitude: str
    longitude: str
    name: str = Field(min_length=1, max_length=100)
    address: str = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def validate_coordinates(self) -> TemplateTransportLocationHeader:
        try:
            latitude = float(self.latitude)
            longitude = float(self.longitude)
        except ValueError as exc:
            raise ValueError("Latitude and longitude must be valid numbers") from exc
        if not -90 <= latitude <= 90:
            raise ValueError("Latitude must be between -90 and 90 degrees")
        if not -180 <= longitude <= 180:
            raise ValueError("Longitude must be between -180 and 180 degrees")
        return self


class TemplateTransportRouting(BaseModel):
    """Provider endpoint routing options."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    policy: TemplateRoutingPolicy = TemplateRoutingPolicy.CATEGORY_DEFAULT


class _TemplateTransportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    recipient: TemplateTransportRecipient
    template_name: str = Field(min_length=1, max_length=512)
    category: TemplateCategory
    authentication_method: TemplateAuthenticationMethod | None = None
    authentication_button_index: int = Field(default=0, ge=0, le=9)
    language_code: str = Field(default="es", min_length=2, max_length=32)
    body_parameters: tuple[TemplateTransportParameter, ...] = Field(
        default=(), max_length=10
    )
    routing: TemplateTransportRouting = Field(default_factory=TemplateTransportRouting)

    @model_validator(mode="after")
    def validate_policy(self) -> _TemplateTransportRequest:
        if (
            self.category != TemplateCategory.MARKETING
            and self.routing.policy is not TemplateRoutingPolicy.CATEGORY_DEFAULT
        ):
            raise ValueError(
                "cloud_messages_fallback is only valid for marketing Templates"
            )
        if self.category is TemplateCategory.AUTHENTICATION:
            if self.authentication_method is None:
                raise ValueError(
                    "authentication_method is required for authentication Templates"
                )
            if isinstance(self.recipient, BsuidTemplateRecipient):
                raise ValueError(
                    "Authentication Templates cannot use a BSUID recipient"
                )
            # Meta's authentication body is the fixed preset
            # "{{1}} is your verification code", so exactly one positional
            # text parameter is legal. The same value fills the OTP button.
            if len(self.body_parameters) != 1:
                raise ValueError(
                    "Authentication Templates require exactly one body parameter "
                    f"carrying the code, got {len(self.body_parameters)}"
                )
            if self.body_parameters[0].parameter_name is not None:
                raise ValueError(
                    "Authentication Templates use the positional code placeholder "
                    "and cannot bind a named parameter"
                )
        else:
            if self.authentication_method is not None:
                raise ValueError(
                    "authentication_method is only valid for authentication Templates"
                )
            if self.authentication_button_index != 0:
                raise ValueError(
                    "authentication_button_index is only valid for authentication "
                    "Templates"
                )
        return self

    @property
    def authentication_code(self) -> str | None:
        """The OTP code this request puts in both the body and the button."""
        if self.category is not TemplateCategory.AUTHENTICATION:
            return None
        return self.body_parameters[0].text


class TextTemplateTransportRequest(_TemplateTransportRequest):
    kind: Literal["text"] = "text"


class MediaTemplateTransportRequest(_TemplateTransportRequest):
    kind: Literal["media"] = "media"
    media_header: TemplateTransportMediaHeader

    @model_validator(mode="after")
    def reject_authentication_header(self) -> MediaTemplateTransportRequest:
        if self.category is TemplateCategory.AUTHENTICATION:
            raise ValueError("Authentication Templates cannot carry a media header")
        return self


class LocationTemplateTransportRequest(_TemplateTransportRequest):
    kind: Literal["location"] = "location"
    location_header: TemplateTransportLocationHeader

    @model_validator(mode="after")
    def reject_authentication_header(self) -> LocationTemplateTransportRequest:
        if self.category is TemplateCategory.AUTHENTICATION:
            raise ValueError("Authentication Templates cannot carry a location header")
        return self


TemplateTransportRequest = Annotated[
    TextTemplateTransportRequest
    | MediaTemplateTransportRequest
    | LocationTemplateTransportRequest,
    Field(discriminator="kind"),
]
