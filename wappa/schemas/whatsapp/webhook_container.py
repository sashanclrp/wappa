"""
Main webhook container models for WhatsApp Business Platform.

This module contains the top-level webhook structure models that wrap
all WhatsApp message types and status updates.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from wappa.schemas.core.base_webhook import (
    BaseContact,
    BaseWebhook,
    BaseWebhookMetadata,
)
from wappa.schemas.core.types import PlatformType, WebhookType
from wappa.schemas.whatsapp.base_models import WhatsAppContact, WhatsAppMetadata


class WebhookValue(BaseModel):
    """
    The core value object containing webhook payload data.

    This is where the actual message or status information is contained.
    Either 'messages' OR 'statuses' will be present, never both.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

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

    @model_validator(mode="after")
    def validate_webhook_content(self):
        """Ensure webhook has either messages, statuses, or errors."""
        has_messages = self.messages is not None and len(self.messages) > 0
        has_statuses = self.statuses is not None and len(self.statuses) > 0
        has_errors = self.errors is not None and len(self.errors) > 0

        if not (has_messages or has_statuses or has_errors):
            raise ValueError(
                "Webhook must contain either messages, statuses, or errors"
            )

        # Messages and statuses should not be present together
        if has_messages and has_statuses:
            raise ValueError("Webhook cannot contain both messages and statuses")

        # If we have messages, we should have contacts
        if has_messages and (self.contacts is None or len(self.contacts) == 0):
            raise ValueError("Incoming messages must include contact information")

        return self

    @field_validator("messages", "statuses", "errors")
    @classmethod
    def validate_arrays_not_empty(cls, v: list[dict] | None) -> list[dict] | None:
        """Validate that arrays are not empty if present."""
        if v is not None and len(v) == 0:
            return None  # Convert empty arrays to None for cleaner logic
        return v


class WebhookChange(BaseModel):
    """
    Change object describing what changed in the webhook.

    For WhatsApp Business webhooks, the field is always 'messages'.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    field: Literal["messages"] = Field(
        ..., description="Always 'messages' for WhatsApp Business webhooks"
    )
    value: WebhookValue = Field(..., description="The webhook payload data")


class WebhookEntry(BaseModel):
    """
    Entry object for WhatsApp Business Account webhook.

    Contains the business account ID and the changes that occurred.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str = Field(..., description="WhatsApp Business Account ID")
    changes: list[WebhookChange] = Field(
        ..., description="Array of changes (typically contains one change)"
    )

    @field_validator("id")
    @classmethod
    def validate_business_account_id(cls, v: str) -> str:
        """Validate business account ID format."""
        if not v or not v.isdigit():
            raise ValueError("Business account ID must be numeric")
        if len(v) < 10:
            raise ValueError("Business account ID must be at least 10 digits")
        return v

    @field_validator("changes")
    @classmethod
    def validate_changes_not_empty(cls, v: list[WebhookChange]) -> list[WebhookChange]:
        """Validate changes array is not empty."""
        if not v or len(v) == 0:
            raise ValueError("Changes array cannot be empty")
        return v


class WhatsAppWebhookMetadata(BaseWebhookMetadata):
    """
    WhatsApp-specific webhook metadata implementation.

    Wraps WhatsApp metadata to provide universal interface.
    """

    def __init__(self, whatsapp_metadata: WhatsAppMetadata):
        super().__init__()
        self._metadata = whatsapp_metadata

    @property
    def business_id(self) -> str:
        """Get the business phone number ID."""
        return self._metadata.phone_number_id

    @property
    def webhook_source_id(self) -> str:
        """Get the webhook source identifier (phone number ID)."""
        return self._metadata.phone_number_id

    @property
    def platform(self) -> PlatformType:
        """Always WhatsApp for this implementation."""
        return PlatformType.WHATSAPP

    def to_universal_dict(self) -> dict[str, Any]:
        """Convert to platform-agnostic dictionary representation."""
        return {
            "platform": self.platform.value,
            "business_id": self.business_id,
            "webhook_source_id": self.webhook_source_id,
            "display_phone_number": self._metadata.display_phone_number,
            "whatsapp_data": {
                "phone_number_id": self._metadata.phone_number_id,
                "display_phone_number": self._metadata.display_phone_number,
            },
        }


