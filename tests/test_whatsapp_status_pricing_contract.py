"""Contract for the ``pricing`` object Meta sends on WhatsApp status webhooks."""

import logging

import pytest

from wappa.processors.base_processor import ProcessorError
from wappa.processors.whatsapp_processor import WhatsAppWebhookProcessor
from wappa.webhooks.whatsapp.status_models import WhatsAppMessageStatus


def _status_payload(pricing: dict) -> dict:
    return {
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
                            "statuses": [
                                {
                                    "id": "wamid.status-pricing-001",
                                    "status": "delivered",
                                    "timestamp": "1793980848",
                                    "recipient_id": "573001234567",
                                    "pricing": pricing,
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }


def _pricing(**extra: object) -> dict:
    return {
        "billable": False,
        "pricing_model": "PMP",
        "type": "free_customer_service",
        "category": "service",
        **extra,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "extra",
    [
        pytest.param({"subtype": "free_tier"}, id="observed-free-tier"),
        pytest.param({"subtype": "paid_exempt"}, id="documented-paid-exempt"),
        pytest.param({"subtype": None}, id="null-subtype"),
        pytest.param({}, id="no-subtype"),
    ],
)
async def test_status_webhook_accepts_pricing_subtype(
    extra: dict, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.CRITICAL):
        webhook = await WhatsAppWebhookProcessor().create_universal_webhook(
            _status_payload(_pricing(**extra))
        )

    assert webhook.message_id == "wamid.status-pricing-001"
    assert "WHATSAPP_WEBHOOK_CONTRACT_DRIFT" not in caplog.text


def test_status_info_exposes_pricing_subtype() -> None:
    status = WhatsAppMessageStatus.model_validate(
        {
            "id": "wamid.status-pricing-002",
            "status": "delivered",
            "timestamp": "1793980848",
            "recipient_id": "573001234567",
            "pricing": _pricing(subtype="free_tier"),
        }
    )

    assert status.get_delivery_info()["pricing"]["subtype"] == "free_tier"


@pytest.mark.asyncio
async def test_pricing_schema_still_rejects_unknown_fields(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """``subtype`` is an addition, not a relaxation of ``extra="forbid"``."""
    with caplog.at_level(logging.CRITICAL), pytest.raises(ProcessorError):
        await WhatsAppWebhookProcessor().create_universal_webhook(
            _status_payload(_pricing(surprise_field="anything"))
        )
