"""
Universal base components for platform-agnostic webhook interfaces.

These components provide the building blocks for all universal webhook types.
They are designed based on WhatsApp's comprehensive webhook structure and
represent the "standard" that all messaging platforms should adapt to.
"""

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field


class TenantBase(BaseModel):
    """
    Universal business/tenant identification component.

    Represents the business account that messages are sent to/from.
    Based on WhatsApp's metadata structure but platform-agnostic.
    """

    model_config = ConfigDict(
        extra="forbid", str_strip_whitespace=True, validate_assignment=True
    )

    # Core tenant identification
    business_phone_number_id: str = Field(description="Unique business phone number ID")
    display_phone_number: str = Field(description="Business display phone number")

    # Platform-specific tenant ID (WhatsApp Business Account ID, Teams tenant ID, etc.)
    platform_tenant_id: str = Field(description="Platform-specific tenant identifier")

    def get_tenant_key(self) -> str:
        """Get unique tenant key for this business account."""
        # For WhatsApp, the business_phone_number_id IS the tenant identifier
        # For other platforms, they might use platform_tenant_id, but for consistency
        # we use business_phone_number_id as the primary tenant key
        return self.business_phone_number_id


class UserBase(BaseModel):
    """
    Universal user/contact identification component.

    Represents the end user sending messages to the business.
    Based on WhatsApp's contact structure but platform-agnostic.

    Field vs Property Pattern:
    - platform_user_id: Raw platform-specific ID field (WhatsApp wa_id, Teams user ID, etc.)
    - phone_number: Raw phone number field from webhook
    - bsuid: Raw BSUID field from webhook (v24.0+)
    - user_id: @property returning BSUID if available, else platform_user_id, else phone_number
    """

    model_config = ConfigDict(
        extra="forbid", str_strip_whitespace=True, validate_assignment=True
    )

    # Core user identification (raw fields from webhook)
    platform_user_id: str = Field(
        default="",
        description="Platform-specific user ID (WhatsApp wa_id, Teams user ID, etc.)",
    )
    phone_number: str = Field(
        default="",
        description="User's phone number (may be empty for username-only users)",
    )

    # BSUID support (v24.0+)
    bsuid: str | None = Field(
        default=None,
        description="Business Scoped User ID - stable identifier across phone changes",
    )
    username: str | None = Field(
        default=None,
        description="Platform username (e.g., WhatsApp username)",
    )
    country_code: str | None = Field(
        default=None,
        description="User's country code from username API",
    )

    # User profile information
    profile_name: str | None = Field(default=None, description="User's display name")

    # Security and identity
    identity_key_hash: str | None = Field(
        default=None,
        description="Identity key hash for security validation (WhatsApp feature)",
    )

    @property
    def user_id(self) -> str:
        """
        Get the recommended user identifier.

        Returns:
            BSUID if available, otherwise falls back to platform_user_id, then phone_number.
        """
        if self.bsuid and self.bsuid.strip():
            return self.bsuid.strip()
        if self.platform_user_id and self.platform_user_id.strip():
            return self.platform_user_id.strip()
        return self.phone_number

    @property
    def has_bsuid(self) -> bool:
        """Check if this user has a BSUID set."""
        return bool(self.bsuid and self.bsuid.strip())

    @property
    def has_phone_number(self) -> bool:
        """Check if this user has a phone number set."""
        return bool(self.phone_number and self.phone_number.strip())

    @property
    def has_username(self) -> bool:
        """Check if this user has a username set."""
        return bool(self.username and self.username.strip())

    def get_display_name(self) -> str:
        """Get user's display name or fallback to username/user_id."""
        if self.profile_name:
            return self.profile_name
        if self.username:
            return f"@{self.username}"
        return self.phone_number or self.user_id

    def get_user_key(self) -> str:
        """Get unique user key for this contact (uses BSUID if available)."""
        return self.user_id


class BusinessContextBase(BaseModel):
    """
    Universal business interaction context component.

    Represents context when users interact with business features like
    product catalogs, business buttons, etc. Based on WhatsApp's business
    features but designed to be universal.
    """

    model_config = ConfigDict(
        extra="forbid", str_strip_whitespace=True, validate_assignment=True
    )

    # Business message context
    contextual_message_id: str = Field(
        description="ID of the business message that triggered this interaction"
    )
    business_phone_number: str = Field(description="Business phone number from context")

    # Product catalog context (for e-commerce interactions)
    catalog_id: str | None = Field(default=None, description="Product catalog ID")
    product_retailer_id: str | None = Field(
        default=None, description="Product ID from catalog"
    )

    def has_product_context(self) -> bool:
        """Check if this interaction involves a product catalog."""
        return self.catalog_id is not None and self.product_retailer_id is not None


