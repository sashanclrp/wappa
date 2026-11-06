"""
Universal base components for platform-agnostic webhook interfaces.

These components provide the building blocks for all universal webhook types.
Every Platform adapter fills the fields it has evidence for; identity fields a
Platform does not supply (phone number, BSUID, username) stay ``None``.
"""

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from wappa.domain.messaging_targets import DeliveryAddresses


class InboxBase(BaseModel):
    """
    Universal inbox identification component.

    Represents the business inbox that messages are sent to/from on any
    Platform.
    """

    model_config = ConfigDict(
        extra="forbid", str_strip_whitespace=True, validate_assignment=True
    )

    # Core inbox identification
    inbox_id: str = Field(description="Unique inbox ID (e.g. business phone number ID)")
    display_address: str | None = Field(
        description="Business display address (e.g. phone number)"
    )

    # Platform-specific account ID (WhatsApp Business Account ID, Teams tenant ID, etc.)
    platform_account_id: str = Field(description="Platform-specific account identifier")

    def get_inbox_key(self) -> str:
        """Get unique inbox key for this business account."""
        # For WhatsApp, the inbox_id IS the inbox identifier
        # For other platforms, they might use platform_account_id, but for consistency
        # we use inbox_id as the primary inbox key
        return self.inbox_id


class UserBase(BaseModel):
    """
    Universal user/contact identification component.

    Represents the end user sending messages to the business. Identity
    evidence is Platform-optional: each adapter sets what its Platform
    supplies and leaves the rest ``None``. A User is identified either by
    address evidence (``phone_number``, ``bsuid``, ``parent_bsuid``; the
    field names follow WhatsApp, ADR-0028) or by a native ``platform_user_id``,
    never both.

    Field vs Property Pattern:
    - phone_number: Raw phone-number address from the webhook
    - bsuid: Raw business-scoped user ID address from the webhook
    - user_id: @property returning platform_user_id, else bsuid, else phone_number
    """

    model_config = ConfigDict(
        extra="forbid", str_strip_whitespace=True, validate_assignment=True
    )

    # Core user identification (raw fields from webhook)
    phone_number: str = Field(
        default="",
        description="User's phone number (may be empty for username-only users)",
    )

    platform_user_id: str | None = Field(
        default=None,
        min_length=1,
        description=(
            "Native Inbox-scoped User ID, set when the Platform identifies the "
            "User by its own ID instead of address evidence"
        ),
    )

    # BSUID support (v24.0+)
    bsuid: str | None = Field(
        default=None,
        description="Business Scoped User ID - stable identifier across phone changes",
    )
    parent_bsuid: str | None = Field(
        default=None,
        description="Parent Business Scoped User ID when enabled for the portfolio",
    )
    username: str | None = Field(
        default=None,
        description="Platform username",
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
        description="Identity key hash for security validation, when the Platform sends one",
    )

    @model_validator(mode="after")
    def _identity_evidence(self) -> "UserBase":
        if self.platform_user_id is not None and (
            self.phone_number or self.bsuid or self.parent_bsuid
        ):
            raise ValueError(
                "A native platform_user_id must not be mixed with address evidence "
                "(phone_number, bsuid, parent_bsuid)"
            )
        return self

    @property
    def user_id(self) -> str:
        """
        Get the recommended user identifier.

        Returns:
            The native ``platform_user_id`` when set, else the BSUID, else the
            phone number.
        """
        if self.platform_user_id and self.platform_user_id.strip():
            return self.platform_user_id.strip()
        if self.bsuid and self.bsuid.strip():
            return self.bsuid.strip()
        if self.phone_number and self.phone_number.strip():
            return self.phone_number.strip()
        return ""

    def delivery_addresses(self) -> DeliveryAddresses:
        """Every address this webhook proved for the User (ADR-0022).

        WhatsApp: BSUID and phone (``wa_id``); the Parent BSUID is identity
        evidence, not a fallback. Instagram: the scoped ID. The WhatsApp
        adapter decides the order and when to fall back.
        """
        if self.platform_user_id and self.platform_user_id.strip():
            return DeliveryAddresses.of(self.platform_user_id)
        return DeliveryAddresses.of(self.bsuid, self.phone_number)

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
        """Get unique user key for this contact (prefers phone_number, falls back to BSUID)."""
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


