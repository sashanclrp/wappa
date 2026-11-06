"""Contacts, locations and the User Data Requests (location and contact request)."""

from __future__ import annotations

from collections.abc import Sequence

from wappa.domain.contacts import ContactCard, contact_cards
from wappa.domain.inbox.identity import InboxRef
from wappa.domain.messaging_targets import DirectMessage
from wappa.domain.results import MessageResult
from wappa.messaging.whatsapp.errors import handle_whatsapp_error
from wappa.messaging.whatsapp.messenger.delivery import _DeliveryMixin
from wappa.messaging.whatsapp.payloads.interactive import (
    build_interactive_payload,
    contact_request_interactive,
)
from wappa.messaging.whatsapp.payloads.specialized import (
    build_payload,
    contacts_data,
    location_data,
    location_request_data,
)


class _SpecializedMixin(_DeliveryMixin):
    async def send_contact(
        self,
        contacts: ContactCard | Sequence[ContactCard],
        target: DirectMessage,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        """One native contacts message carrying every card."""
        cards = contact_cards(contacts)
        target.resolve_all(InboxRef.whatsapp(self._inbox_id))
        return await self._deliver(
            target,
            lambda recipient: self._send_contact_card_to(
                recipient=recipient,
                contacts=cards,
                reply_to_message_id=reply_to_message_id,
            ),
        )

    async def send_location(
        self,
        latitude: float,
        longitude: float,
        target: DirectMessage,
        name: str | None = None,
        address: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        return await self._deliver(
            target,
            lambda recipient: self._send_location_to(
                recipient=recipient,
                latitude=latitude,
                longitude=longitude,
                name=name,
                address=address,
                reply_to_message_id=reply_to_message_id,
            ),
        )

    async def send_location_request(
        self, body: str, target: DirectMessage, reply_to_message_id: str | None = None
    ) -> MessageResult:
        return await self._deliver(
            target,
            lambda recipient: self._send_location_request_to(
                recipient=recipient, body=body, reply_to_message_id=reply_to_message_id
            ),
        )

    async def send_contact_request(
        self,
        body: str,
        target: DirectMessage,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        """Request a user's phone number through Meta's contact-info flow."""
        return await self._deliver(
            target,
            lambda recipient: self._send_contact_request_to(
                recipient=recipient,
                body=body,
                reply_to_message_id=reply_to_message_id,
            ),
        )

    async def _send_contact_card_to(
        self,
        recipient: str,
        contacts: Sequence[ContactCard],
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        """One ``contacts`` message carrying every card (Cloud API array)."""
        try:
            payload = build_payload(
                recipient=recipient,
                message_type="contacts",
                message_data=contacts_data(contacts),
                reply_to_message_id=reply_to_message_id,
                include_recipient_type=False,
            )

            self.logger.debug(f"Sending {len(contacts)} contact card(s) to {recipient}")
            result = await self._post_payload(payload, recipient)
            self.logger.info(f"Contact card sent successfully to {result.recipient}")
            return result

        except Exception as e:
            return handle_whatsapp_error(
                error=e,
                operation="send contact card",
                recipient=recipient,
                inbox_id=self._inbox_id,
                logger=self.logger,
            )

    async def _send_location_to(
        self,
        recipient: str,
        latitude: float,
        longitude: float,
        name: str | None = None,
        address: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        try:
            if not recipient or latitude is None or longitude is None:
                raise ValueError(
                    "recipient, latitude, and longitude are required parameters"
                )
            if not -90 <= latitude <= 90:
                raise ValueError("Latitude must be between -90 and 90 degrees")
            if not -180 <= longitude <= 180:
                raise ValueError("Longitude must be between -180 and 180 degrees")

            payload = build_payload(
                recipient=recipient,
                message_type="location",
                message_data=location_data(latitude, longitude, name, address),
                reply_to_message_id=reply_to_message_id,
            )

            self.logger.debug(
                f"Sending location ({latitude}, {longitude}) to {recipient}"
            )
            result = await self._post_payload(payload, recipient)
            self.logger.info(
                f"Location message sent successfully to {result.recipient}"
            )
            return result

        except Exception as e:
            return handle_whatsapp_error(
                error=e,
                operation="send location message",
                recipient=recipient,
                inbox_id=self._inbox_id,
                logger=self.logger,
            )

    async def _send_location_request_to(
        self, recipient: str, body: str, reply_to_message_id: str | None = None
    ) -> MessageResult:
        try:
            if not recipient or not body:
                raise ValueError("recipient and body are required parameters")
            if len(body) > 1024:
                raise ValueError("Body text cannot exceed 1024 characters")

            payload = build_payload(
                recipient=recipient,
                message_type="interactive",
                message_data=location_request_data(body),
                reply_to_message_id=reply_to_message_id,
            )

            self.logger.debug(f"Sending location request to {recipient}")
            result = await self._post_payload(payload, recipient)
            self.logger.info(
                f"Location request sent successfully to {result.recipient}"
            )
            return result

        except Exception as e:
            return handle_whatsapp_error(
                error=e,
                operation="send location request",
                recipient=recipient,
                inbox_id=self._inbox_id,
                logger=self.logger,
            )

    async def _send_contact_request_to(
        self,
        recipient: str,
        body: str,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        """Ask a username-only user to share their phone number."""
        try:
            if not body or len(body) > 4096:
                return self._error_result(
                    "Body text must contain 1 to 4096 characters",
                    "INVALID_BODY",
                    recipient,
                )

            payload = build_interactive_payload(
                recipient=recipient,
                interactive_data=contact_request_interactive(body),
                reply_to_message_id=reply_to_message_id,
            )
            return await self._post_payload(payload, recipient)
        except Exception as e:
            return handle_whatsapp_error(
                error=e,
                operation="send contact information request",
                recipient=recipient,
                inbox_id=self._inbox_id,
                logger=self.logger,
            )
