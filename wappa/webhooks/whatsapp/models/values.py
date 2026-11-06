"""Webhook ``value`` models: the messages value and the field-specific values."""

from __future__ import annotations

from typing import Any, ClassVar, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from wappa.webhooks.whatsapp.models.base import WhatsAppContact, WhatsAppMetadata
from wappa.webhooks.whatsapp.models.system import UserActionEntry


class WebhookValue(BaseModel):
    """
    The core value object containing webhook payload data.

    This is where the actual message or status information is contained.
    Either 'messages' OR 'statuses' will be present, never both.
    """

    model_config = ConfigDict(extra="allow", str_strip_whitespace=True)

    messaging_product: Literal["whatsapp"] = Field(
        ..., description="Always 'whatsapp' for WhatsApp Business webhooks"
    )
    metadata: WhatsAppMetadata = Field(
        ..., description="Business phone number metadata"
    )
    contacts: list[WhatsAppContact] | None = Field(
        None, description="Contact information (present for incoming messages)"
    )
    messages: list[dict[str, Any]] | None = Field(
        None,
        description="Incoming messages array (parsed by specific message type schemas)",
    )
    statuses: list[dict[str, Any]] | None = Field(
        None, description="Outgoing message status array (parsed by status schemas)"
    )
    errors: list[dict[str, Any]] | None = Field(
        None, description="System, app, or account level errors"
    )
    user_preferences: list[dict[str, Any]] | None = Field(
        None, description="User marketing preference changes"
    )
    user_id_update: list[dict[str, Any]] | None = Field(
        None, description="User BSUID change notifications"
    )
    groups: list[dict[str, Any]] | None = Field(
        None, description="WhatsApp group participant updates"
    )
    user_actions: list[UserActionEntry] | None = Field(
        None,
        description=(
            "User interaction events (e.g. marketing message link clicks). "
            "Delivered on the 'messages' field without messages or contacts."
        ),
    )

    @model_validator(mode="after")
    def validate_webhook_content(self) -> Self:
        """Ensure webhook has at least one content array."""
        has_messages = self.messages is not None and len(self.messages) > 0
        has_statuses = self.statuses is not None and len(self.statuses) > 0
        has_errors = self.errors is not None and len(self.errors) > 0
        has_user_prefs = (
            self.user_preferences is not None and len(self.user_preferences) > 0
        )
        has_user_id_update = (
            self.user_id_update is not None and len(self.user_id_update) > 0
        )
        has_groups = self.groups is not None and len(self.groups) > 0
        has_user_actions = self.user_actions is not None and len(self.user_actions) > 0

        if not (
            has_messages
            or has_statuses
            or has_errors
            or has_user_prefs
            or has_user_id_update
            or has_groups
            or has_user_actions
        ):
            raise ValueError(
                "Webhook must contain messages, statuses, errors, user preferences, "
                "user ID updates, groups, or user actions"
            )

        # Messages and statuses should not be present together
        if has_messages and has_statuses:
            raise ValueError("Webhook cannot contain both messages and statuses")

        # User-authored messages carry contacts. Meta system messages do not.
        has_only_system_messages = has_messages and all(
            message.get("type") == "system" for message in self.messages or []
        )
        if (
            has_messages
            and not has_only_system_messages
            and (self.contacts is None or len(self.contacts) == 0)
        ):
            raise ValueError("Incoming messages must include contact information")

        return self

    @field_validator(
        "messages",
        "statuses",
        "errors",
        "user_preferences",
        "user_id_update",
        "groups",
        "user_actions",
    )
    @classmethod
    def validate_arrays_not_empty(cls, v: list[Any] | None) -> list[Any] | None:
        """Validate that arrays are not empty if present."""
        if v is not None and len(v) == 0:
            return None  # Convert empty arrays to None for cleaner logic
        return v


class CustomWebhookValue(BaseModel):
    """
    Permissive value container for app-registered custom webhook fields.

    Built-in fields use strict, field-appropriate models. App-registered fields
    (e.g. ``message_template_status_update``) use this permissive model —
    the framework never imposes a schema; the app's registered parser does
    that downstream in the processor.
    """

    model_config = ConfigDict(extra="allow", str_strip_whitespace=True)
    # Not drift: the Host's parser owns this schema (schema_drift.py).
    drift_exempt: ClassVar[bool] = True


class AccountWebhookValue(BaseModel):
    """Strict ``value`` model for account-level coexistence webhooks.

    Covers both ``account_offboarded`` and ``account_reconnected``. Their value
    is a flat, WABA-scoped object (no ``metadata``, no sub-array) rather than the
    phone-scoped :class:`WebhookValue` shape, so they get their own typed model
    instead of being forced through the permissive ``CustomWebhookValue`` path.

    Unknown keys are kept and reported as schema drift (ADR-0023), like every
    other Meta input model.
    """

    model_config = ConfigDict(extra="allow", str_strip_whitespace=True)

    waba_id: str = Field(..., description="WhatsApp Business Account ID (required)")
    timestamp: int = Field(..., description="Unix timestamp of the event")
    reason: str | None = Field(
        None,
        description="Why offboarding happened, e.g. USER_INITIATED (account_offboarded)",
    )
    phone_number_id: str | None = Field(
        None, description="Phone number ID that reconnected (account_reconnected)"
    )


class BusinessUsernameWebhookValue(BaseModel):
    """Strict value for Meta's business_username_updates field."""

    model_config = ConfigDict(extra="allow", str_strip_whitespace=True)

    display_phone_number: str = Field(..., description="Business display number")
    username: str | None = Field(None, description="Current business username")
    status: Literal["approved", "deleted", "reserved"]
