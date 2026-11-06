"""WhatsApp message context adapter: reply and forward context for the Universal interface."""

from __future__ import annotations

from typing import Any

from wappa.schemas.core.types import PlatformType
from wappa.webhooks.core.base_message import BaseMessageContext
from wappa.webhooks.whatsapp.models.base import MessageContext


class WhatsAppMessageContext(BaseMessageContext):
    """
    WhatsApp-specific message context adapter for universal interface.

    Adapts WhatsApp MessageContext to the universal context interface.
    """

    def __init__(self, whatsapp_context: MessageContext | None):
        super().__init__()
        self._context = whatsapp_context

    @property
    def original_message_id(self) -> str | None:
        """Get the ID of the original message being replied to or forwarded."""
        return self._context.id if self._context else None

    @property
    def original_sender_id(self) -> str | None:
        """Get the sender ID of the original message."""
        if not self._context:
            return None
        return self._context.from_bsuid or self._context.from_

    @property
    def is_reply(self) -> bool:
        """Check if this represents a reply context."""
        if not self._context:
            return False
        return (
            self._context.id is not None
            and not self._context.forwarded
            and not self._context.frequently_forwarded
            and self._context.referred_product is None
        )

    @property
    def is_forward(self) -> bool:
        """Check if this represents a forward context."""
        if not self._context:
            return False
        return bool(self._context.forwarded or self._context.frequently_forwarded)

    def to_universal_dict(self) -> dict[str, Any]:
        """Convert to platform-agnostic dictionary representation."""
        if not self._context:
            return {"platform": PlatformType.WHATSAPP.value, "has_context": False}

        return {
            "platform": PlatformType.WHATSAPP.value,
            "has_context": True,
            "original_message_id": self.original_message_id,
            "original_sender_id": self.original_sender_id,
            "is_reply": self.is_reply,
            "is_forward": self.is_forward,
            "whatsapp_data": {
                "original_sender_phone": self._context.from_,
                "original_sender_bsuid": self._context.from_bsuid,
                "original_sender_parent_bsuid": self._context.from_parent_bsuid,
                "forwarded": self._context.forwarded,
                "frequently_forwarded": self._context.frequently_forwarded,
                "referred_product": self._context.referred_product.model_dump()
                if self._context.referred_product
                else None,
            },
        }
