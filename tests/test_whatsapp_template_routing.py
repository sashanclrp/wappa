from __future__ import annotations

import pytest
from pydantic import ValidationError

from wappa.messaging.whatsapp.handlers.whatsapp_template_handler import (
    WhatsAppTemplateHandler,
)
from wappa.messaging.whatsapp.models.template_models import (
    TextTemplateMessage,
    WhatsAppTemplateType,
)


class _DummyUrlBuilder:
    def get_marketing_messages_url(self) -> str:
        return "https://graph.facebook.com/v99/123/marketing_messages"


class _DummyClient:
    def __init__(self) -> None:
        self.url_builder = _DummyUrlBuilder()
        self.last_custom_url: str | None = None

    async def post_request(self, payload, custom_url=None):
        self.last_custom_url = custom_url
        return {
            "messages": [{"id": "wamid.test"}],
            "contacts": [{"input": "573001112233", "wa_id": "573001112233"}],
        }


def _build_handler() -> tuple[WhatsAppTemplateHandler, _DummyClient]:
    client = _DummyClient()
    return WhatsAppTemplateHandler(client=client, tenant_id="tenant-1"), client


@pytest.mark.asyncio
async def test_marketing_template_uses_marketing_messages_by_default() -> None:
    handler, client = _build_handler()

    result = await handler.send_text_template(
        recipient="573001112233",
        template_name="promo_template",
        template_type=WhatsAppTemplateType.MARKETING,
    )

    assert result.success is True
    assert client.last_custom_url is not None
    assert client.last_custom_url.endswith("/marketing_messages")


@pytest.mark.asyncio
async def test_marketing_template_override_false_uses_messages() -> None:
    handler, client = _build_handler()

    result = await handler.send_text_template(
        recipient="573001112233",
        template_name="promo_template",
        template_type=WhatsAppTemplateType.MARKETING,
        override=False,
    )

    assert result.success is True
    assert client.last_custom_url is None


def test_non_marketing_override_true_is_rejected() -> None:
    with pytest.raises(ValidationError, match="only compatible"):
        TextTemplateMessage(
            recipient="573001112233",
            template_name="utility_template",
            template_type=WhatsAppTemplateType.UTILITY,
            override=True,
        )
