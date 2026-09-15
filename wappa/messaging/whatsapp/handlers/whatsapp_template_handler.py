"""WhatsApp template message handler (text, media, and location templates)."""

from typing import Any

from wappa.core.logging.logger import get_logger
from wappa.messaging.template_transport import (
    TemplateAuthenticationMethod,
    TemplateCategory,
    TemplateEndpoint,
    TemplateRoutingPolicy,
    resolve_template_route,
)
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

    def __init__(self, client: WhatsAppClient, inbox_id: str):
        self.client = client
        self._inbox_id = inbox_id
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

    def _resolve_authentication_code(
        self, body_parameters: list[TemplateParameter] | None
    ) -> str:
        """Return the single OTP code an Authentication Template body carries.

        Meta's authentication body is the fixed preset ``{{1}} is your
        verification code``, so exactly one positional text parameter is
        legal. Failing here costs one local raise instead of a provider
        round trip that returns a parameter-count error.
        """
        parameters = [
            parameter
            for parameter in (body_parameters or [])
            if parameter.type == TemplateParameterType.TEXT
        ]
        if len(parameters) != 1:
            raise ValueError(
                "An authentication Template requires exactly one body text "
                f"parameter carrying the code, got {len(parameters)}"
            )
        code = parameters[0].text
        if not code:
            raise ValueError("The authentication Template code cannot be empty")
        if parameters[0].parameter_name:
            raise ValueError(
                "Authentication Templates use the positional {{1}} code "
                "placeholder and cannot bind a named parameter"
            )
        return code

    def _build_authentication_button_component(
        self, code: str, button_index: int
    ) -> dict[str, Any]:
        """Build the OTP button component Meta requires beside the body.

        The button's URL ends in ``...&code=otp{{1}}``, so its single
        parameter is a real placeholder. Meta rejects the whole send when it
        is missing. ``index`` is serialised as a string because that is the
        type Meta's Cloud API reference declares for it.
        """
        return {
            "type": "button",
            "sub_type": "url",
            "index": str(button_index),
            "parameters": [{"type": "text", "text": code}],
        }

    def _build_authentication_components(
        self,
        body_parameters: list[TemplateParameter] | None,
        authentication_method: str,
        button_index: int,
    ) -> list[dict[str, Any]]:
        """Build ``[body, button]`` for one Authentication Template send.

        Both components carry the same code, filled once here rather than by
        two callers agreeing: the body is what the person reads, the button
        is what "Copy code" writes to their clipboard.
        """
        # Raises on an unknown method rather than silently degrading to a
        # body-only payload Meta would reject anyway.
        TemplateAuthenticationMethod(authentication_method)
        code = self._resolve_authentication_code(body_parameters)
        body_component = self._build_body_component(body_parameters)
        if body_component is None:  # pragma: no cover - guarded above
            raise ValueError("An authentication Template requires a body parameter")
        return [
            body_component,
            self._build_authentication_button_component(code, button_index),
        ]

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
        self, template_type: WhatsAppTemplateType, routing_policy: str
    ) -> str | None:
        endpoint, _ = resolve_template_route(
            TemplateCategory(template_type.value),
            TemplateRoutingPolicy(routing_policy),
        )
        if endpoint is TemplateEndpoint.MARKETING_MESSAGES:
            return self.client.url_builder.get_marketing_messages_url()
        return None

    async def _send_template_payload(
        self,
        payload: dict[str, Any],
        recipient: str,
        template_type: WhatsAppTemplateType,
        routing_policy: str,
    ) -> MessageResult:
        response = await self.client.post_request(
            payload,
            custom_url=self._resolve_template_send_url(template_type, routing_policy),
        )
        return MessageResult.from_response_payload(
            response,
            inbox_id=self._inbox_id,
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

    def _resolve_text_components(
        self,
        body_parameters: list[TemplateParameter] | None,
        *,
        template_type: WhatsAppTemplateType,
        authentication_method: str | None,
        authentication_button_index: int,
    ) -> list[dict[str, Any]] | None:
        """Decide the components one text Template send puts on the wire."""
        is_authentication = template_type is WhatsAppTemplateType.AUTHENTICATION
        if authentication_method is not None and not is_authentication:
            raise ValueError(
                "authentication_method is only valid for authentication Templates"
            )
        if is_authentication:
            if authentication_method is None:
                raise ValueError(
                    "authentication_method is required for authentication Templates"
                )
            return self._build_authentication_components(
                body_parameters,
                authentication_method,
                authentication_button_index,
            )
        body_component = self._build_body_component(body_parameters)
        return [body_component] if body_component else None

    async def send_text_template(
        self,
        recipient: str,
        template_name: str,
        body_parameters: list[TemplateParameter] | None = None,
        language_code: str = "es",
        *,
        template_type: WhatsAppTemplateType,
        routing_policy: str = "category_default",
        authentication_method: str | None = None,
        authentication_button_index: int = 0,
    ) -> MessageResult:
        try:
            components = self._resolve_text_components(
                body_parameters,
                template_type=template_type,
                authentication_method=authentication_method,
                authentication_button_index=authentication_button_index,
            )
            template_data = self._build_template_data(
                template_name,
                language_code,
                components=components,
            )
            # Text-only templates omit recipient_type for WhatsApp API compatibility.
            payload = self._build_template_payload(
                recipient, template_data, include_recipient_type=False
            )

            self.logger.debug(f"Sending text template '{template_name}' to {recipient}")
            result = await self._send_template_payload(
                payload, recipient, template_type, routing_policy
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
                inbox_id=self._inbox_id,
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
        routing_policy: str = "category_default",
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
                payload, recipient, template_type, routing_policy
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
                inbox_id=self._inbox_id,
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
        routing_policy: str = "category_default",
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
                payload, recipient, template_type, routing_policy
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
                inbox_id=self._inbox_id,
                logger=self.logger,
            )
