"""WhatsApp specialized message handler (contacts, locations, location requests)."""

from typing import Any

from wappa.core.logging.logger import get_logger
from wappa.messaging.whatsapp.client.whatsapp_client import WhatsAppClient
from wappa.messaging.whatsapp.models.basic_models import MessageResult
from wappa.messaging.whatsapp.models.specialized_models import ContactCard
from wappa.messaging.whatsapp.utils.error_helpers import handle_whatsapp_error
from wappa.schemas.core.recipient import apply_recipient_to_payload


def _copy_optional(src: Any, dst: dict[str, Any], fields: tuple[str, ...]) -> None:
    """Copy truthy optional attrs from a pydantic model into a dict payload."""
    for field in fields:
        value = getattr(src, field, None)
        if value:
            dst[field] = value


class WhatsAppSpecializedHandler:
    """Contact cards, locations, and location-request messaging for WhatsAppMessenger."""

    def __init__(self, client: WhatsAppClient, tenant_id: str):
        self.client = client
        self._tenant_id = tenant_id
        self.logger = get_logger(__name__)

    def _build_payload(
        self,
        recipient: str,
        message_type: str,
        message_data: dict[str, Any] | list[dict[str, Any]],
        *,
        reply_to_message_id: str | None = None,
        include_recipient_type: bool = True,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "messaging_product": "whatsapp",
            "type": message_type,
        }
        if include_recipient_type:
            payload["recipient_type"] = "individual"
        payload[message_type] = message_data
        apply_recipient_to_payload(payload, recipient)
        if reply_to_message_id:
            payload["context"] = {"message_id": reply_to_message_id}
        return payload

    async def _send_payload(
        self, payload: dict[str, Any], recipient: str
    ) -> MessageResult:
        response = await self.client.post_request(payload)
        return MessageResult.from_response_payload(
            response,
            tenant_id=self._tenant_id,
            fallback_recipient=recipient,
        )

    async def send_contact_card(
        self,
        recipient: str,
        contact: ContactCard,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        try:
            if not contact.name.formatted_name:
                raise ValueError(
                    "Contact must include 'formatted_name' in the name object"
                )
            if not contact.phones:
                raise ValueError("Contact must include at least one phone number")

            contact_dict = self._convert_contact_to_api_format(contact)
            payload = self._build_payload(
                recipient=recipient,
                message_type="contacts",
                message_data=[contact_dict],
                reply_to_message_id=reply_to_message_id,
                include_recipient_type=False,
            )

            self.logger.debug(
                f"Sending contact card for '{contact.name.formatted_name}' to {recipient}"
            )
            result = await self._send_payload(payload, recipient)
            self.logger.info(f"Contact card sent successfully to {result.recipient}")
            return result

        except Exception as e:
            return handle_whatsapp_error(
                error=e,
                operation="send contact card",
                recipient=recipient,
                tenant_id=self._tenant_id,
                logger=self.logger,
            )

    async def send_location(
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

            location_data: dict[str, Any] = {
                "latitude": str(latitude),
                "longitude": str(longitude),
            }
            if name:
                location_data["name"] = name
            if address:
                location_data["address"] = address

            payload = self._build_payload(
                recipient=recipient,
                message_type="location",
                message_data=location_data,
                reply_to_message_id=reply_to_message_id,
            )

            self.logger.debug(
                f"Sending location ({latitude}, {longitude}) to {recipient}"
            )
            result = await self._send_payload(payload, recipient)
            self.logger.info(f"Location message sent successfully to {result.recipient}")
            return result

        except Exception as e:
            return handle_whatsapp_error(
                error=e,
                operation="send location message",
                recipient=recipient,
                tenant_id=self._tenant_id,
                logger=self.logger,
            )

    async def send_location_request(
        self, recipient: str, body: str, reply_to_message_id: str | None = None
    ) -> MessageResult:
        try:
            if not recipient or not body:
                raise ValueError("recipient and body are required parameters")
            if len(body) > 1024:
                raise ValueError("Body text cannot exceed 1024 characters")

            payload = self._build_payload(
                recipient=recipient,
                message_type="interactive",
                message_data={
                    "type": "location_request_message",
                    "body": {"text": body},
                    "action": {"name": "send_location"},
                },
                reply_to_message_id=reply_to_message_id,
            )

            self.logger.debug(f"Sending location request to {recipient}")
            result = await self._send_payload(payload, recipient)
            self.logger.info(f"Location request sent successfully to {result.recipient}")
            return result

        except Exception as e:
            return handle_whatsapp_error(
                error=e,
                operation="send location request",
                recipient=recipient,
                tenant_id=self._tenant_id,
                logger=self.logger,
            )

    def _convert_contact_to_api_format(self, contact: ContactCard) -> dict[str, Any]:
        name_dict: dict[str, Any] = {"formatted_name": contact.name.formatted_name}
        _copy_optional(
            contact.name,
            name_dict,
            ("first_name", "last_name", "middle_name", "suffix", "prefix"),
        )

        phones: list[dict[str, Any]] = []
        for phone in contact.phones:
            phone_dict: dict[str, Any] = {"phone": phone.phone}
            _copy_optional(phone, phone_dict, ("type", "wa_id"))
            phones.append(phone_dict)

        api_contact: dict[str, Any] = {"name": name_dict, "phones": phones}

        if contact.emails:
            emails: list[dict[str, Any]] = []
            for email in contact.emails:
                email_dict: dict[str, Any] = {"email": email.email}
                _copy_optional(email, email_dict, ("type",))
                emails.append(email_dict)
            api_contact["emails"] = emails

        if contact.addresses:
            addresses: list[dict[str, Any]] = []
            address_fields = (
                "type",
                "street",
                "city",
                "state",
                "zip",
                "country",
                "country_code",
            )
            for address in contact.addresses:
                address_dict: dict[str, Any] = {}
                _copy_optional(address, address_dict, address_fields)
                addresses.append(address_dict)
            api_contact["addresses"] = addresses

        if contact.org:
            org_dict: dict[str, Any] = {}
            _copy_optional(contact.org, org_dict, ("company", "department", "title"))
            api_contact["org"] = org_dict

        if contact.urls:
            urls: list[dict[str, Any]] = []
            for url in contact.urls:
                url_dict: dict[str, Any] = {"url": url.url}
                _copy_optional(url, url_dict, ("type",))
                urls.append(url_dict)
            api_contact["urls"] = urls

        if contact.birthday:
            api_contact["birthday"] = contact.birthday

        return api_contact
