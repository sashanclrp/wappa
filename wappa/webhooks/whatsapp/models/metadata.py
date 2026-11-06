"""Universal metadata wrapper over the WhatsApp phone-number metadata."""

from __future__ import annotations

from typing import Any

from wappa.schemas.core.types import PlatformType
from wappa.webhooks.core.base_webhook import (
    BaseWebhookMetadata,
)
from wappa.webhooks.whatsapp.models.base import WhatsAppMetadata


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