class GroupParticipant(BaseModel):
    """A participant named by a group membership event."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    input: str | None = None
    wa_id: str | None = None
    user_id: str | None = None
    parent_user_id: str | None = None
    username: str | None = None


class GroupUpdate(BaseModel):
    """A group membership change (WhatsApp ``group_participants_update``)."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    group_id: str
    event_type: str
    timestamp: int
    request_id: str | None = None
    initiated_by: str | None = None
    reason: str | None = None
    join_request_id: str | None = None
    added: tuple[GroupParticipant, ...] = ()
    removed: tuple[GroupParticipant, ...] = ()


class UserAction(BaseModel):
    """A User interaction outside a message (e.g. a marketing link click)."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    action_type: str
    timestamp: int
    click_component: str | None = None
    click_id: str | None = None
    tracking_token: str | None = None
    product_id: str | None = None
    client_user_agent: str | None = None


class ContactSync(BaseModel):
    """A contact added, edited or removed in the Platform's own business app
    (WhatsApp Coexistence ``smb_app_state_sync``)."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    action: str
    timestamp: int
    full_name: str
    first_name: str
    phone_number: str | None = None
    user_id: str
    parent_user_id: str | None = None
    username: str | None = None


class SystemEventDetail(BaseModel):
    """
    Universal system event detail component.

    Platform-agnostic representation of system-level account/identity events.
    Covers phone number changes, BSUID updates, and marketing preferences.
    """

    model_config = ConfigDict(
        extra="forbid", str_strip_whitespace=True, validate_assignment=True
    )

    platform_event: dict | None = Field(
        default=None,
        description=(
            "Native evidence for UNSUPPORTED_EVENT only: an event Wappa has no "
            "contract for yet. Every supported event is typed (ADR-0025)."
        ),
    )

    # User identification (present in most system events)
    wa_id: str | None = Field(
        default=None,
        description="User's phone number (may be omitted for username-only users)",
    )
    user_id: str | None = Field(default=None, description="User's BSUID")
    parent_user_id: str | None = Field(
        default=None, description="User's parent BSUID (if parent BSUIDs enabled)"
    )

    # BSUID change fields (for user_id_update and system message user_changed_user_id)
    previous_user_id: str | None = Field(
        default=None, description="Previous BSUID before change"
    )
    current_user_id: str | None = Field(
        default=None, description="Current BSUID after change"
    )
    previous_parent_user_id: str | None = Field(
        default=None, description="Previous parent BSUID before change"
    )
    current_parent_user_id: str | None = Field(
        default=None, description="Current parent BSUID after change"
    )

    # Phone number change fields
    old_phone_number: str | None = Field(
        default=None, description="Old phone number before change"
    )
    new_phone_number: str | None = Field(
        default=None, description="New phone number after change"
    )

    # Human-readable description
    body: str | None = Field(default=None, description="System message body text")
    detail: str | None = Field(
        default=None, description="Human-readable event description"
    )

    # Marketing preference fields
    category: str | None = Field(
        default=None, description="Preference category (e.g., 'marketing_messages')"
    )
    preference_value: str | None = Field(
        default=None, description="Preference value (e.g., opt-in/opt-out)"
    )

    # Coexistence account-level fields (account_offboarded / account_reconnected).
    # WABA-scoped, not user-scoped.
    waba_id: str | None = Field(
        default=None, description="WhatsApp Business Account ID for account events"
    )
    phone_number_id: str | None = Field(
        default=None,
        description="Phone number ID that reconnected (account_reconnected)",
    )
    reason: str | None = Field(
        default=None,
        description="Reason for an account status change (account_offboarded)",
    )

    # Business username updates (Inbox-scoped, no User).
    username: str | None = Field(default=None, description="Business username")
    username_status: str | None = Field(
        default=None,
        description="Business username status: approved, reserved, or deleted",
    )
    display_phone_number: str | None = Field(
        default=None,
        description="Business display phone number from the username event",
    )

    # Group participant updates.
    group_id: str | None = Field(default=None, description="WhatsApp group ID")
    group_event_type: str | None = Field(
        default=None, description="Meta group participant event type"
    )
    group_update: GroupUpdate | None = Field(
        default=None, description="Typed group membership change"
    )
    contact_sync: ContactSync | None = Field(
        default=None, description="Business-app contact change (Coexistence)"
    )
    entry_referral: EntryReferral | None = Field(
        default=None, description="Standalone entry-point referral (no message)"
    )

    # User interaction events (marketing message link clicks and future actions).
    action_type: str | None = Field(
        default=None,
        description="Provider action name, e.g. 'marketing_messages_link_click'",
    )
    user_action: UserAction | None = Field(
        default=None, description="Typed User interaction event"
    )
