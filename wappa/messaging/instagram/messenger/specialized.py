"""Location and contact sends, emulated as text (ADR-0025)."""

from __future__ import annotations

from collections.abc import Sequence

from wappa.domain.contacts import ContactCard, contact_cards
from wappa.domain.messaging_targets import DirectMessage
from wappa.domain.results import MessageResult

from ..payloads.specialized import contact_text
from ._base import _InstagramBase


class _SpecializedMixin(_InstagramBase):
    async def send_location(
        self,
        latitude: float,
        longitude: float,
        target: DirectMessage,
        name: str | None = None,
        address: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        """Instagram has no location message: name, address and a maps link as text.
        ``reply_to_message_id`` is temporarily ignored on Instagram; result evidence records the dropped quote.
        """
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            raise ValueError("latitude/longitude out of range")
        link = f"https://www.google.com/maps/search/?api=1&query={latitude},{longitude}"
        text = "\n".join(p for p in (name, address, f"📍 {link}") if p)
        return await self.send_text(
            text, target, reply_to_message_id=reply_to_message_id
        )

    async def send_contact(
        self,
        contacts: ContactCard | Sequence[ContactCard],
        target: DirectMessage,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        """Instagram has no contact message: each card is sent as a text block.

        ``contacts`` are the same typed ``ContactCard`` values WhatsApp sends
        natively. The blocks are separated by a blank line, and text over 1000
        UTF-8 bytes is split into several messages as ``send_text`` does.

        ``reply_to_message_id`` is temporarily ignored on Instagram; result evidence records the dropped quote.
        """
        blocks = [contact_text(card) for card in contact_cards(contacts)]
        return await self.send_text(
            "\n\n".join(blocks), target, reply_to_message_id=reply_to_message_id
        )