class WhatsAppContactAdapter(BaseContact):
    """
    WhatsApp-specific contact adapter for universal interface.

    Adapts WhatsApp contact data to the universal contact interface.

    BSUID Support (v24.0+):
    - user_id: Returns BSUID if available, else wa_id (phone number)
    - Exposes BSUID-related properties from underlying WhatsAppContact
    """

    def __init__(self, whatsapp_contact: WhatsAppContact):
        super().__init__()
        self._contact = whatsapp_contact

    @property
    def user_id(self) -> str:
        """Get the universal user identifier (BSUID if available, else WhatsApp ID)."""
        return (
            self._contact.user_id
        )  # Uses WhatsAppContact.user_id property (BSUID-aware)

    @property
    def display_name(self) -> str | None:
        """Get the user's display name (profile name)."""
        return self._contact.profile.name if self._contact.profile else None

    @property
    def platform(self) -> PlatformType:
        """Always WhatsApp for this implementation."""
        return PlatformType.WHATSAPP

    @property
    def bsuid(self) -> str | None:
        """Get the BSUID if available (v24.0+)."""
        return self._contact.bsuid

    @property
    def username(self) -> str | None:
        """Get the WhatsApp username if available (v24.0+)."""
        return self._contact.profile.username if self._contact.profile else None

    @property
    def country_code(self) -> str | None:
        """Get the user's country code if available (v24.0+)."""
        return self._contact.profile.country_code if self._contact.profile else None

    @property
    def identity_key_hash(self) -> str | None:
        """Get the identity key hash for security validation."""
        return self._contact.identity_key_hash

    def to_universal_dict(self) -> dict[str, Any]:
        """Convert to platform-agnostic dictionary representation."""
        return {
            "platform": self.platform.value,
            "user_id": self.user_id,
            "display_name": self.display_name,
            "whatsapp_data": {
                "wa_id": self._contact.wa_id,
                "bsuid": self._contact.bsuid,
                "username": self.username,
                "country_code": self.country_code,
                "profile": self._contact.profile.model_dump()
                if self._contact.profile
                else None,
            },
        }


class WhatsAppWebhook(BaseWebhook):
    """
    Top-level WhatsApp Business Platform webhook model.

    This is the root model for all WhatsApp webhook payloads.
    Use this model to parse incoming webhook requests.
    """

    model_config = ConfigDict(
        extra="forbid", str_strip_whitespace=True, validate_assignment=True
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
    def is_incoming_message(self) -> bool:
        """Check if this webhook contains incoming messages."""
        if not self.entry:
            return False

        for entry in self.entry:
            for change in entry.changes:
                if change.value.messages is not None:
                    return True
        return False

    @property
    def is_status_update(self) -> bool:
        """Check if this webhook contains message status updates."""
        if not self.entry:
            return False

        for entry in self.entry:
            for change in entry.changes:
                if change.value.statuses is not None:
                    return True
        return False

    @property
    def has_errors(self) -> bool:
        """Check if this webhook contains errors."""
        if not self.entry:
            return False

        for entry in self.entry:
            for change in entry.changes:
                if change.value.errors is not None:
                    return True
        return False

    def get_business_account_id(self) -> str:
        """Get the WhatsApp Business Account ID from the first entry."""
        if not self.entry:
            raise ValueError("No entry data available")
        return self.entry[0].id

    def get_phone_number_id(self) -> str:
        """Get the business phone number ID from the first entry."""
        if not self.entry:
            raise ValueError("No entry data available")
        return self.entry[0].changes[0].value.metadata.phone_number_id

    def get_display_phone_number(self) -> str:
        """Get the business display phone number from the first entry."""
        if not self.entry:
            raise ValueError("No entry data available")
        return self.entry[0].changes[0].value.metadata.display_phone_number

    def get_raw_messages(self) -> list[dict[str, Any]]:
        """
        Get raw message data for parsing with specific message type schemas.

        Returns empty list if no messages present.
        """
        messages = []
        for entry in self.entry:
            for change in entry.changes:
                if change.value.messages:
                    messages.extend(change.value.messages)
        return messages

    def get_raw_statuses(self) -> list[dict[str, Any]]:
        """
        Get raw status data for parsing with status schemas.

        Returns empty list if no statuses present.
        """
        statuses = []
        for entry in self.entry:
            for change in entry.changes:
                if change.value.statuses:
                    statuses.extend(change.value.statuses)
        return statuses

    def get_contacts(self) -> list[BaseContact]:
        """
        Get contact information from the webhook with universal interface.

        Returns empty list if no contacts present.
        """
        contacts = []
        for entry in self.entry:
            for change in entry.changes:
                if change.value.contacts:
                    # Convert WhatsApp contacts to universal interface
                    adapted_contacts = [
                        WhatsAppContactAdapter(contact)
                        for contact in change.value.contacts
                    ]
                    contacts.extend(adapted_contacts)
        return contacts

    def get_whatsapp_contacts(self) -> list[WhatsAppContact]:
        """
        Get original WhatsApp contact objects (platform-specific).

        Returns empty list if no contacts present.
        """
        contacts = []
        for entry in self.entry:
            for change in entry.changes:
                if change.value.contacts:
                    contacts.extend(change.value.contacts)
        return contacts

    # Implement abstract methods from BaseWebhook

    @property
    def platform(self) -> PlatformType:
        """Get the platform type this webhook came from."""
        return PlatformType.WHATSAPP

    @property
    def webhook_type(self) -> WebhookType:
        """Get the type of webhook (messages, status updates, errors, etc.)."""
        if self.is_incoming_message:
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

        whatsapp_metadata = self.entry[0].changes[0].value.metadata
        return WhatsAppWebhookMetadata(whatsapp_metadata)

    def to_universal_dict(self) -> dict[str, Any]:
        """Convert webhook to platform-agnostic dictionary representation."""
        return {
            "platform": self.platform.value,
            "webhook_type": self.webhook_type.value,
            "business_id": self.business_id,
            "source_id": self.source_id,
            "received_at": self.received_at.isoformat(),
            "has_messages": self.is_incoming_message(),
            "has_statuses": self.is_status_update(),
            "has_errors": self.has_errors(),
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
        cls, payload: dict[str, Any], **kwargs
    ) -> "WhatsAppWebhook":
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
