"""Meta payloads parse tolerantly; schema drift is reported (ADR-0023)."""

import logging

import pytest
from pydantic import ValidationError

from wappa.processors.instagram_processor import InstagramWebhookProcessor
from wappa.processors.whatsapp_processor import WhatsAppWebhookProcessor
from wappa.webhooks import (
    InboundMessageWebhook,
    StatusWebhook,
    SystemEventType,
    SystemWebhook,
)
from wappa.webhooks.core import schema_drift
from wappa.webhooks.core.schema_drift import MetaSchemaDriftError
from wappa.webhooks.core.webhook_interfaces import SystemEventDetail

# The routed Inbox the runtime passes to translate().
INBOX_ID = "routed-inbox"

SECRET_VALUE = "personal-value-do-not-log"


@pytest.fixture(autouse=True)
def fresh_drift_log():
    schema_drift._reported.clear()
    yield
    schema_drift._reported.clear()


def _wa_status_payload() -> dict:
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
                                    "id": "wamid.status-001",
                                    "status": "delivered",
                                    "timestamp": "1776696189",
                                    "recipient_id": "573168227670",
                                    "brand_new_meta_field": SECRET_VALUE,
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }


def _wa_account_update_payload() -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "1831186907601026",
                "changes": [
                    {
                        "field": "account_update",
                        "value": {
                            "event": "SOME_EVENT",
                            "waba_info": {"waba_id": "1831186907601026"},
                        },
                    }
                ],
            }
        ],
    }


def _ig_payload(**extra) -> dict:
    return {
        "object": "instagram",
        "entry": [
            {
                "id": "17890001",
                "messaging": [
                    {
                        "sender": {"id": "12345"},
                        "recipient": {"id": "17890001"},
                        "timestamp": 1793710000123,
                        "message": {"mid": "ig.mid", "text": "hello"},
                        **extra,
                    }
                ],
            }
        ],
    }


@pytest.mark.asyncio
async def test_lax_mode_processes_status_with_unknown_field_and_logs_once(
    monkeypatch, caplog
):
    monkeypatch.setenv("WAPPA_STRICT_META_SCHEMA", "")
    processor = WhatsAppWebhookProcessor()

    with caplog.at_level(logging.WARNING):
        first = await processor.translate(_wa_status_payload(), inbox_id=INBOX_ID)
        second = await processor.translate(_wa_status_payload(), inbox_id=INBOX_ID)

    assert isinstance(first, StatusWebhook)
    assert isinstance(second, StatusWebhook)
    drift = [r for r in caplog.records if "META_SCHEMA_DRIFT" in r.getMessage()]
    assert len(drift) == 1
    assert "brand_new_meta_field" in drift[0].getMessage()
    assert SECRET_VALUE not in caplog.text


@pytest.mark.asyncio
async def test_strict_mode_raises_for_the_same_status_payload(monkeypatch):
    monkeypatch.setenv("WAPPA_STRICT_META_SCHEMA", "1")

    with pytest.raises(Exception) as excinfo:
        await WhatsAppWebhookProcessor().translate(
            _wa_status_payload(), inbox_id=INBOX_ID
        )

    chain = []
    exc: BaseException | None = excinfo.value
    while exc is not None:
        chain.append(exc)
        exc = exc.__cause__ or exc.__context__
    assert any(isinstance(e, MetaSchemaDriftError) for e in chain)
    assert "brand_new_meta_field" in str(excinfo.value)


@pytest.mark.asyncio
async def test_unknown_whatsapp_webhook_field_becomes_unsupported_event(
    monkeypatch, caplog
):
    monkeypatch.setenv("WAPPA_STRICT_META_SCHEMA", "")

    with caplog.at_level(logging.WARNING):
        webhook = await WhatsAppWebhookProcessor().translate(
            _wa_account_update_payload(), inbox_id=INBOX_ID
        )

    assert isinstance(webhook, SystemWebhook)
    assert webhook.system_event_type is SystemEventType.UNSUPPORTED_EVENT
    evidence = webhook.event_detail.platform_event
    assert evidence["field"] == "account_update"
    assert evidence["value"]["event"] == "SOME_EVENT"
    assert "META_SCHEMA_DRIFT" in caplog.text
    assert "webhook field 'account_update'" in caplog.text


@pytest.mark.asyncio
async def test_instagram_unknown_messaging_key_is_processed_and_reported_in_lax_mode(
    monkeypatch, caplog
):
    monkeypatch.setenv("WAPPA_STRICT_META_SCHEMA", "")

    with caplog.at_level(logging.WARNING):
        webhook = await InstagramWebhookProcessor().translate(
            _ig_payload(brand_new_ig_key={"secret": SECRET_VALUE}), inbox_id=INBOX_ID
        )

    assert isinstance(webhook, InboundMessageWebhook)
    assert webhook.get_message_text() == "hello"
    assert "META_SCHEMA_DRIFT" in caplog.text
    assert "brand_new_ig_key" in caplog.text
    assert SECRET_VALUE not in caplog.text


@pytest.mark.asyncio
async def test_instagram_unknown_key_raises_in_strict_mode(monkeypatch):
    monkeypatch.setenv("WAPPA_STRICT_META_SCHEMA", "1")

    with pytest.raises(Exception, match="brand_new_ig_key"):
        await InstagramWebhookProcessor().translate(
            _ig_payload(brand_new_ig_key=1), inbox_id=INBOX_ID
        )


def test_universal_webhook_output_models_still_forbid_extras():
    with pytest.raises(ValidationError):
        SystemEventDetail(unknown=1)


def test_instagram_card_echo_attachment_is_modelled():
    """Live echo of a generic-template card (2026-11-05) has no drift."""
    from wappa.webhooks.core.schema_drift import unmodelled_fields
    from wappa.webhooks.instagram.models import InstagramAttachment

    attachment = InstagramAttachment.model_validate(
        {
            "type": "template",
            "payload": {
                "generic": {
                    "elements": [
                        {
                            "title": "Wappa lab",
                            "buttons": [
                                {
                                    "type": "postback",
                                    "title": "Start form",
                                    "payload": "lab:form",
                                }
                            ],
                        }
                    ]
                }
            },
        }
    )

    assert unmodelled_fields(attachment) == []
    assert attachment.payload.generic.elements[0].buttons[0].payload == "lab:form"
