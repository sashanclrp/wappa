"""
WhatsApp template message handler.

Provides template messaging operations using WhatsApp Cloud API:
- Text-only templates
- Media templates (image, video, document headers)
- Location templates with coordinate headers

Migrated from whatsapp_latest/services/send_templates.py with SOLID architecture.
"""

from wappa.core.logging.logger import get_logger
from wappa.messaging.whatsapp.client.whatsapp_client import WhatsAppClient
from wappa.messaging.whatsapp.models.basic_models import MessageResult
from wappa.messaging.whatsapp.models.template_models import (
    MediaType,
    TemplateParameter,
    TemplateParameterType,
)


class WhatsAppTemplateHandler:
    """
    Handler for WhatsApp template message operations.

    Provides composition-based template functionality for WhatsAppMessenger:
    - Text templates with parameter substitution
    - Media templates with header media content
    - Location templates with geographic coordinates

    Based on WhatsApp Cloud API 2025 template specifications.
    """

    def __init__(self, client: WhatsAppClient, tenant_id: str):
        """Initialize template handler.

        Args:
            client: Configured WhatsApp client for API operations
            tenant_id: Tenant identifier for logging context
        """
        self.client = client
        self._tenant_id = tenant_id
        self.logger = get_logger(__name__)

    async def send_text_template(
        self,
        phone_number: str,
        template_name: str,
        body_parameters: list[TemplateParameter] | None = None,
        language_code: str = "es",
    ) -> MessageResult:
        """
        Send a text-only WhatsApp template message.

        Args:
            phone_number: Recipient's phone number in E.164 format
            template_name: Name of the approved template
            body_parameters: List of parameters for template text replacement
            language_code: BCP-47 language code for the template

        Returns:
            MessageResult with operation status and metadata

        Raises:
            ValueError: If template parameters are invalid
            Exception: For API request failures
        """
        try:
            # Build template data
            template_data = {"name": template_name, "language": {"code": language_code}}

            # Add body parameters if provided
            if body_parameters:
                # Convert TemplateParameter objects to API format
                api_parameters = []
                for param in body_parameters:
                    if param.type == TemplateParameterType.TEXT:
                        api_parameters.append({"type": "text", "text": param.text})
                    # Future: Add support for currency, date_time, etc.

                template_data["components"] = [
                    {"type": "body", "parameters": api_parameters}
                ]

            # Build message payload
            payload = {
                "messaging_product": "whatsapp",
                "to": phone_number,
                "type": "template",
                "template": template_data,
            }

            self.logger.debug(
                f"Sending text template '{template_name}' to {phone_number}"
            )

            # Send template message
            response = await self.client.post_request(payload)

            # Parse response
            if response.get("messages"):
                message_id = response["messages"][0].get("id")
                self.logger.info(
                    f"Text template '{template_name}' sent successfully to {phone_number}"
                )

                return MessageResult(
                    success=True,
                    message_id=message_id,
                    platform="whatsapp",
                    api_response=response,
                )
            else:
                error_msg = f"No message ID in response for template '{template_name}'"
                self.logger.error(error_msg)

                return MessageResult(
                    success=False,
                    platform="whatsapp",
                    error=error_msg,
                    error_code="NO_MESSAGE_ID",
                    api_response=response,
                )

        except Exception as e:
            error_msg = f"Failed to send text template '{template_name}' to {phone_number}: {str(e)}"
            self.logger.exception(error_msg)

            return MessageResult(
                success=False,
                platform="whatsapp",
                error=error_msg,
                error_code="TEMPLATE_SEND_FAILED",
            )

    async def send_media_template(
        self,
        phone_number: str,
        template_name: str,
        media_type: MediaType,
        media_id: str | None = None,
        media_url: str | None = None,
        body_parameters: list[TemplateParameter] | None = None,
        language_code: str = "es",
    ) -> MessageResult:
        """
        Send a WhatsApp template message with media header.

        Args:
            phone_number: Recipient's phone number in E.164 format
            template_name: Name of the approved template
            media_type: Type of media (image, video, document)
            media_id: ID of pre-uploaded media (exclusive with media_url)
            media_url: URL of media to include (exclusive with media_id)
            body_parameters: List of parameters for template text replacement
            language_code: BCP-47 language code for the template

        Returns:
            MessageResult with operation status and metadata

        Raises:
            ValueError: If media parameters are invalid or both/neither media source provided
            Exception: For API request failures
        """
        try:
            # Validate media source
            if (media_id and media_url) or (not media_id and not media_url):
                raise ValueError(
                    "Either media_id or media_url must be provided, but not both"
                )

            # Build header component with media
            header_component = {
                "type": "header",
                "parameters": [
                    {
                        "type": media_type.value,
                        media_type.value: {"id": media_id}
                        if media_id
                        else {"link": media_url},
                    }
                ],
            }

            # Build template components
            components = [header_component]

            # Add body parameters if provided
            if body_parameters:
                api_parameters = []
                for param in body_parameters:
                    if param.type == TemplateParameterType.TEXT:
                        api_parameters.append({"type": "text", "text": param.text})

                components.append({"type": "body", "parameters": api_parameters})

            # Build template data
            template_data = {
                "name": template_name,
                "language": {"code": language_code},
                "components": components,
            }

            # Build message payload
            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": phone_number,
                "type": "template",
                "template": template_data,
            }

            self.logger.debug(
                f"Sending media template '{template_name}' ({media_type.value}) to {phone_number}"
            )

            # Send template message
            response = await self.client.post_request(payload)

            # Parse response
            if response.get("messages"):
                message_id = response["messages"][0].get("id")
                self.logger.info(
                    f"Media template '{template_name}' sent successfully to {phone_number}"
                )

                return MessageResult(
                    success=True,
                    message_id=message_id,
                    platform="whatsapp",
                    api_response=response,
                )
            else:
                error_msg = (
                    f"No message ID in response for media template '{template_name}'"
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
            error_msg = f"Failed to send media template '{template_name}' to {phone_number}: {str(e)}"
            self.logger.exception(error_msg)

            return MessageResult(
                success=False,
                platform="whatsapp",
                error=error_msg,
                error_code="MEDIA_TEMPLATE_SEND_FAILED",
            )

    async def send_location_template(
        self,
        phone_number: str,
        template_name: str,
        latitude: str,
        longitude: str,
        name: str,
        address: str,
        body_parameters: list[TemplateParameter] | None = None,
        language_code: str = "es",
    ) -> MessageResult:
        """
        Send a location-based WhatsApp template message.

        Args:
            phone_number: Recipient's phone number in E.164 format
            template_name: Name of the approved template
            latitude: Location latitude as string
            longitude: Location longitude as string
            name: Name/title of the location
            address: Physical address of the location
            body_parameters: List of parameters for template text replacement
            language_code: BCP-47 language code for the template

        Returns:
            MessageResult with operation status and metadata

        Raises:
            ValueError: If location parameters are invalid
            Exception: For API request failures
        """
        try:
            # Validate coordinates (basic range check)
            try:
                lat = float(latitude)
                lon = float(longitude)
                if not (-90 <= lat <= 90):
                    raise ValueError("Latitude must be between -90 and 90 degrees")
                if not (-180 <= lon <= 180):
                    raise ValueError("Longitude must be between -180 and 180 degrees")
            except ValueError as e:
                if "could not convert" in str(e):
                    raise ValueError(
                        "Latitude and longitude must be valid numbers"
                    ) from e
                raise

            # Build location parameter
            location_param = {
                "type": "location",
                "location": {
                    "latitude": latitude,
                    "longitude": longitude,
                    "name": name,
                    "address": address,
                },
            }

            # Build header component with location
            header_component = {"type": "header", "parameters": [location_param]}

            # Build template components
            components = [header_component]

            # Add body parameters if provided
            if body_parameters:
                api_parameters = []
                for param in body_parameters:
                    if param.type == TemplateParameterType.TEXT:
                        api_parameters.append({"type": "text", "text": param.text})

                components.append({"type": "body", "parameters": api_parameters})

            # Build template data
            template_data = {
                "name": template_name,
                "language": {"code": language_code},
                "components": components,
            }

            # Build message payload
            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": phone_number,
                "type": "template",
                "template": template_data,
            }

            self.logger.debug(
                f"Sending location template '{template_name}' to {phone_number}"
            )

            # Send template message
            response = await self.client.post_request(payload)

            # Parse response
            if response.get("messages"):
                message_id = response["messages"][0].get("id")
                self.logger.info(
                    f"Location template '{template_name}' sent successfully to {phone_number}"
                )

                return MessageResult(
                    success=True,
                    message_id=message_id,
                    platform="whatsapp",
                    api_response=response,
                )
            else:
                error_msg = (
                    f"No message ID in response for location template '{template_name}'"
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
            error_msg = f"Failed to send location template '{template_name}' to {phone_number}: {str(e)}"
            self.logger.exception(error_msg)

            return MessageResult(
                success=False,
                platform="whatsapp",
                error=error_msg,
                error_code="LOCATION_TEMPLATE_SEND_FAILED",
            )

    async def get_template_info(self, template_name: str) -> dict:
        """
        Get information about a specific template.

        Args:
            template_name: Name of the template to query

        Returns:
            Dict with template information or error details
        """
        try:
            # This would typically call WhatsApp's template management API
            # For now, return basic info structure
            self.logger.debug(f"Getting template info for '{template_name}'")

            return {
                "template_name": template_name,
                "status": "APPROVED",  # This should come from actual API
                "category": "MARKETING",  # This should come from actual API
                "language": "es",  # This should come from actual API
            }

        except Exception as e:
            self.logger.exception(
                f"Failed to get template info for '{template_name}': {str(e)}"
            )
            return {"template_name": template_name, "error": str(e), "status": "ERROR"}
