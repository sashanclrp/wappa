import pytest

from wappa.processors.whatsapp_processor import WhatsAppWebhookProcessor
from wappa.webhooks.whatsapp.webhook_container import WhatsAppWebhook


def test_create_user_base_from_contacts_preserves_wa_id_when_bsuid_exists() -> None:
    processor = WhatsAppWebhookProcessor()
    webhook = WhatsAppWebhook.model_validate(
        {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "id": "535497026314662",
                    "changes": [
                        {
                            "field": "messages",
                            "value": {
                                "messaging_product": "whatsapp",
                                "metadata": {
                                    "display_phone_number": "573232821994",
                                    "phone_number_id": "508386009032748",
                                },
                                "contacts": [
                                    {
                                        "profile": {"name": "Sasha Nicolai Canal"},
                                        "wa_id": "573168227670",
                                        "user_id": "CO.2186878922080769",
                                    }
                                ],
                                "messages": [
                                    {
                                        "from": "573168227670",
                                        "from_user_id": "CO.2186878922080769",
                                        "id": "wamid.test",
                                        "timestamp": "1776696189",
                                        "text": {"body": "Hola"},
                                        "type": "text",
                                    }
                                ],
                            },
                        }
                    ],
                }
            ],
        }
    )

    user = processor._create_user_base_from_contacts(
        webhook, "CO.2186878922080769"
    )

    assert user.bsuid == "CO.2186878922080769"
    assert user.platform_user_id == "573168227670"
    assert user.phone_number == "573168227670"
    assert user.user_id == "CO.2186878922080769"


@pytest.mark.asyncio
async def test_create_universal_webhook_accepts_contact_without_profile() -> None:
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "535497026314662",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "573232821994",
                                "phone_number_id": "508386009032748",
                            },
                            "contacts": [
                                {
                                    "wa_id": "573168227670",
                                    "user_id": "CO.2186878922080769",
                                }
                            ],
                            "messages": [
                                {
                                    "from": "573168227670",
                                    "from_user_id": "CO.2186878922080769",
                                    "id": "wamid.test",
                                    "timestamp": "1776696189",
                                    "text": {"body": "Hola"},
                                    "type": "text",
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }

    processor = WhatsAppWebhookProcessor()
    webhook = await processor.create_universal_webhook(payload)

    assert webhook.user.user_id == "CO.2186878922080769"
    assert webhook.user.platform_user_id == "573168227670"
    assert webhook.user.phone_number == "573168227670"
