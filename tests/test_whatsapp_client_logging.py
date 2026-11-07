"""WhatsApp failures are logged once, by the shared Meta transport (ADR-0029)."""

import logging

import httpx
import pytest

from wappa.messaging.meta.graph import MetaGraphError
from wappa.messaging.whatsapp.client import WhatsAppClient

TOKEN = "1234567890abcdefghijklmnopqrstuvwxyz"


@pytest.mark.asyncio
async def test_post_request_logs_meta_error_details_and_never_the_token(caplog) -> None:
    body = {
        "error": {
            "message": "(#100) Invalid parameter",
            "type": "OAuthException",
            "code": 100,
            "error_data": {"details": 'Unexpected key "recipient" on param.'},
            "fbtrace_id": "A1B2C3",
        }
    }
    session = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _r: httpx.Response(400, json=body))
    )
    client = WhatsAppClient(
        session=session,
        access_token=TOKEN,
        phone_number_id="493419253863068",
        logger=logging.getLogger("tests.whatsapp_client"),
    )

    with caplog.at_level(logging.DEBUG), pytest.raises(MetaGraphError) as caught:
        await client.post_request(
            {
                "messaging_product": "whatsapp",
                "type": "text",
                "text": {"body": "Welcome to Wappa", "preview_url": False},
                "recipient": "CO.2186878922080769",
            }
        )

    assert caught.value.code == "100" and caught.value.status_code == 400
    assert "Meta rejected WhatsApp text send (HTTP 400)" in caplog.text
    assert "Unexpected key" in caplog.text and "A1B2C3" in caplog.text
    assert TOKEN not in caplog.text
    assert TOKEN[:20] not in caplog.text


async def test_provider_echo_and_request_payload_do_not_log_the_address(caplog):
    phone = "573168227670"
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                400,
                json={
                    "error": {
                        "code": 131030,
                        "message": f"Rejected {phone}",
                        "error_data": {"details": f"Address {phone} is not allowed"},
                    }
                },
            )
        )
    ) as session:
        client = WhatsAppClient(
            session=session, access_token=TOKEN, phone_number_id="test-inbox"
        )
        with caplog.at_level(logging.DEBUG), pytest.raises(MetaGraphError):
            await client.post_request(
                {"type": "text", "to": phone, "text": {"body": "hi"}}
            )
    assert phone not in caplog.text
    assert "[redacted]" in caplog.text
