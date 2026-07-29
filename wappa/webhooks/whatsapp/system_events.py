"""
WhatsApp system event models for user_preferences and user_id_update webhooks.

These are platform-specific parsing models for the new webhook field types
introduced alongside the BSUID system. They are parsed by the processor
and transformed into the universal SystemWebhook interface.
"""

from pydantic import BaseModel, ConfigDict, Field, model_validator

from wappa.core.logging.logger import get_logger

logger = get_logger(__name__)


def _warn_on_undocumented_fields(model: BaseModel, *, context: str) -> None:
    """Log a warning (not a 400) when a tolerant model receives unknown fields.

    ``extra="allow"`` keeps Meta's undocumented additions from becoming a
    sustained 400, but silently swallowing them means we'd never notice a new
    field exists until a host asks why data is missing. This surfaces it in
    logs instead, with the field names and the raw values Meta actually sent,
    so the contract can be updated deliberately.
    """
    extra = model.model_extra
    if extra:
        logger.warning(
            "WHATSAPP_WEBHOOK_UNDOCUMENTED_FIELDS context=%s fields=%s raw=%s",
            context,
            ",".join(extra.keys()),
            extra,
        )


class UserPreferenceEntry(BaseModel):
    """
    A single entry from the user_preferences webhook array.

    Represents a user's marketing preference change (opt-in/opt-out).
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    wa_id: str | None = Field(
        None,
        description="User's phone number (omitted if username feature enabled)",
    )
    user_id: str | None = Field(None, description="Business Scoped User ID (BSUID)")
    parent_user_id: str | None = Field(
        None, description="Parent BSUID (if parent BSUIDs enabled)"
    )
    detail: str = Field(..., description="Human-readable preference description")
    category: str = Field(
        ..., description="Preference category (e.g., 'marketing_messages')"
    )
    value: str = Field(..., description="Preference value (e.g., opt-in/opt-out)")
    timestamp: int = Field(..., description="Unix timestamp of the preference change")


class UserIdChange(BaseModel):
    """Object containing previous and current BSUID."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    previous: str = Field(..., description="User's old BSUID")
    current: str = Field(..., description="User's new BSUID")


class ParentUserIdChange(BaseModel):
    """Object containing previous and current parent BSUID."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    previous: str = Field(..., description="User's old parent BSUID")
    current: str = Field(..., description="User's new parent BSUID")


class UserIdUpdateEntry(BaseModel):
    """
    A single entry from the user_id_update webhook array.

    Represents a BSUID change notification for a WhatsApp user.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    wa_id: str | None = Field(
        None,
        description="User's phone number (omitted if username feature enabled)",
    )
    detail: str = Field(..., description="Human-readable description of the update")
    user_id: UserIdChange = Field(..., description="Previous and current BSUID")
    parent_user_id: ParentUserIdChange | None = Field(
        None,
        description="Previous and current parent BSUID (if parent BSUIDs enabled)",
    )
    timestamp: str = Field(..., description="Unix timestamp when the webhook was sent")


class GroupParticipantIdentity(BaseModel):
    """Participant identity used by Meta group membership events."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    input: str | None = None
    wa_id: str | None = None
    user_id: str | None = None
    parent_user_id: str | None = None
    username: str | None = None


class GroupParticipantsUpdateEntry(BaseModel):
    """One group_participants_update event."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    timestamp: int
    group_id: str
    type: str
    request_id: str | None = None
    initiated_by: str | None = None
    reason: str | None = None
    join_request_id: str | None = None
    wa_id: str | None = None
    user_id: str | None = None
    parent_user_id: str | None = None
    username: str | None = None
    removed_participants: list[GroupParticipantIdentity] | None = None
    added_participants: list[GroupParticipantIdentity] | None = None


class MarketingMessagesLinkClickData(BaseModel):
    """Payload of the ``marketing_messages_link_click`` user action.

    Delivered by Meta's Marketing Messages API when a user clicks the body or
    call-to-action of a marketing message.
    """

    # Meta ships new fields on this sub-object without announcing them (e.g.
    # ``client_user_agent`` appeared in production undocumented). ``extra="allow"``
    # keeps a genuinely new field from turning into a sustained 400, matching the
    # tolerance already applied to ``UserActionEntry`` above.
    model_config = ConfigDict(extra="allow", str_strip_whitespace=True)

    click_component: str | None = Field(
        None, description="Where the click happened: 'cta' or 'body'"
    )
    click_id: str | None = Field(
        None,
        description="Unique click identifier, also appended to the visited URL",
    )
    tracking_token: str | None = Field(
        None, description="Internal Meta token for processing and tracking"
    )
    product_id: str | None = Field(
        None, description="Product SKU ID when assigned in Ads Manager / Marketing API"
    )
    client_user_agent: str | None = Field(
        None, description="User agent of the client that performed the click, e.g. '(Android 14)'"
    )

    @model_validator(mode="after")
    def _warn_on_extra(self) -> "MarketingMessagesLinkClickData":
        _warn_on_undocumented_fields(self, context="marketing_messages_link_click_data")
        return self


class UserActionEntry(BaseModel):
    """One entry of the ``user_actions`` array on a ``messages`` webhook.

    Meta delivers user interaction events (currently marketing-message link
    clicks) on the ``messages`` field, in a ``value`` that carries no
    ``messages`` and no ``contacts`` — only ``metadata`` plus this array.

    Each entry is ``action_type`` + ``timestamp`` plus one action-specific
    ``<action_type>_data`` object. Meta ships new action types without
    announcing them, and the ones seen in production already carry undocumented
    sub-objects (e.g. device/agent descriptors). ``extra="allow"`` is therefore
    deliberate: an unknown action type must not turn into a sustained 400 that
    makes Meta throttle or disable the whole webhook. Strictness is kept one
    level up — ``WebhookValue`` still rejects unknown keys, so a genuinely new
    top-level field still surfaces as contract drift.
    """

    model_config = ConfigDict(extra="allow", str_strip_whitespace=True)

    action_type: str = Field(
        ..., description="Name of the action, e.g. 'marketing_messages_link_click'"
    )
    timestamp: int | str = Field(
        ..., description="Unix timestamp of when the action happened"
    )
    marketing_messages_link_click_data: MarketingMessagesLinkClickData | None = Field(
        None, description="Click details for 'marketing_messages_link_click'"
    )

    @property
    def timestamp_int(self) -> int:
        """Timestamp as an int, tolerating Meta's string-encoded form."""
        return int(self.timestamp)

    @model_validator(mode="after")
    def _warn_on_extra(self) -> "UserActionEntry":
        _warn_on_undocumented_fields(
            self, context=f"user_actions.action_type={self.action_type}"
        )
        return self


# NOTE: Coexistence account-level events (account_offboarded / account_reconnected)
# are modeled by ``AccountWebhookValue`` in ``webhook_container.py``, alongside the
# other strict change-value models. Their value is a flat change ``value`` (not a
# sub-array like the entries above), so it lives with the routing/union logic.
