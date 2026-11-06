"""Inbound WhatsApp models accept what Meta delivers (ADR-0023).

Send-side limits (button title 20, row title 24, caption 1024...) belong to the
outbound models. Enforcing them on inbound webhooks turned valid deliveries into
400s, which Meta retries and then drops.
"""

from __future__ import annotations

import pytest

from wappa.processors.whatsapp_processor import WhatsAppWebhookProcessor
from wappa.webhooks.whatsapp.message_types.interactive import (
    WhatsAppInteractiveMessage,
)

# The routed Inbox the runtime passes to translate().
INBOX_ID = "routed-inbox"


def _payload(message: dict) -> dict:
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
                                "display_phone_number": "15551889071",
                                "phone_number_id": "508386009032748",
                            },
                            "contacts": [
                                {
                                    "profile": {"name": "Test User"},
                                    "wa_id": "573001112233",
                                    "user_id": "CO.2186878922080769",
                                }
                            ],
                            "messages": [
                                {
                                    "from": "573001112233",
                                    "from_user_id": "CO.2186878922080769",
                                    "id": "wamid.inbound-tolerance-001",
                                    "timestamp": "1776696189",
                                    **message,
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }


def _interactive(interactive: dict) -> dict:
    return {
        "type": "interactive",
        "context": {"from": "15551889071", "id": "wamid.sent-list-001"},
        "interactive": interactive,
    }


async def _parse(message: dict):
    return await WhatsAppWebhookProcessor().translate(
        _payload(message), inbox_id=INBOX_ID
    )


@pytest.mark.asyncio
async def test_list_reply_without_description_parses() -> None:
    """Live payload: a row sent without a description comes back without one."""
    webhook = await _parse(
        _interactive(
            {
                "type": "list_reply",
                "list_reply": {"id": "form:service:chatbot", "title": "Chatbot"},
            }
        )
    )

    assert isinstance(webhook.message, WhatsAppInteractiveMessage)
    assert webhook.message.selected_option_id == "form:service:chatbot"
    assert webhook.message.get_list_data() == (
        "form:service:chatbot",
        "Chatbot",
        None,
    )


@pytest.mark.asyncio
async def test_list_reply_with_description_keeps_it() -> None:
    webhook = await _parse(
        _interactive(
            {
                "type": "list_reply",
                "list_reply": {
                    "id": "row-1",
                    "title": "Plan",
                    "description": "Monthly plan",
                },
            }
        )
    )

    assert webhook.message.get_list_data() == ("row-1", "Plan", "Monthly plan")


@pytest.mark.asyncio
async def test_inbound_does_not_enforce_send_side_title_limits() -> None:
    long_title = "A button title longer than twenty characters"
    button = await _parse(
        _interactive(
            {"type": "button_reply", "button_reply": {"id": "b1", "title": long_title}}
        )
    )
    row = await _parse(
        _interactive(
            {
                "type": "list_reply",
                "list_reply": {
                    "id": "r1",
                    "title": "A row title longer than twenty-four",
                    "description": "x" * 100,
                },
            }
        )
    )

    assert button.message.selected_option_title == long_title
    assert row.message.get_list_data()[2] == "x" * 100


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message",
    [
        {"type": "text", "text": {"body": "x" * 5000}},
        {
            "type": "document",
            "document": {
                "id": "1234567890123456",
                "mime_type": "application/pdf",
                "sha256": "q2iEbX9N4uY8y5dyJ6tYwA7tkKcI3wL9vZ3k1mJ2p0s=",
                "filename": ("f" * 300) + ".pdf",
                "caption": "c" * 2000,
            },
        },
        {
            "type": "image",
            "image": {
                "id": "1234567890123456",
                "mime_type": "image/jpeg",
                "sha256": "q2iEbX9N4uY8y5dyJ6tYwA7tkKcI3wL9vZ3k1mJ2p0s=",
                "caption": "c" * 2000,
            },
        },
        {
            "type": "video",
            "video": {
                "id": "1234567890123456",
                "mime_type": "video/mp4",
                "sha256": "q2iEbX9N4uY8y5dyJ6tYwA7tkKcI3wL9vZ3k1mJ2p0s=",
                "caption": "c" * 2000,
            },
        },
        {
            "type": "location",
            "location": {
                "latitude": 4.6,
                "longitude": -74.08,
                "name": "n" * 300,
                "address": "a" * 1200,
            },
        },
    ],
    ids=["text", "document", "image", "video", "location"],
)
async def test_inbound_does_not_enforce_send_side_length_limits(message) -> None:
    webhook = await _parse(message)

    assert webhook.message is not None


_UNMODELLED_REPLY = {
    "type": "product_reply",
    "product_reply": {"id": "sku-1"},
}

_FLOW_REPLY = {
    "type": "nfm_reply",
    "nfm_reply": {
        "name": "flow",
        "body": "Sent",
        "response_json": '{"flow_token": "intake:42", "plan": "team"}',
    },
}


