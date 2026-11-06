"""WhatsApp Template sends: text, media and location Templates (``ITemplateMessaging``)."""

from __future__ import annotations

from wappa.domain.inbox.identity import InboxRef
from wappa.domain.messaging_targets import DirectMessage
from wappa.domain.results import MessageResult
from wappa.messaging.template_transport.values import TemplateMediaType
from wappa.messaging.whatsapp.messenger.template_sends import _TemplateSendsMixin
from wappa.messaging.whatsapp.models.template_models import (
    TemplateParameter,
    TemplateParameterType,
    WhatsAppTemplateType,
)


class _TemplatesMixin(_TemplateSendsMixin):
    def _convert_body_parameters(
        self, body_parameters: list[dict] | None
    ) -> list | None:
        if not body_parameters:
            return None

        result = []
        for p in body_parameters:
            if not isinstance(p, dict):
                continue
            if p.get("type") == "text":
                result.append(
                    TemplateParameter(
                        type=TemplateParameterType.TEXT,
                        text=p.get("text"),
                        parameter_name=p.get("parameter_name"),
                    )
                )
            else:
                self.logger.warning(
                    "Skipping unsupported template body parameter type '%s' in "
                    "WhatsAppMessengerAdapter._convert_body_parameters",
                    p.get("type"),
                )
        return result

    def _parse_template_type(self, template_type: str) -> WhatsAppTemplateType | None:
        try:
            return WhatsAppTemplateType(template_type)
        except ValueError:
            return None

    def _parse_template_enums(
        self, template_type: str, media_type: str
    ) -> tuple[WhatsAppTemplateType | None, TemplateMediaType | None]:
        template_type_enum = self._parse_template_type(template_type)
        if template_type_enum is None:
            return None, None
        try:
            media_type_enum = TemplateMediaType(media_type)
        except ValueError:
            return template_type_enum, None
        return template_type_enum, media_type_enum

    async def send_text_template(
        self,
        template_name: str,
        target: DirectMessage,
        body_parameters: list[dict] | None = None,
        language_code: str = "es",
        *,
        template_type: str,
        routing_policy: str = "category_default",
        authentication_method: str | None = None,
        authentication_button_index: int = 0,
    ) -> MessageResult:
        target.resolve_all(InboxRef.whatsapp(self._inbox_id))
        template_type_enum = self._parse_template_type(template_type)
        if template_type_enum is None:
            return self._error_result(
                f"Invalid template type: {template_type}", "INVALID_TEMPLATE_TYPE"
            )
        return await self._deliver(
            target,
            lambda recipient: self._send_text_template_to(
                recipient=recipient,
                template_name=template_name,
                body_parameters=self._convert_body_parameters(body_parameters),
                language_code=language_code,
                template_type=template_type_enum,
                routing_policy=routing_policy,
                authentication_method=authentication_method,
                authentication_button_index=authentication_button_index,
            ),
            phone_only=template_type_enum is WhatsAppTemplateType.AUTHENTICATION,
        )

    async def send_media_template(
        self,
        template_name: str,
        target: DirectMessage,
        media_type: str,
        media_id: str | None = None,
        media_url: str | None = None,
        body_parameters: list[dict] | None = None,
        language_code: str = "es",
        *,
        template_type: str,
        routing_policy: str = "category_default",
    ) -> MessageResult:
        target.resolve_all(InboxRef.whatsapp(self._inbox_id))
        template_type_enum, media_type_enum = self._parse_template_enums(
            template_type, media_type
        )
        if template_type_enum is None:
            return self._error_result(
                f"Invalid template type: {template_type}", "INVALID_TEMPLATE_TYPE"
            )
        if media_type_enum is None:
            return self._error_result(
                f"Invalid media type: {media_type}", "INVALID_MEDIA_TYPE"
            )

        return await self._deliver(
            target,
            lambda recipient: self._send_media_template_to(
                recipient=recipient,
                template_name=template_name,
                media_type=media_type_enum,
                media_id=media_id,
                media_url=media_url,
                body_parameters=self._convert_body_parameters(body_parameters),
                language_code=language_code,
                template_type=template_type_enum,
                routing_policy=routing_policy,
            ),
        )

    async def send_location_template(
        self,
        template_name: str,
        target: DirectMessage,
        latitude: str,
        longitude: str,
        name: str,
        address: str,
        body_parameters: list[dict] | None = None,
        language_code: str = "es",
        *,
        template_type: str,
        routing_policy: str = "category_default",
    ) -> MessageResult:
        target.resolve_all(InboxRef.whatsapp(self._inbox_id))
        template_type_enum = self._parse_template_type(template_type)
        if template_type_enum is None:
            return self._error_result(
                f"Invalid template type: {template_type}", "INVALID_TEMPLATE_TYPE"
            )
        return await self._deliver(
            target,
            lambda recipient: self._send_location_template_to(
                recipient=recipient,
                template_name=template_name,
                latitude=latitude,
                longitude=longitude,
                name=name,
                address=address,
                body_parameters=self._convert_body_parameters(body_parameters),
                language_code=language_code,
                template_type=template_type_enum,
                routing_policy=routing_policy,
            ),
        )