class ForwardContextBase(BaseModel):
    """
    Universal message forwarding context component.

    Represents information about forwarded messages. Based on WhatsApp's
    forwarding detection but designed to be universal.
    """

    model_config = ConfigDict(
        extra="forbid", str_strip_whitespace=True, validate_assignment=True
    )

    # Forwarding indicators
    is_forwarded: bool = Field(
        default=False, description="Whether the message was forwarded"
    )
    is_frequently_forwarded: bool = Field(
        default=False,
        description="Whether the message has been forwarded multiple times (>5)",
    )

    # Optional forwarding metadata
    forward_count: int | None = Field(
        default=None, description="Number of times forwarded (if known)"
    )
    original_sender: str | None = Field(
        default=None, description="Original sender ID (if available)"
    )


class AdReferralBase(BaseModel):
    """
    Universal advertisement referral context component.

    Represents information when users interact via advertisements.
    Based on WhatsApp's Click-to-WhatsApp ads but designed to be universal
    for all advertising platforms.
    """

    model_config = ConfigDict(
        extra="forbid", str_strip_whitespace=True, validate_assignment=True
    )

    # Core ad identification
    source_type: str = Field(
        description="Type of ad source (e.g., 'ad', 'social', 'search')"
    )
    source_id: str = Field(description="Advertisement ID")
    source_url: str = Field(description="Advertisement URL")

    # Ad content
    ad_body: str | None = Field(default=None, description="Advertisement primary text")
    ad_headline: str | None = Field(default=None, description="Advertisement headline")

    # Media content
    media_type: str | None = Field(
        default=None, description="Ad media type (image, video)"
    )
    image_url: str | None = Field(default=None, description="Ad image URL")
    video_url: str | None = Field(default=None, description="Ad video URL")
    thumbnail_url: str | None = Field(
        default=None, description="Ad video thumbnail URL"
    )

    # Tracking and attribution
    click_id: str | None = Field(default=None, description="Click tracking ID")

    # Welcome message (for chat ads)
    welcome_message_text: str | None = Field(
        default=None, description="Predefined welcome message from the ad"
    )

    def has_media(self) -> bool:
        """Check if this ad referral includes media content."""
        return self.image_url is not None or self.video_url is not None

    def is_video_ad(self) -> bool:
        """Check if this is a video advertisement."""
        return self.media_type == "video" and self.video_url is not None


class ConversationBase(BaseModel):
    """
    Universal conversation and billing context component.

    Represents conversation state and billing information. Based on WhatsApp's
    conversation-based pricing but designed to be universal for all platforms
    that may implement conversation tracking.
    """

    model_config = ConfigDict(
        extra="forbid", str_strip_whitespace=True, validate_assignment=True
    )

    # Conversation identification
    conversation_id: str = Field(description="Unique conversation identifier")
    expiration_timestamp: datetime | None = Field(
        default=None, description="When this conversation window expires"
    )

    # Conversation categorization
    category: str | None = Field(
        default=None,
        description="Conversation category (service, marketing, authentication, etc.)",
    )
    origin_type: str | None = Field(
        default=None,
        description="How this conversation was initiated (user, business, service, etc.)",
    )

    # Billing information
    is_billable: bool | None = Field(
        default=None, description="Whether this conversation is billable"
    )
    pricing_model: str | None = Field(
        default=None,
        description="Pricing model (CBP=conversation-based, PMP=per-message)",
    )
    pricing_category: str | None = Field(
        default=None,
        description="Pricing category/rate (service, marketing, authentication, etc.)",
    )
    pricing_type: str | None = Field(
        default=None,
        description="Pricing type (regular, free_customer_service, free_entry_point)",
    )

    def is_free_conversation(self) -> bool:
        """Check if this conversation is free (not billable)."""
        return self.is_billable is False or self.pricing_type in [
            "free_customer_service",
            "free_entry_point",
        ]

    def is_expired(self) -> bool:
        """Check if this conversation has expired."""
        if self.expiration_timestamp is None:
            return False
        return datetime.now(timezone.utc) > self.expiration_timestamp


class ErrorDetailBase(BaseModel):
    """
    Universal error detail component.

    Represents structured error information from messaging platforms.
    Based on WhatsApp's error structure but designed to be universal.
    """

    model_config = ConfigDict(
        extra="forbid", str_strip_whitespace=True, validate_assignment=True
    )

    # Core error identification
    error_code: int = Field(description="Numeric error code")
    error_title: str = Field(description="Human-readable error title")
    error_message: str = Field(description="Detailed error message")

    # Additional error context
    error_details: str | None = Field(
        default=None, description="Extended error details"
    )
    documentation_url: str | None = Field(
        default=None, description="URL to error code documentation"
    )

    # Error categorization
    error_type: str | None = Field(
        default=None, description="Type of error (system, validation, rate_limit, etc.)"
    )
    is_retryable: bool | None = Field(
        default=None, description="Whether this error condition can be retried"
    )

    # Timestamp
    occurred_at: datetime | None = Field(
        default=None, description="When this error occurred"
    )

    def is_temporary_error(self) -> bool:
        """Check if this is likely a temporary error that could be retried."""
        temporary_codes = [429, 500, 502, 503, 504]  # Rate limits and server errors
        return self.error_code in temporary_codes or self.is_retryable is True

    def get_error_summary(self) -> str:
        """Get a concise error summary for logging."""
        return f"Error {self.error_code}: {self.error_title}"
