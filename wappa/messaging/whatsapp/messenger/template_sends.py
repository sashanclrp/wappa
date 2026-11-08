"""The three Template sends to one address: payload, route, post and error result."""

from __future__ import annotations

from typing import Any

from wappa.domain.results import MessageResult
from wappa.messaging.template_transport import (
    TemplateCategory,
    TemplateEndpoint,
    TemplateRoutingPolicy,
    resolve_template_route,
)
from wappa.messaging.template_transport.values import TemplateMediaType
from wappa.messaging.whatsapp.errors import handle_whatsapp_error
from wappa.messaging.whatsapp.messenger.delivery import _DeliveryMixin
from wappa.messaging.whatsapp.models.template_models import (
    TemplateParameter,
    WhatsAppTemplateType,
)
from wappa.messaging.whatsapp.payloads.templates import (
    build_components_with_header,
    build_template_data,
    build_template_payload,
    location_header_component,
    media_header_component,
    resolve_text_components,
)


class _TemplateSendsMixin(_DeliveryMixin):
    # Template routing and the three sends

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
        return await self._post_payload(
            payload,
            recipient,
            custom_url=self._resolve_template_send_url(template_type, routing_policy),
        )

    async def _send_text_template_to(
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
            components = resolve_text_components(
                body_parameters,
                template_type=template_type,
                authentication_method=authentication_method,
                authentication_button_index=authentication_button_index,
            )
            template_data = build_template_data(
                template_name,
                language_code,
                components=components,
            )
            # Text-only templates omit recipient_type for WhatsApp API compatibility.
            payload = build_template_payload(
                recipient, template_data, include_recipient_type=False
            )

            self.logger.debug(f"Sending text template '{template_name}'")
            result = await self._send_template_payload(
                payload, recipient, template_type, routing_policy
            )
            self.logger.info(f"Text template '{template_name}' sent successfully")
            return result

        except Exception as e:
            return handle_whatsapp_error(
                error=e,
                operation=f"send text template '{template_name}'",
                recipient=recipient,
                inbox_id=self._inbox_id,
                logger=self.logger,
            )

    async def _send_media_template_to(
        self,
        recipient: str,
        template_name: str,
        media_type: TemplateMediaType,
        media_id: str | None = None,
        media_url: str | None = None,
        body_parameters: list[TemplateParameter] | None = None,
        language_code: str = "es",
        *,
        template_type: WhatsAppTemplateType,
        routing_policy: str = "category_default",
    ) -> MessageResult:
        try:
            header_component = media_header_component(media_type, media_id, media_url)
            template_data = build_template_data(
                template_name,
                language_code,
                components=build_components_with_header(
                    header_component, body_parameters
                ),
            )
            payload = build_template_payload(recipient, template_data)

            self.logger.debug(
                f"Sending media template '{template_name}' ({media_type.value})"
            )
            result = await self._send_template_payload(
                payload, recipient, template_type, routing_policy
            )
            self.logger.info(f"Media template '{template_name}' sent successfully")
            return result

        except Exception as e:
            return handle_whatsapp_error(
                error=e,
                operation=f"send media template '{template_name}'",
                recipient=recipient,
                inbox_id=self._inbox_id,
                logger=self.logger,
            )

    async def _send_location_template_to(
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
            header_component = location_header_component(
                latitude, longitude, name, address
            )
            template_data = build_template_data(
                template_name,
                language_code,
                components=build_components_with_header(
                    header_component, body_parameters
                ),
            )
            payload = build_template_payload(recipient, template_data)

            self.logger.debug(f"Sending location template '{template_name}'")
            result = await self._send_template_payload(
                payload, recipient, template_type, routing_policy
            )
            self.logger.info(f"Location template '{template_name}' sent successfully")
            return result

        except Exception as e:
            return handle_whatsapp_error(
                error=e,
                operation=f"send location template '{template_name}'",
                recipient=recipient,
                inbox_id=self._inbox_id,
                logger=self.logger,
            )
