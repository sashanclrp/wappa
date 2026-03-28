"""
WhatsApp system event models for user_preferences and user_id_update webhooks.

These are platform-specific parsing models for the new webhook field types
introduced alongside the BSUID system. They are parsed by the processor
and transformed into the universal SystemWebhook interface.
"""

from pydantic import BaseModel, ConfigDict, Field


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
