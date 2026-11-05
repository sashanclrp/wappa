"""Tests for template send through MessengerPipeline with keyword-only arguments."""

from __future__ import annotations

import pytest

from wappa.core.messaging.pipeline import MessengerPipeline, SendInvocation
from wappa.domain.inbox import InboxRef
from wappa.messaging import DeliveryAddresses, DirectMessage, ITemplateMessaging
from wappa.messaging.whatsapp.models.basic_models import MessageResult
from wappa.schemas.core.types import PlatformType


class _StrictTemplateMessenger:
    """Mock messenger that enforces keyword-only Template routing values."""

    platform = PlatformType.WHATSAPP
    inbox_id = "test-inbox"

    def capability(self, kind):  # noqa: ANN001, ANN201 - test double
        return self

    def require_capability(self, kind):  # noqa: ANN001, ANN201 - test double
        return self

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
        return MessageResult(success=True, message_id="text-tmpl-ok")

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
        return MessageResult(success=True, message_id="media-tmpl-ok")

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
        return MessageResult(success=True, message_id="loc-tmpl-ok")


@pytest.fixture
def pipeline():
    return MessengerPipeline(raw=_StrictTemplateMessenger())


class TestTemplatePipelineKeywordArgs:
    @pytest.mark.asyncio
    async def test_text_template_through_pipeline(self, pipeline):
        result = await pipeline.require_capability(
            ITemplateMessaging
        ).send_text_template(
            template_name="welcome",
            target=DirectMessage(
                inbox_ref=InboxRef.whatsapp("test-inbox"),
                addresses=DeliveryAddresses.of("+1234567890"),
            ),
            template_type="marketing",
        )
        assert result.success
        assert result.message_id == "text-tmpl-ok"

    @pytest.mark.asyncio
    async def test_media_template_through_pipeline(self, pipeline):
        result = await pipeline.require_capability(
            ITemplateMessaging
        ).send_media_template(
            template_name="promo",
            target=DirectMessage(
                inbox_ref=InboxRef.whatsapp("test-inbox"),
                addresses=DeliveryAddresses.of("+1234567890"),
            ),
            media_type="image",
            media_url="https://example.com/img.png",
            template_type="utility",
        )
        assert result.success
        assert result.message_id == "media-tmpl-ok"

    @pytest.mark.asyncio
    async def test_location_template_through_pipeline(self, pipeline):
        result = await pipeline.require_capability(
            ITemplateMessaging
        ).send_location_template(
            template_name="store_loc",
            target=DirectMessage(
                inbox_ref=InboxRef.whatsapp("test-inbox"),
                addresses=DeliveryAddresses.of("+1234567890"),
            ),
            latitude="4.6097",
            longitude="-74.0817",
            name="HQ",
            address="Bogota",
            template_type="utility",
        )
        assert result.success
        assert result.message_id == "loc-tmpl-ok"

    @pytest.mark.asyncio
    async def test_template_send_with_middleware(self):
        captured: list[SendInvocation] = []

        class SpyMiddleware:
            name = "spy"

            async def handle(self, invocation: SendInvocation, call_next):
                captured.append(invocation)
                return await call_next(invocation)

        pipeline = MessengerPipeline(
            raw=_StrictTemplateMessenger(),
            middleware=[(SpyMiddleware(), 50)],
        )
        result = await pipeline.require_capability(
            ITemplateMessaging
        ).send_text_template(
            template_name="test",
            target=DirectMessage(
                inbox_ref=InboxRef.whatsapp("test-inbox"),
                addresses=DeliveryAddresses.of("+1234567890"),
            ),
            template_type="marketing",
            routing_policy="cloud_messages_fallback",
        )
        assert result.success
        assert len(captured) == 1
        inv = captured[0]
        assert inv.arguments["template_type"] == "marketing"
        assert inv.arguments["routing_policy"] == "cloud_messages_fallback"
        assert inv.kwargs["template_type"] == "marketing"
        assert inv.kwargs["routing_policy"] == "cloud_messages_fallback"
        # Middleware sees the authentication binding as a keyword-only value,
        # so a middleware may reason about OTP sends without re-parsing them.
        assert inv.kwargs["authentication_method"] is None
        assert inv.kwargs["authentication_button_index"] == 0
