"""The top-level WhatsApp webhook model."""

from __future__ import annotations

from typing import Any, Literal, cast

from pydantic import (
    ConfigDict,
    Field,
    field_validator,
)

from wappa.schemas.core.types import PlatformType, WebhookType
from wappa.webhooks.core.base_webhook import (
    BaseContact,
    BaseWebhook,
    BaseWebhookMetadata,
)
from wappa.webhooks.whatsapp.fields import (
    _DIRECT_SYSTEM_EVENT_FIELDS,
    BUILTIN_WEBHOOK_FIELDS,
    COEXISTENCE_EVENT_FIELDS,
)
from wappa.webhooks.whatsapp.models.base import WhatsAppContact
from wappa.webhooks.whatsapp.models.calls import CallsWebhookValue
from wappa.webhooks.whatsapp.models.coexistence import (
    CoexistenceWebhookValue,
    HistoryWebhookValue,
    SmbAppStateSyncWebhookValue,
    SmbMessageEchoesWebhookValue,
)
from wappa.webhooks.whatsapp.models.contact_adapter import WhatsAppContactAdapter
from wappa.webhooks.whatsapp.models.entry import WebhookEntry
from wappa.webhooks.whatsapp.models.metadata import WhatsAppWebhookMetadata
from wappa.webhooks.whatsapp.models.system import UserActionEntry
from wappa.webhooks.whatsapp.models.values import (
    AccountWebhookValue,
    BusinessUsernameWebhookValue,
)


