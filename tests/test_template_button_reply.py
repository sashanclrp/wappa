"""Regression tests for template quick-reply ("button") messages.

Meta omits the `context` block when a user taps a quick-reply button on a
template message. The webhook must still parse instead of failing with 400.
"""

from __future__ import annotations

from typing import Any

import pytest

from wappa.processors.whatsapp_processor import WhatsAppWebhookProcessor
from wappa.schemas.core.types import MessageType
from wappa.webhooks.whatsapp.message_types.button import WhatsAppButtonMessage

MESSAGE_ID = "wamid.HBgMNTczMDAyNDA5MDEyFQIAEhgUMEExITEST0BUT09OMDBFRTAwQgA="


def _button_message(context: dict[str, Any] | None = None) -> dict[str, Any]:
    message: dict[str, Any] = {
        "from": "573002409012",
        "id": MESSAGE_ID,
        "timestamp": "1753375021",
        "type": "button",
        "button": {"payload": "QUIERO PROMO SUERO", "text": "QUIERO PROMO SUERO"},
    }
    if context is not None:
        message["context"] = context
    return message


def _payload(message: dict[str, Any]) -> dict[str, Any]:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "114814944889265",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "573138301772",
                                "phone_number_id": "110693698598080",
                            },
                            "contacts": [
                                {
                                    "profile": {"name": "Cliente"},
                                    "wa_id": "573002409012",
                                }
                            ],
                            "messages": [message],
                        },
                    }
                ],
            }
        ],
    }


def test_button_message_parses_without_context() -> None:
    message = WhatsAppButtonMessage.model_validate(_button_message())

    assert message.button_text == "QUIERO PROMO SUERO"
    assert message.button_payload == "QUIERO PROMO SUERO"
    assert message.text_content == "QUIERO PROMO SUERO"
    assert message.has_context() is False
    assert message.original_message_id is None
    assert message.business_phone is None
    assert message.get_button_context() == (None, None)
    assert message.get_platform_data()["context"] is None
    assert message.to_universal_dict()["whatsapp_data"]["context"] is None


def test_button_message_keeps_context_when_present() -> None:
    context = {"from": "573138301772", "id": "wamid.HBgMNTczMDAyNDA5MDEyFQIAERgS"}
    message = WhatsAppButtonMessage.model_validate(_button_message(context))

    assert message.has_context() is True
    assert message.original_message_id == context["id"]
    assert message.business_phone == context["from"]
    assert message.get_button_context() == (context["from"], context["id"])


def test_forwarded_button_context_still_rejected() -> None:
    context = {
        "from": "573138301772",
        "id": "wamid.HBgMNTczMDAyNDA5MDEyFQIAERgS",
        "forwarded": True,
    }

    with pytest.raises(ValueError, match="cannot be forwarded"):
        WhatsAppButtonMessage.model_validate(_button_message(context))


@pytest.mark.asyncio
async def test_universal_webhook_exposes_button_text() -> None:
    processor = WhatsAppWebhookProcessor()

    webhook = await processor.create_universal_webhook(_payload(_button_message()))

    assert webhook.message.message_type is MessageType.BUTTON
    assert webhook.get_message_text() == "QUIERO PROMO SUERO"
    assert webhook.user.user_id == "573002409012"
