"""
WhatsApp specialized message handler.

Provides specialized messaging operations using WhatsApp Cloud API:
- Contact card sharing
- Location sharing and requesting
- Coordinate validation and geocoding

Migrated from whatsapp_latest/services/special_messages.py with SOLID architecture.
"""

from wappa.core.logging.logger import get_logger
from wappa.messaging.whatsapp.client.whatsapp_client import WhatsAppClient
from wappa.messaging.whatsapp.models.basic_models import MessageResult
from wappa.messaging.whatsapp.models.specialized_models import ContactCard


class WhatsAppSpecializedHandler:
    """
    Handler for WhatsApp specialized message operations.

    Provides composition-based specialized functionality for WhatsAppMessenger:
    - Contact card sharing with comprehensive contact information
    - Location sharing with geographic coordinates and optional metadata
    - Interactive location requests for user location sharing

    Based on WhatsApp Cloud API 2025 specialized message specifications.
    """

    def __init__(self, client: WhatsAppClient, tenant_id: str):
        """Initialize specialized handler.

        Args:
            client: Configured WhatsApp client for API operations
            tenant_id: Tenant identifier for logging context
        """
        self.client = client
        self._tenant_id = tenant_id
        self.logger = get_logger(__name__)

    async def send_contact_card(
        self,
        recipient: str,
        contact: ContactCard,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        """
        Send a contact card message via WhatsApp.

        Args:
            recipient: Recipient's phone number in E.164 format
            contact: Contact card information
            reply_to_message_id: Optional message ID to reply to

        Returns:
            MessageResult with operation status and metadata

        Raises:
            ValueError: If required contact fields are missing or invalid
            Exception: For API request failures
        """
        try:
            # Validate required contact fields
            if not contact.name.formatted_name:
                raise ValueError(
                    "Contact must include 'formatted_name' in the name object"
                )

            if not contact.phones or len(contact.phones) == 0:
                raise ValueError("Contact must include at least one phone number")

            # Convert ContactCard to WhatsApp API format
            contact_dict = self._convert_contact_to_api_format(contact)

            # Build message payload
            payload = {
                "messaging_product": "whatsapp",
                "to": recipient,
                "type": "contacts",
                "contacts": [contact_dict],
            }

            # Add reply context if provided
            if reply_to_message_id:
                payload["context"] = {"message_id": reply_to_message_id}

            self.logger.debug(
                f"Sending contact card for '{contact.name.formatted_name}' to {recipient}"
            )

            # Send contact message
            response = await self.client.post_request(payload)

            # Parse response
            if response.get("messages"):
                message_id = response["messages"][0].get("id")
                self.logger.info(f"Contact card sent successfully to {recipient}")

                return MessageResult(
                    success=True,
                    message_id=message_id,
                    platform="whatsapp",
                    api_response=response,
                )
            else:
                error_msg = f"No message ID in response for contact card to {recipient}"
                self.logger.error(error_msg)

                return MessageResult(
                    success=False,
                    platform="whatsapp",
                    error=error_msg,
                    error_code="NO_MESSAGE_ID",
                    api_response=response,
                )

        except Exception as e:
            error_msg = f"Failed to send contact card to {recipient}: {str(e)}"
            self.logger.exception(error_msg)

            return MessageResult(
                success=False,
                platform="whatsapp",
                error=error_msg,
                error_code="CONTACT_SEND_FAILED",
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
        """
        Send a location message via WhatsApp.

        Args:
            recipient: Recipient's phone number in E.164 format
            latitude: Location latitude in decimal degrees
            longitude: Location longitude in decimal degrees
            name: Optional location name (e.g., "Philz Coffee")
            address: Optional location address
            reply_to_message_id: Optional message ID to reply to

        Returns:
            MessageResult with operation status and metadata

        Raises:
            ValueError: If coordinates are invalid
            Exception: For API request failures
        """
        try:
            # Validate required parameters
            if not recipient or latitude is None or longitude is None:
                raise ValueError(
                    "recipient, latitude, and longitude are required parameters"
                )

            # Validate coordinate ranges
            if not -90 <= latitude <= 90:
                raise ValueError("Latitude must be between -90 and 90 degrees")

            if not -180 <= longitude <= 180:
                raise ValueError("Longitude must be between -180 and 180 degrees")

            # Build location payload
            location_data = {"latitude": str(latitude), "longitude": str(longitude)}

            if name:
                location_data["name"] = name
            if address:
                location_data["address"] = address

            # Build message payload
            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": recipient,
                "type": "location",
                "location": location_data,
            }

            # Add reply context if provided
            if reply_to_message_id:
                payload["context"] = {"message_id": reply_to_message_id}

            self.logger.debug(
                f"Sending location ({latitude}, {longitude}) to {recipient}"
            )

            # Send location message
            response = await self.client.post_request(payload)

            # Parse response
            if response.get("messages"):
                message_id = response["messages"][0].get("id")
                self.logger.info(f"Location message sent successfully to {recipient}")

                return MessageResult(
                    success=True,
                    message_id=message_id,
                    platform="whatsapp",
                    api_response=response,
                )
            else:
                error_msg = (
                    f"No message ID in response for location message to {recipient}"
                )
                self.logger.error(error_msg)

                return MessageResult(
                    success=False,
                    platform="whatsapp",
                    error=error_msg,
                    error_code="NO_MESSAGE_ID",
                    api_response=response,
                )

        except Exception as e:
            error_msg = f"Failed to send location to {recipient}: {str(e)}"
            self.logger.exception(error_msg)

            return MessageResult(
                success=False,
                platform="whatsapp",
                error=error_msg,
                error_code="LOCATION_SEND_FAILED",
            )

    async def send_location_request(
        self, recipient: str, body: str, reply_to_message_id: str | None = None
    ) -> MessageResult:
        """
        Send a location request message via WhatsApp.

        This displays a message with a "Send Location" button that allows
        users to share their location.

        Args:
            recipient: Recipient's phone number in E.164 format
            body: Message text that appears above the location button (max 1024 chars)
            reply_to_message_id: Optional message ID to reply to

        Returns:
            MessageResult with operation status and metadata

        Raises:
            ValueError: If required parameters are invalid
            Exception: For API request failures
        """
        try:
            # Validate required parameters
            if not recipient or not body:
                raise ValueError("recipient and body are required parameters")

            # Validate body length
            if len(body) > 1024:
                raise ValueError("Body text cannot exceed 1024 characters")

            # Build interactive location request payload
            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "type": "interactive",
                "to": recipient,
                "interactive": {
                    "type": "location_request_message",
                    "body": {"text": body},
                    "action": {"name": "send_location"},
                },
            }

            # Add reply context if provided
            if reply_to_message_id:
                payload["context"] = {"message_id": reply_to_message_id}

            self.logger.debug(f"Sending location request to {recipient}")

            # Send location request message
            response = await self.client.post_request(payload)

            # Parse response
            if response.get("messages"):
                message_id = response["messages"][0].get("id")
                self.logger.info(f"Location request sent successfully to {recipient}")

                return MessageResult(
                    success=True,
                    message_id=message_id,
                    platform="whatsapp",
                    api_response=response,
                )
            else:
                error_msg = (
                    f"No message ID in response for location request to {recipient}"
                )
                self.logger.error(error_msg)

                return MessageResult(
                    success=False,
                    platform="whatsapp",
                    error=error_msg,
                    error_code="NO_MESSAGE_ID",
                    api_response=response,
                )

        except Exception as e:
            error_msg = f"Failed to send location request to {recipient}: {str(e)}"
            self.logger.exception(error_msg)

            return MessageResult(
                success=False,
                platform="whatsapp",
                error=error_msg,
                error_code="LOCATION_REQUEST_FAILED",
            )

    def _convert_contact_to_api_format(self, contact: ContactCard) -> dict:
        """
        Convert ContactCard model to WhatsApp API contact format.

        Args:
            contact: ContactCard model instance

        Returns:
            Dict in WhatsApp API contact format
        """
        api_contact = {}

        # Name (required)
        api_contact["name"] = {"formatted_name": contact.name.formatted_name}

        if contact.name.first_name:
            api_contact["name"]["first_name"] = contact.name.first_name
        if contact.name.last_name:
            api_contact["name"]["last_name"] = contact.name.last_name
        if contact.name.middle_name:
            api_contact["name"]["middle_name"] = contact.name.middle_name
        if contact.name.suffix:
            api_contact["name"]["suffix"] = contact.name.suffix
        if contact.name.prefix:
            api_contact["name"]["prefix"] = contact.name.prefix

        # Phones (required)
        api_contact["phones"] = []
        for phone in contact.phones:
            phone_dict = {"phone": phone.phone}
            if phone.type:
                phone_dict["type"] = phone.type
            if phone.wa_id:
                phone_dict["wa_id"] = phone.wa_id
            api_contact["phones"].append(phone_dict)

        # Emails (optional)
        if contact.emails:
            api_contact["emails"] = []
            for email in contact.emails:
                email_dict = {"email": email.email}
                if email.type:
                    email_dict["type"] = email.type
                api_contact["emails"].append(email_dict)

        # Addresses (optional)
        if contact.addresses:
            api_contact["addresses"] = []
            for address in contact.addresses:
                address_dict = {}
                if address.type:
                    address_dict["type"] = address.type
                if address.street:
                    address_dict["street"] = address.street
                if address.city:
                    address_dict["city"] = address.city
                if address.state:
                    address_dict["state"] = address.state
                if address.zip:
                    address_dict["zip"] = address.zip
                if address.country:
                    address_dict["country"] = address.country
                if address.country_code:
                    address_dict["country_code"] = address.country_code
                api_contact["addresses"].append(address_dict)

        # Organization (optional)
        if contact.org:
            api_contact["org"] = {}
            if contact.org.company:
                api_contact["org"]["company"] = contact.org.company
            if contact.org.department:
                api_contact["org"]["department"] = contact.org.department
            if contact.org.title:
                api_contact["org"]["title"] = contact.org.title

        # URLs (optional)
        if contact.urls:
            api_contact["urls"] = []
            for url in contact.urls:
                url_dict = {"url": url.url}
                if url.type:
                    url_dict["type"] = url.type
                api_contact["urls"].append(url_dict)

        # Birthday (optional)
        if contact.birthday:
            api_contact["birthday"] = contact.birthday

        return api_contact

    def validate_coordinates(self, latitude: float, longitude: float) -> dict:
        """
        Validate geographic coordinates.

        Args:
            latitude: Latitude coordinate
            longitude: Longitude coordinate

        Returns:
            Dict with validation results and any errors
        """
        errors = []

        # Validate latitude range
        if not -90 <= latitude <= 90:
            errors.append("Latitude must be between -90 and 90 degrees")

        # Validate longitude range
        if not -180 <= longitude <= 180:
            errors.append("Longitude must be between -180 and 180 degrees")

        # Check for obviously invalid coordinates (e.g., 0,0 unless intentional)
        if latitude == 0 and longitude == 0:
            errors.append("Coordinates (0,0) may be invalid - please verify location")

        return {
            "valid": len(errors) == 0,
            "latitude": latitude,
            "longitude": longitude,
            "errors": errors if errors else None,
        }
