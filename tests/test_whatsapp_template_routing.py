from __future__ import annotations

import pytest
from pydantic import ValidationError

from wappa.messaging import (
    PhoneNumberTemplateRecipient,
    TemplateCategory,
    TemplateEndpoint,
    TemplateRoutingPolicy,
    TemplateTransportRouting,
    TextTemplateTransportRequest,
)
from wappa.messaging.whatsapp.handlers.whatsapp_template_handler import (
    WhatsAppTemplateHandler,
)
from wappa.messaging.whatsapp.models.template_models import WhatsAppTemplateType


class _DummyUrlBuilder:
    def get_marketing_messages_url(self) -> str:
        return "https://graph.facebook.com/v99/123/marketing_messages"


class _DummyClient:
    def __init__(self) -> None:
        self.url_builder = _DummyUrlBuilder()
        self.last_custom_url: str | None = None
        self.calls: list[tuple[dict, str | None]] = []

    async def post_request(self, payload, custom_url=None):
        self.last_custom_url = custom_url
        self.calls.append((payload, custom_url))
        return {
            "messages": [{"id": "wamid.test"}],
            "contacts": [{"input": "573001112233", "wa_id": "573001112233"}],
        }


def _build_handler() -> tuple[WhatsAppTemplateHandler, _DummyClient]:
    client = _DummyClient()
    return WhatsAppTemplateHandler(client=client, inbox_id="inbox-1"), client


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
async def test_marketing_template_explicit_fallback_uses_messages() -> None:
    handler, client = _build_handler()

    result = await handler.send_text_template(
        recipient="573001112233",
        template_name="promo_template",
        template_type=WhatsAppTemplateType.MARKETING,
        routing_policy=TemplateRoutingPolicy.CLOUD_MESSAGES_FALLBACK.value,
    )

    assert result.success is True
    assert client.last_custom_url is None


def test_non_marketing_fallback_is_rejected() -> None:
    with pytest.raises(ValidationError, match="only valid for marketing"):
        TextTemplateTransportRequest(
            recipient=PhoneNumberTemplateRecipient(value="573001112233"),
            template_name="utility_template",
            category=TemplateCategory.UTILITY,
            routing=TemplateTransportRouting(
                policy=TemplateRoutingPolicy.CLOUD_MESSAGES_FALLBACK
            ),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("recipient", "field"),
    [("573001112233", "to"), ("CO.user123", "recipient")],
)
async def test_template_payload_uses_exact_recipient_field(
    recipient: str, field: str
) -> None:
    handler, client = _build_handler()

    await handler.send_text_template(
        recipient=recipient,
        template_name="utility_template",
        template_type=WhatsAppTemplateType.UTILITY,
    )

    payload, _ = client.calls[0]
    assert payload[field] == recipient
    assert ({"to", "recipient"} & payload.keys()) == {field}


@pytest.mark.asyncio
async def test_provider_response_never_triggers_cross_endpoint_retry() -> None:
    handler, client = _build_handler()

    await handler.send_text_template(
        recipient="573001112233",
        template_name="promo_template",
        template_type=WhatsAppTemplateType.MARKETING,
    )

    assert len(client.calls) == 1
    assert client.calls[0][1] is not None
    assert client.calls[0][1].endswith(f"/{TemplateEndpoint.MARKETING_MESSAGES.value}")
