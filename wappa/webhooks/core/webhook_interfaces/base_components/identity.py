"""Universal inbox and user identification components."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from wappa.domain.inbox.identity import InboxRef
from wappa.domain.messaging_targets import DeliveryAddresses
from wappa.domain.user_identity import UserIdentity


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
    def _identity_evidence(self) -> UserBase:
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
        addresses = DeliveryAddresses.of(self.bsuid, self.phone_number)
        return addresses.model_copy(
            update={
                "evidence": tuple(
                    value for value in (self.bsuid, self.parent_bsuid) if value
                )
            }
        )

    def identity(self, inbox_ref: InboxRef) -> UserIdentity:
        """Project known evidence within the Inbox that supplied it."""
        return UserIdentity(
            inbox_ref=inbox_ref,
            user_id=self.user_id,
            addresses=self.delivery_addresses(),
            platform_user_id=self.platform_user_id,
            phone_number=self.phone_number or None,
            bsuid=self.bsuid,
            parent_bsuid=self.parent_bsuid,
            username=self.username,
        )

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
