"""
Base models for WhatsApp Business Platform webhooks.

This module contains common Pydantic models used across different WhatsApp
message types, including metadata, contact information, and context models.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class WhatsAppMetadata(BaseModel):
    """
    Business phone number metadata from WhatsApp webhooks.

    Present in all webhook payloads to identify the business phone number
    that received or sent the message.
    """

    model_config = ConfigDict(
        extra="forbid", str_strip_whitespace=True, validate_assignment=True
    )

    display_phone_number: str = Field(
        ..., description="Business display phone number (formatted for display)"
    )
    phone_number_id: str = Field(
        ..., description="Business phone number ID (WhatsApp internal identifier)"
    )

    @field_validator("display_phone_number")
    @classmethod
    def validate_display_phone_number(cls, v: str) -> str:
        """Validate display phone number format."""
        if not v or len(v) < 10:
            raise ValueError("Display phone number must be at least 10 characters")
        return v

    @field_validator("phone_number_id")
    @classmethod
    def validate_phone_number_id(cls, v: str) -> str:
        """Validate phone number ID format."""
        if not v or not v.isdigit():
            raise ValueError("Phone number ID must be numeric")
        return v


class ContactProfile(BaseModel):
    """User profile information from WhatsApp contact."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(..., description="WhatsApp user's display name")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate user name is not empty."""
        if not v.strip():
            raise ValueError("Contact name cannot be empty")
        return v.strip()


class WhatsAppContact(BaseModel):
    """
    Contact information for WhatsApp users.

    Present in incoming message webhooks to identify the sender.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    wa_id: str = Field(
        ..., description="WhatsApp user ID (may differ from phone number)"
    )
    profile: ContactProfile = Field(..., description="User profile information")
    identity_key_hash: str | None = Field(
        None, description="Identity key hash (only if identity change check enabled)"
    )

    @field_validator("wa_id")
    @classmethod
    def validate_wa_id(cls, v: str) -> str:
        """Validate WhatsApp ID format."""
        if not v or len(v) < 8:
            raise ValueError("WhatsApp ID must be at least 8 characters")
        return v


class ReferredProduct(BaseModel):
    """Product catalog reference for message business button context."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    catalog_id: str = Field(..., description="Product catalog ID")
    product_retailer_id: str = Field(..., description="Product retailer ID")

    @field_validator("catalog_id", "product_retailer_id")
    @classmethod
    def validate_ids(cls, v: str) -> str:
        """Validate IDs are not empty."""
        if not v.strip():
            raise ValueError("Product IDs cannot be empty")
        return v.strip()


class MessageContext(BaseModel):
    """
    Context information for WhatsApp messages.

    Used for replies, forwards, and message business button interactions.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    # For replies and message business buttons
    from_: str | None = Field(
        None, alias="from", description="Original message sender (for replies)"
    )
    id: str | None = Field(
        None, description="ID of the original message being replied to or referenced"
    )

    # For forwarded messages
    forwarded: bool | None = Field(
        None, description="True if forwarded 5 times or less"
    )
    frequently_forwarded: bool | None = Field(
        None, description="True if forwarded more than 5 times"
    )

    # For message business button context
    referred_product: ReferredProduct | None = Field(
        None, description="Product information for message business button"
    )

    @field_validator("id")
    @classmethod
    def validate_message_id(cls, v: str | None) -> str | None:
        """Validate message ID format if present."""
        if v is not None and not v.strip():
            raise ValueError("Message ID cannot be empty string")
        return v


class WelcomeMessage(BaseModel):
    """Welcome message for Click-to-WhatsApp ads."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    text: str = Field(..., description="Ad greeting text")


class AdReferral(BaseModel):
    """
    Click-to-WhatsApp ad referral information.

    Present when a user sends a message via a Click-to-WhatsApp ad.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    source_url: str = Field(..., description="Click-to-WhatsApp ad URL")
    source_id: str = Field(..., description="Click-to-WhatsApp ad ID")
    source_type: Literal["ad"] = Field(..., description="Source type (always 'ad')")
    body: str = Field(..., description="Ad primary text")
    headline: str = Field(..., description="Ad headline")
    media_type: Literal["image", "video"] = Field(..., description="Ad media type")

    # Media URLs (conditionally present based on media_type)
    image_url: str | None = Field(None, description="Ad image URL (only for image ads)")
    video_url: str | None = Field(None, description="Ad video URL (only for video ads)")
    thumbnail_url: str | None = Field(
        None, description="Ad video thumbnail URL (only for video ads)"
    )

    ctwa_clid: str = Field(..., description="Click-to-WhatsApp ad click ID")
    welcome_message: WelcomeMessage = Field(..., description="Ad greeting message")

    @field_validator("source_url", "image_url", "video_url", "thumbnail_url")
    @classmethod
    def validate_urls(cls, v: str | None) -> str | None:
        """Validate URL format if present."""
        if v is not None:
            if not v.strip():
                return None
            if not (v.startswith("http://") or v.startswith("https://")):
                raise ValueError("URLs must start with http:// or https://")
        return v

    @field_validator("source_id", "ctwa_clid")
    @classmethod
    def validate_ids(cls, v: str) -> str:
        """Validate required IDs are not empty."""
        if not v.strip():
            raise ValueError("Ad IDs cannot be empty")
        return v.strip()


class ConversationOrigin(BaseModel):
    """Conversation origin information for pricing."""

    model_config = ConfigDict(extra="forbid")

    type: Literal[
        "authentication",
        "authentication_international",
        "marketing",
        "marketing_lite",
        "referral_conversion",
        "service",
        "utility",
    ] = Field(..., description="Conversation category")


class Conversation(BaseModel):
    """Conversation information for message status."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str = Field(..., description="Conversation ID")
    expiration_timestamp: str | None = Field(
        None, description="Unix timestamp when conversation expires"
    )
    origin: ConversationOrigin = Field(..., description="Conversation origin")

    @field_validator("expiration_timestamp")
    @classmethod
    def validate_timestamp(cls, v: str | None) -> str | None:
        """Validate timestamp format if present."""
        if v is not None and not v.isdigit():
            raise ValueError("Timestamp must be numeric")
        return v


class Pricing(BaseModel):
    """Pricing information for message status."""

    model_config = ConfigDict(extra="forbid")

    billable: bool = Field(..., description="Whether message is billable")
    pricing_model: Literal["CBP", "PMP"] = Field(
        ..., description="Pricing model (CBP=conversation-based, PMP=per-message)"
    )
    type: Literal["regular", "free_customer_service", "free_entry_point"] | None = (
        Field(None, description="Pricing type (available from July 1, 2025)")
    )
    category: Literal[
        "authentication",
        "authentication-international",
        "marketing",
        "marketing_lite",
        "referral_conversion",
        "service",
        "utility",
    ] = Field(..., description="Pricing category")


class ErrorData(BaseModel):
    """Error details for failed messages."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    details: str = Field(..., description="Detailed error description")


class MessageError(BaseModel):
    """Error information for failed messages."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    code: int = Field(..., description="Error code")
    title: str = Field(..., description="Error title")
    message: str = Field(..., description="Error message")
    error_data: ErrorData = Field(..., description="Additional error details")
    href: str | None = Field(None, description="Link to error documentation (optional)")

    @field_validator("href")
    @classmethod
    def validate_href(cls, v: str | None) -> str | None:
        """Validate error documentation URL."""
        if v is not None and not v.startswith("https://"):
            raise ValueError("Error documentation URL must use HTTPS")
        return v
