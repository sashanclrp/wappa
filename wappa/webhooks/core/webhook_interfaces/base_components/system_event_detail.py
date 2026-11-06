"""Universal system event detail and the group, contact-sync and user-action details it carries."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from wappa.webhooks.core.webhook_interfaces.base_components.context import EntryReferral


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
