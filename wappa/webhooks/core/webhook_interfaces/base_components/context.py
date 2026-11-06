"""Universal interaction-context components: business, forward, entry point and conversation."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


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


class EntryPointKind(StrEnum):
    """The surface that brought a User into a conversation."""

    AD = "ad"
    """A paid ad (Click-to-WhatsApp, Instagram ad)."""
    POST = "post"
    """An organic post (WhatsApp ``source_type=post``)."""
    LINK = "link"
    """A conversation link carrying a Host ``ref`` (ig.me, shortlink)."""
    OTHER = "other"
    """An entry point the Platform named that Wappa does not classify yet."""


class EntryReferral(BaseModel):
    """Entry-point attribution, one model on every Platform (ADR-0025).

    Answers "what brought this User here": WhatsApp Click-to-WhatsApp ``referral``
    and Instagram ad / link ``referral`` fill the same fields; a field the
    Platform does not send stays ``None``.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: EntryPointKind
    source: str | None = Field(
        default=None, description="The Platform's own source label (ad, ADS, …)"
    )
    ref: str | None = Field(
        default=None, description="Host-defined ref carried by a link or ad"
    )
    ad_id: str | None = None
    post_id: str | None = None
    product_id: str | None = None
    source_url: str | None = None
    headline: str | None = Field(default=None, description="Ad headline or title")
    body: str | None = Field(default=None, description="Ad primary text")
    media_type: str | None = None
    image_url: str | None = None
    video_url: str | None = None
    thumbnail_url: str | None = None
    click_id: str | None = Field(
        default=None, description="Ad click ID (WhatsApp ctwa_clid)"
    )
    welcome_message_text: str | None = None

    @property
    def is_ad(self) -> bool:
        return self.kind is EntryPointKind.AD


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
    pricing_subtype: str | None = Field(
        default=None,
        description="Pricing subtype as sent by the platform (e.g. paid_exempt)",
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
        return datetime.now(UTC) > self.expiration_timestamp
