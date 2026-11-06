"""Pipeline-wrapped Template and user-data-request capabilities."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ....domain.interfaces.template_messaging import (
    ITemplateMessaging,
)
from ....domain.interfaces.user_data_requests import (
    IUserDataRequests,
)
from ....domain.messaging_targets import DirectMessage

if TYPE_CHECKING:
    from wappa.domain.results import MessageResult

    from .messenger import MessengerPipeline


class _PipelineTemplates(ITemplateMessaging):
    """Template capability that still runs the pipeline's message middleware.

    Invocations keep the historic method names (``send_text_template`` …) so
    window guards and cache middleware see Templates exactly as before.
    """

    def __init__(self, pipeline: MessengerPipeline) -> None:
        self._pipeline = pipeline

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
        kw = {
            "template_type": template_type,
            "routing_policy": routing_policy,
            "authentication_method": authentication_method,
            "authentication_button_index": authentication_button_index,
        }
        return await self._pipeline._invoke(
            "send_text_template",
            "text_template",
            target,
            {
                "template_name": template_name,
                "target": target,
                "body_parameters": body_parameters,
                "language_code": language_code,
                **kw,
            },
            keyword_only=kw,
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
        kw = {"template_type": template_type, "routing_policy": routing_policy}
        return await self._pipeline._invoke(
            "send_media_template",
            "media_template",
            target,
            {
                "template_name": template_name,
                "target": target,
                "media_type": media_type,
                "media_id": media_id,
                "media_url": media_url,
                "body_parameters": body_parameters,
                "language_code": language_code,
                **kw,
            },
            keyword_only=kw,
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
        kw = {"template_type": template_type, "routing_policy": routing_policy}
        return await self._pipeline._invoke(
            "send_location_template",
            "location_template",
            target,
            {
                "template_name": template_name,
                "target": target,
                "latitude": latitude,
                "longitude": longitude,
                "name": name,
                "address": address,
                "body_parameters": body_parameters,
                "language_code": language_code,
                **kw,
            },
            keyword_only=kw,
        )


class _PipelineUserDataRequests(IUserDataRequests):
    """User-data request capability that still runs the message middleware."""

    def __init__(self, pipeline: MessengerPipeline) -> None:
        self._pipeline = pipeline

    async def send_location_request(
        self,
        body: str,
        target: DirectMessage,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        return await self._pipeline._invoke(
            "send_location_request",
            "location_request",
            target,
            {
                "body": body,
                "target": target,
                "reply_to_message_id": reply_to_message_id,
            },
        )

    async def send_contact_request(
        self,
        body: str,
        target: DirectMessage,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        return await self._pipeline._invoke(
            "send_contact_request",
            "request_contact_info",
            target,
            {
                "body": body,
                "target": target,
                "reply_to_message_id": reply_to_message_id,
            },
        )
