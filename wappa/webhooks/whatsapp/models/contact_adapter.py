"""Universal contact adapter over a WhatsApp contact."""

from __future__ import annotations

from typing import Any

from wappa.schemas.core.types import PlatformType
from wappa.webhooks.core.base_webhook import (
    BaseContact,
)
from wappa.webhooks.whatsapp.models.base import WhatsAppContact


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
    def parent_bsuid(self) -> str | None:
        """Get the parent BSUID when the portfolio is enrolled for one."""
        return self._contact.parent_bsuid

    @property
    def wa_id(self) -> str:
        """Get the WhatsApp numeric user ID / phone number if available."""
        return self._contact.wa_id

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
                "parent_bsuid": self.parent_bsuid,
                "username": self.username,
                "country_code": self.country_code,
                "profile": self._contact.profile.model_dump()
                if self._contact.profile
                else None,
            },
        }