class WhatsAppWebhook(BaseWebhook):
    """
    Top-level WhatsApp Business Platform webhook model.

    This is the root model for all WhatsApp webhook payloads.
    Use this model to parse incoming webhook requests.
    """

    model_config = ConfigDict(
        extra="allow", str_strip_whitespace=True, validate_assignment=True
    )

    object: Literal["whatsapp_business_account"] = Field(
        ..., description="Always 'whatsapp_business_account' for WhatsApp webhooks"
    )
    entry: list[WebhookEntry] = Field(
        ..., description="Array of webhook entries (typically contains one entry)"
    )

    @field_validator("entry")
    @classmethod
    def validate_entry_not_empty(cls, v: list[WebhookEntry]) -> list[WebhookEntry]:
        """Validate entry array is not empty."""
        if not v or len(v) == 0:
            raise ValueError("Entry array cannot be empty")
        return v

    @property
    def is_system_event(self) -> bool:
        """
        Check if this webhook is a platform-level system event.

        Returns True for:
        - field: "user_preferences" webhooks
        - field: "user_id_update" webhooks
        - field: "messages" where ALL messages have type: "system"
        - field: "messages" carrying only user_actions (no messages)
        """
        if not self.entry:
            return False

        for entry in self.entry:
            for change in entry.changes:
                # Direct system event fields
                if change.field in _DIRECT_SYSTEM_EVENT_FIELDS:
                    return True
                messages = getattr(change.value, "messages", None)
                # User action events ride the messages field with no messages.
                if not messages and getattr(change.value, "user_actions", None):
                    return True
                # System messages within the messages field
                if (
                    change.field == "messages"
                    and messages
                    and all(msg.get("type") == "system" for msg in messages)
                ):
                    return True
        return False

    @property
    def is_user_action(self) -> bool:
        """Check if this webhook carries user interaction events only."""
        for entry in self.entry:
            for change in entry.changes:
                if getattr(change.value, "messages", None):
                    continue
                if getattr(change.value, "user_actions", None):
                    return True
        return False

    @property
    def is_incoming_message(self) -> bool:
        """Check if this webhook contains incoming messages."""
        if not self.entry:
            return False

        for entry in self.entry:
            for change in entry.changes:
                if getattr(change.value, "messages", None) is not None:
                    return True
        return False

    @property
    def is_status_update(self) -> bool:
        """Check if this webhook contains message status updates."""
        if not self.entry:
            return False

        for entry in self.entry:
            for change in entry.changes:
                if getattr(change.value, "statuses", None) is not None:
                    return True
        return False

    @property
    def is_call_event(self) -> bool:
        """Check if this webhook carries a native WhatsApp Calling event."""
        return any(
            change.field == "calls" for entry in self.entry for change in entry.changes
        )

    @property
    def has_errors(self) -> bool:
        """Check if this webhook contains errors."""
        if not self.entry:
            return False

        for entry in self.entry:
            for change in entry.changes:
                if getattr(change.value, "errors", None) is not None:
                    return True
        return False

    @property
    def is_custom_field(self) -> bool:
        """Check if this webhook is for an app-registered custom field."""
        if not self.entry:
            return False
        for entry in self.entry:
            for change in entry.changes:
                if change.field not in BUILTIN_WEBHOOK_FIELDS:
                    return True
        return False

    def get_business_account_id(self) -> str:
        """Get the WhatsApp Business Account ID from the first entry."""
        if not self.entry:
            raise ValueError("No entry data available")
        return self.entry[0].id

    def get_phone_number_id(self) -> str:
        """Get the business phone number ID from the first entry.

        Returns an empty string when the webhook is for a custom registered
        field whose ``value`` does not include phone-number metadata
        (e.g. ``message_template_status_update``).
        """
        if not self.entry:
            raise ValueError("No entry data available")
        metadata = getattr(self.entry[0].changes[0].value, "metadata", None)
        if metadata is None:
            return ""
        return cast(str, metadata.phone_number_id)

    def get_display_phone_number(self) -> str:
        """Get the business display phone number from the first entry.

        Empty string when the value does not carry metadata (custom fields).
        """
        if not self.entry:
            raise ValueError("No entry data available")
        metadata = getattr(self.entry[0].changes[0].value, "metadata", None)
        if metadata is None:
            return ""
        return cast(str, metadata.display_phone_number)

    def get_raw_user_preferences(self) -> list[dict[str, Any]]:
        """
        Get raw user_preferences data for parsing.

        Returns empty list if no user_preferences present.
        """
        items = []
        for entry in self.entry:
            for change in entry.changes:
                prefs = getattr(change.value, "user_preferences", None)
                if prefs:
                    items.extend(prefs)
        return items

    def get_raw_user_id_updates(self) -> list[dict[str, Any]]:
        """
        Get raw user_id_update data for parsing.

        Returns empty list if no user_id_update present.
        """
        items = []
        for entry in self.entry:
            for change in entry.changes:
                updates = getattr(change.value, "user_id_update", None)
                if updates:
                    items.extend(updates)
        return items

    def get_raw_group_updates(self) -> list[dict[str, Any]]:
        """Return group participant update entries."""
        items: list[dict[str, Any]] = []
        for entry in self.entry:
            for change in entry.changes:
                groups = getattr(change.value, "groups", None)
                if groups:
                    items.extend(groups)
        return items

    def get_user_actions(self) -> list[UserActionEntry]:
        """Return typed user interaction events, empty when none are present."""
        actions: list[UserActionEntry] = []
        for entry in self.entry:
            for change in entry.changes:
                value_actions = getattr(change.value, "user_actions", None)
                if value_actions:
                    actions.extend(value_actions)
        return actions

    def get_account_event(self, field_name: str) -> AccountWebhookValue | None:
        """Return the typed ``value`` of an account-level coexistence event.

        Account events (``account_offboarded``/``account_reconnected``) carry
        their fields flat in the value, already validated into a strict
        :class:`AccountWebhookValue` at parse time. Returns the typed value, or
        ``None`` if the field is absent.
        """
        for entry in self.entry:
            for change in entry.changes:
                if change.field == field_name and isinstance(
                    change.value, AccountWebhookValue
                ):
                    return change.value
        return None

    def get_business_username_event(self) -> BusinessUsernameWebhookValue | None:
        """Return the typed business username update value, when present."""
        for entry in self.entry:
            for change in entry.changes:
                if change.field == "business_username_updates" and isinstance(
                    change.value, BusinessUsernameWebhookValue
                ):
                    return change.value
        return None

    def get_call_event(self) -> CallsWebhookValue | None:
        """Return the typed calls value, when present."""
        for entry in self.entry:
            for change in entry.changes:
                if change.field == "calls" and isinstance(
                    change.value, CallsWebhookValue
                ):
                    return change.value
        return None

    def get_coexistence_event(self) -> CoexistenceWebhookValue | None:
        """Return a typed history, SMB echo, or app-state value."""
        for entry in self.entry:
            for change in entry.changes:
                if change.field in COEXISTENCE_EVENT_FIELDS and isinstance(
                    change.value,
                    (
                        HistoryWebhookValue,
                        SmbMessageEchoesWebhookValue,
                        SmbAppStateSyncWebhookValue,
                    ),
                ):
                    return change.value
        return None

    def get_raw_messages(self) -> list[dict[str, Any]]:
        """
        Get raw message data for parsing with specific message type schemas.

        Returns empty list if no messages present.
        """
        messages: list[dict[str, Any]] = []
        for entry in self.entry:
            for change in entry.changes:
                value_messages = getattr(change.value, "messages", None)
                if value_messages:
                    messages.extend(value_messages)
        return messages

    def get_raw_statuses(self) -> list[dict[str, Any]]:
        """
        Get raw status data for parsing with status schemas.

        Returns empty list if no statuses present.
        """
        statuses: list[dict[str, Any]] = []
        for entry in self.entry:
            for change in entry.changes:
                value_statuses = getattr(change.value, "statuses", None)
                if value_statuses:
                    statuses.extend(value_statuses)
        return statuses

    def get_contacts(self) -> list[BaseContact]:
        """
        Get contact information from the webhook with universal interface.

        Returns empty list if no contacts present.
        """
        contacts: list[BaseContact] = []
        for entry in self.entry:
            for change in entry.changes:
                value_contacts = getattr(change.value, "contacts", None)
                if value_contacts:
                    contacts.extend(
                        WhatsAppContactAdapter(contact) for contact in value_contacts
                    )
        return contacts

    def get_whatsapp_contacts(self) -> list[WhatsAppContact]:
        """
        Get original WhatsApp contact objects (platform-specific).

        Returns empty list if no contacts present.
        """
        contacts: list[WhatsAppContact] = []
        for entry in self.entry:
            for change in entry.changes:
                value_contacts = getattr(change.value, "contacts", None)
                if value_contacts:
                    contacts.extend(value_contacts)
        return contacts

    # Implement abstract methods from BaseWebhook

    @property
    def platform(self) -> PlatformType:
        """Get the platform type this webhook came from."""
        return PlatformType.WHATSAPP

    @property
    def webhook_type(self) -> WebhookType:
        """Get the type of webhook (messages, status updates, errors, etc.)."""
        # System events must be checked BEFORE is_incoming_message to intercept
        # system messages (type=="system") from the messages field
        if self.is_system_event:
            return WebhookType.SYSTEM_EVENTS
        elif self.is_incoming_message:
            return WebhookType.INCOMING_MESSAGES
        elif self.is_status_update:
            return WebhookType.STATUS_UPDATES
        elif self.has_errors:
            return WebhookType.ERRORS
        else:
            return WebhookType.ERRORS  # Default fallback

    @property
    def business_id(self) -> str:
        """Get the business/account identifier."""
        return self.get_business_account_id()

    @property
    def source_id(self) -> str:
        """Get the webhook source identifier (phone number ID)."""
        return self.get_phone_number_id()

    def get_metadata(self) -> BaseWebhookMetadata:
        """Get webhook metadata with universal interface."""
        if not self.entry:
            raise ValueError("No entry data available")

        whatsapp_metadata = getattr(self.entry[0].changes[0].value, "metadata", None)
        if whatsapp_metadata is None:
            raise ValueError("Webhook value does not contain WhatsApp metadata")
        return WhatsAppWebhookMetadata(whatsapp_metadata)

    def to_universal_dict(self) -> dict[str, Any]:
        """Convert webhook to platform-agnostic dictionary representation."""
        return {
            "platform": self.platform.value,
            "webhook_type": self.webhook_type.value,
            "business_id": self.business_id,
            "source_id": self.source_id,
            "received_at": self.received_at.isoformat(),
            "has_messages": self.is_incoming_message,
            "has_statuses": self.is_status_update,
            "has_errors": self.has_errors,
            "message_count": len(self.get_raw_messages()),
            "status_count": len(self.get_raw_statuses()),
            "contact_count": len(self.get_contacts()),
            "metadata": self.get_metadata().to_universal_dict(),
            "whatsapp_data": {
                "object": self.object,
                "business_account_id": self.business_id,
                "phone_number_id": self.source_id,
                "display_phone_number": self.get_display_phone_number(),
            },
        }

    def get_processing_context(self) -> dict[str, Any]:
        """Get context information needed for message processing."""
        return {
            "platform": self.platform.value,
            "business_id": self.business_id,
            "source_id": self.source_id,
            "webhook_type": self.webhook_type.value,
            "display_phone_number": self.get_display_phone_number(),
            "webhook_id": self.get_webhook_id(),
            "received_at": self.received_at.isoformat(),
        }

    @classmethod
    def from_platform_payload(
        cls, payload: dict[str, Any], **kwargs: Any
    ) -> WhatsAppWebhook:
        """
        Create webhook instance from WhatsApp-specific payload.

        Args:
            payload: Raw webhook payload from WhatsApp
            **kwargs: Additional WhatsApp-specific parameters

        Returns:
            Validated WhatsApp webhook instance

        Raises:
            ValidationError: If payload is invalid
        """
        return cls.model_validate(payload)
