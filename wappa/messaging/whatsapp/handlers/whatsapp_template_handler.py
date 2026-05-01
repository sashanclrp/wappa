"""WhatsApp template message handler (text, media, and location templates)."""

from typing import Any

from wappa.core.logging.logger import get_logger
from wappa.messaging.whatsapp.client.whatsapp_client import WhatsAppClient
from wappa.messaging.whatsapp.models.basic_models import MessageResult
from wappa.messaging.whatsapp.models.template_models import (
    TemplateParameter,
    TemplateParameterType,
    WhatsAppTemplateMediaType,
    WhatsAppTemplateType,
)
from wappa.messaging.whatsapp.utils.error_helpers import handle_whatsapp_error
from wappa.schemas.core.recipient import apply_recipient_to_payload


class WhatsAppTemplateHandler:
    """Template message operations for WhatsAppMessenger."""

    def __init__(self, client: WhatsAppClient, tenant_id: str):
        self.client = client
        self._tenant_id = tenant_id
        self.logger = get_logger(__name__)

    def _build_text_parameter(self, param: TemplateParameter) -> dict[str, Any]:
        param_dict: dict[str, Any] = {"type": "text", "text": param.text}
        if param.parameter_name:
            param_dict["parameter_name"] = param.parameter_name
        return param_dict

    def _build_body_component(
        self, body_parameters: list[TemplateParameter] | None
    ) -> dict[str, Any] | None:
        if not body_parameters:
            return None
        api_parameters = [
            self._build_text_parameter(param)
            for param in body_parameters
            if param.type == TemplateParameterType.TEXT
        ]
        return {"type": "body", "parameters": api_parameters}

    def _build_template_payload(
        self,
        recipient: str,
        template_data: dict[str, Any],
        *,
        include_recipient_type: bool = True,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "messaging_product": "whatsapp",
            "type": "template",
            "template": template_data,
        }
        if include_recipient_type:
            payload["recipient_type"] = "individual"
        apply_recipient_to_payload(payload, recipient)
        return payload

    def _resolve_template_send_url(
        self, template_type: WhatsAppTemplateType, override: bool | None
    ) -> str | None:
        if template_type != WhatsAppTemplateType.MARKETING and override:
            raise ValueError(
                "override parameter is only compatible with template_type='marketing'"
            )
        if template_type == WhatsAppTemplateType.MARKETING:
            if override is False:
                return None
            return self.client.url_builder.get_marketing_messages_url()
        return None

    async def _send_template_payload(
        self,
        payload: dict[str, Any],
        recipient: str,
        template_type: WhatsAppTemplateType,
        override: bool | None,
    ) -> MessageResult:
        response = await self.client.post_request(
            payload, custom_url=self._resolve_template_send_url(template_type, override)
        )
        return MessageResult.from_response_payload(
            response,
            tenant_id=self._tenant_id,
            fallback_recipient=recipient,
        )

    def _build_components_with_header(
        self,
        header_component: dict[str, Any],
        body_parameters: list[TemplateParameter] | None,
    ) -> list[dict[str, Any]]:
        components: list[dict[str, Any]] = [header_component]
        if body_component := self._build_body_component(body_parameters):
            components.append(body_component)
        return components

    def _build_template_data(
        self,
        template_name: str,
        language_code: str,
        components: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        data: dict[str, Any] = {
            "name": template_name,
            "language": {"code": language_code},
        }
        if components:
            data["components"] = components
        return data

    async def send_text_template(
        self,
        recipient: str,
        template_name: str,
        body_parameters: list[TemplateParameter] | None = None,
        language_code: str = "es",
        *,
        template_type: WhatsAppTemplateType,
        override: bool | None = None,
    ) -> MessageResult:
        try:
            body_component = self._build_body_component(body_parameters)
            template_data = self._build_template_data(
                template_name,
                language_code,
                components=[body_component] if body_component else None,
            )
            # Text-only templates omit recipient_type for WhatsApp API compatibility.
            payload = self._build_template_payload(
                recipient, template_data, include_recipient_type=False
            )

            self.logger.debug(f"Sending text template '{template_name}' to {recipient}")
            result = await self._send_template_payload(
                payload, recipient, template_type, override
            )
            self.logger.info(
                f"Text template '{template_name}' sent successfully to {result.recipient}"
            )
            return result

        except Exception as e:
            return handle_whatsapp_error(
                error=e,
                operation=f"send text template '{template_name}'",
                recipient=recipient,
                tenant_id=self._tenant_id,
                logger=self.logger,
            )

    async def send_media_template(
        self,
        recipient: str,
        template_name: str,
        media_type: WhatsAppTemplateMediaType,
        media_id: str | None = None,
        media_url: str | None = None,
        body_parameters: list[TemplateParameter] | None = None,
        language_code: str = "es",
        *,
        template_type: WhatsAppTemplateType,
        override: bool | None = None,
    ) -> MessageResult:
        try:
            if bool(media_id) == bool(media_url):
                raise ValueError(
                    "Either media_id or media_url must be provided, but not both"
                )

            media_source = {"id": media_id} if media_id else {"link": media_url}
            header_component = {
                "type": "header",
                "parameters": [
                    {"type": media_type.value, media_type.value: media_source}
                ],
            }

            template_data = self._build_template_data(
                template_name,
                language_code,
                components=self._build_components_with_header(
                    header_component, body_parameters
                ),
            )
            payload = self._build_template_payload(recipient, template_data)

            self.logger.debug(
                f"Sending media template '{template_name}' ({media_type.value}) to {recipient}"
            )
            result = await self._send_template_payload(
                payload, recipient, template_type, override
            )
            self.logger.info(
                f"Media template '{template_name}' sent successfully to {result.recipient}"
            )
            return result

        except Exception as e:
            return handle_whatsapp_error(
                error=e,
                operation=f"send media template '{template_name}'",
                recipient=recipient,
                tenant_id=self._tenant_id,
                logger=self.logger,
            )

    async def send_location_template(
        self,
        recipient: str,
        template_name: str,
        latitude: str,
        longitude: str,
        name: str,
        address: str,
        body_parameters: list[TemplateParameter] | None = None,
        language_code: str = "es",
        *,
        template_type: WhatsAppTemplateType,
        override: bool | None = None,
    ) -> MessageResult:
        try:
            try:
                lat = float(latitude)
                lon = float(longitude)
            except ValueError as e:
                raise ValueError("Latitude and longitude must be valid numbers") from e
            if not -90 <= lat <= 90:
                raise ValueError("Latitude must be between -90 and 90 degrees")
            if not -180 <= lon <= 180:
                raise ValueError("Longitude must be between -180 and 180 degrees")

            header_component = {
                "type": "header",
                "parameters": [
                    {
                        "type": "location",
                        "location": {
                            "latitude": latitude,
                            "longitude": longitude,
                            "name": name,
                            "address": address,
                        },
                    }
                ],
            }

            template_data = self._build_template_data(
                template_name,
                language_code,
                components=self._build_components_with_header(
                    header_component, body_parameters
                ),
            )
            payload = self._build_template_payload(recipient, template_data)

            self.logger.debug(
                f"Sending location template '{template_name}' to {recipient}"
            )
            result = await self._send_template_payload(
                payload, recipient, template_type, override
            )
            self.logger.info(
                f"Location template '{template_name}' sent successfully to {result.recipient}"
            )
            return result

        except Exception as e:
            return handle_whatsapp_error(
                error=e,
                operation=f"send location template '{template_name}'",
                recipient=recipient,
                tenant_id=self._tenant_id,
                logger=self.logger,
            )