@pytest.mark.asyncio
async def test_flow_reply_arrives_typed_with_its_token_as_selection() -> None:
    from wappa.schemas.core.types import InteractiveType, MessageType
    from wappa.webhooks.whatsapp.message_types.interactive import (
        WhatsAppInteractiveMessage,
    )

    webhook = await _parse(_interactive(_FLOW_REPLY))

    message = webhook.message
    assert isinstance(message, WhatsAppInteractiveMessage)
    assert message.message_type is MessageType.INTERACTIVE
    assert message.is_flow_reply
    assert message.interactive_type is InteractiveType.FLOW_REPLY
    reply = message.interactive.nfm_reply
    assert reply is not None
    assert reply.response == {"flow_token": "intake:42", "plan": "team"}
    assert reply.flow_token == "intake:42"
    assert webhook.get_interactive_selection() == "intake:42"


@pytest.mark.asyncio
async def test_flow_reply_with_undecodable_answers_is_still_delivered() -> None:
    broken = {
        "type": "nfm_reply",
        "nfm_reply": {"name": "flow", "body": "Sent", "response_json": "{oops"},
    }

    webhook = await _parse(_interactive(broken))

    assert webhook.message.interactive.nfm_reply.response == {}
    assert not webhook.get_interactive_selection()


@pytest.mark.asyncio
async def test_unmodelled_interactive_type_is_unsupported_not_400(monkeypatch) -> None:
    """An interactive reply type Wappa does not model is Unsupported, never a 400."""
    from wappa.schemas.core.types import MessageType
    from wappa.webhooks.whatsapp.message_types.unsupported import (
        WhatsAppUnsupportedMessage,
    )

    monkeypatch.delenv("WAPPA_STRICT_META_SCHEMA", raising=False)
    webhook = await _parse(_interactive(_UNMODELLED_REPLY))

    assert isinstance(webhook.message, WhatsAppUnsupportedMessage)
    assert webhook.message.message_type is MessageType.UNSUPPORTED
    assert webhook.message.is_unknown_message_type()
    assert webhook.message.unsupported["interactive"] == _UNMODELLED_REPLY


@pytest.mark.asyncio
async def test_unmodelled_interactive_type_fails_in_strict_mode(monkeypatch) -> None:
    from wappa.processors.errors import ProcessorError

    monkeypatch.setenv("WAPPA_STRICT_META_SCHEMA", "1")
    with pytest.raises(ProcessorError, match="InteractiveContent.type=product_reply"):
        await _parse(_interactive(_UNMODELLED_REPLY))


@pytest.mark.asyncio
async def test_carousel_quick_reply_tap_is_a_selection() -> None:
    """Live 13:17: a carousel card tap arrives as type=button with a payload."""
    webhook = await _parse(
        {
            "type": "button",
            "context": {"from": "15551889071", "id": "wamid.sent-carousel-001"},
            "button": {"payload": "lab:plan:team", "text": "Choose"},
        }
    )

    assert webhook.get_interactive_selection() == "lab:plan:team"
    assert webhook.get_message_text() == "Choose"
    assert webhook.message.interactive_type.value == "quick_reply"


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["informe..final.pdf", "a/b.pdf", None])
async def test_any_document_filename_is_accepted(name: str | None) -> None:
    document = {
        "id": "1234567890123456",
        "mime_type": "application/pdf",
        "sha256": "q2iEbX9N4uY8y5dyJ6tYwA7tkKcI3wL9vZ3k1mJ2p0s=",
    }
    if name is not None:
        document["filename"] = name
    webhook = await _parse({"type": "document", "document": document})

    assert webhook.message.filename == name


def _status_payload(status: str) -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "1831186907601026",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "15551889071",
                                "phone_number_id": "508386009032748",
                            },
                            "statuses": [
                                {
                                    "id": "wamid.HBgMNTczMTY4MjI3NjcwFQIAERgSNEE4MzlGMjY0",
                                    "status": status,
                                    "timestamp": "1793907357",
                                    "recipient_id": "573168227670",
                                    "recipient_user_id": "CO.862165913565991",
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }


@pytest.mark.asyncio
async def test_played_status_is_a_status_webhook() -> None:
    """Live 14:35: a played voice note sends status=played (was a 400)."""
    from wappa.schemas.core.types import MessageStatus
    from wappa.webhooks.core.webhook_interfaces import StatusWebhook

    webhook = await WhatsAppWebhookProcessor().translate(
        _status_payload("played"), inbox_id=INBOX_ID
    )

    assert isinstance(webhook, StatusWebhook)
    assert webhook.status is MessageStatus.PLAYED


@pytest.mark.asyncio
async def test_unknown_status_is_unsupported_not_400(monkeypatch) -> None:
    from wappa.webhooks.core.webhook_interfaces import SystemEventType, SystemWebhook

    monkeypatch.delenv("WAPPA_STRICT_META_SCHEMA", raising=False)
    webhook = await WhatsAppWebhookProcessor().translate(
        _status_payload("archived"), inbox_id=INBOX_ID
    )

    assert isinstance(webhook, SystemWebhook)
    assert webhook.system_event_type is SystemEventType.UNSUPPORTED_EVENT
    assert webhook.event_detail.platform_event["status"]["status"] == "archived"
