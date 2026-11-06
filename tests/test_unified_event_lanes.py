"""ADR-0025 unification: history backfill, connection changes, typed payloads."""

from __future__ import annotations

import httpx
import pytest
from pydantic import SecretStr

from wappa.domain.inbox.identity import InboxRef
from wappa.domain.interfaces.conversation_capabilities import ReadOutcome
from wappa.messaging import IConversationHistoryReader
from wappa.messaging.instagram.messenger import InstagramMessengerAdapter
from wappa.schemas.core.types import MessageType, PlatformType
from wappa.webhooks import (
    EntryPointKind,
    HistoryDirection,
    HistorySyncWebhook,
    InboundMessageWebhook,
    MessageUpdateKind,
    MessageUpdateWebhook,
)
from wappa.webhooks.whatsapp.processor import WhatsAppWebhookProcessor

# The routed Inbox the runtime passes to translate().
INBOX_ID = "routed-inbox"

ACCOUNT = "17841400000000000"
IG_REF = InboxRef(platform=PlatformType.INSTAGRAM, inbox_id=ACCOUNT)
PHONE_ID = "1234567890"
BUSINESS = "15550001111"


def _wa(field: str, value: dict) -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "102290129340398",
                "changes": [
                    {
                        "field": field,
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": BUSINESS,
                                "phone_number_id": PHONE_ID,
                            },
                            **value,
                        },
                    }
                ],
            }
        ],
    }


async def test_whatsapp_text_edit_is_a_message_update_with_typed_replacement():
    webhook = await WhatsAppWebhookProcessor().translate(
        _wa(
            "messages",
            {
                "contacts": [{"profile": {"name": "Ana"}, "wa_id": "573001112233"}],
                "messages": [
                    {
                        "from": "573001112233",
                        "id": "wamid.HBgLNTczMDAxMTEyMjMzFQIAEhgEZWRpdA",
                        "timestamp": "1776696189",
                        "type": "edit",
                        "edit": {
                            "original_message_id": "wamid.HBgLNTczMDAxMTEyMjMzFQIAEhgCT1I",
                            "message": {"type": "text", "text": {"body": "fixed"}},
                        },
                    }
                ],
            },
        ),
        inbox_id=INBOX_ID,
    )
    assert isinstance(webhook, MessageUpdateWebhook)
    assert webhook.update_kind is MessageUpdateKind.EDITED
    assert webhook.message_id == "wamid.HBgLNTczMDAxMTEyMjMzFQIAEhgCT1I"
    assert webhook.text == "fixed"
    assert webhook.message is not None
    assert webhook.message.message_type is MessageType.TEXT


async def test_whatsapp_ctwa_referral_fills_the_shared_entry_referral():
    webhook = await WhatsAppWebhookProcessor().translate(
        _wa(
            "messages",
            {
                "contacts": [{"profile": {"name": "Ana"}, "wa_id": "573001112233"}],
                "messages": [
                    {
                        "from": "573001112233",
                        "id": "wamid.HBgLNTczMDAxMTEyMjMzFQIAEhgDQ1RX",
                        "timestamp": "1776696189",
                        "type": "text",
                        "text": {"body": "Hi from the ad"},
                        "referral": {
                            "source_url": "https://fb.me/ad",
                            "source_id": "120200000",
                            "source_type": "ad",
                            "body": "Big sale",
                            "headline": "Sale",
                            "media_type": "image",
                            "image_url": "https://cdn/ad.jpg",
                            "ctwa_clid": "clid-1",
                            "welcome_message": {"text": "Hello!"},
                        },
                    }
                ],
            },
        ),
        inbox_id=INBOX_ID,
    )
    assert isinstance(webhook, InboundMessageWebhook)
    ref = webhook.entry_referral
    assert ref is not None and ref.kind is EntryPointKind.AD
    assert (ref.ad_id, ref.click_id, ref.headline) == ("120200000", "clid-1", "Sale")
    assert webhook.is_from_ad()


async def test_media_history_sync_builds_one_typed_thread():
    webhook = await WhatsAppWebhookProcessor().translate(
        _wa(
            "history",
            {
                "contacts": [{"profile": {"name": "Ana"}, "wa_id": "573001112233"}],
                "messages": [
                    {
                        "from": "573001112233",
                        "id": "wamid.HBgLNTczMDAxMTEyMjMzFQIAEhgCSU4",
                        "timestamp": "1776696100",
                        "type": "text",
                        "text": {"body": "old question"},
                    }
                ],
                "message_echoes": [
                    {
                        "from": BUSINESS,
                        "to": "573001112233",
                        "id": "wamid.HBgLNTczMDAxMTEyMjMzFQIAEhgDT1VU",
                        "timestamp": "1776696150",
                        "type": "text",
                        "text": {"body": "old answer"},
                    }
                ],
            },
        ),
        inbox_id=INBOX_ID,
    )
    assert isinstance(webhook, HistorySyncWebhook)
    (thread,) = webhook.threads
    assert [m.direction for m in thread.messages] == [
        HistoryDirection.INBOUND,
        HistoryDirection.OUTBOUND,
    ]
    assert thread.messages[1].message.text_content == "old answer"


async def test_instagram_history_reader_returns_the_shared_thread_shape():
    calls: list[httpx.Request] = []

    def transport(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path.endswith("/conversations"):
            return httpx.Response(200, json={"data": [{"id": "conv1"}]})
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "m2",
                        "created_time": "2026-11-05T10:01:00+0000",
                        "from": {"id": ACCOUNT},
                        "message": "answer",
                    },
                    {
                        "id": "m1",
                        "created_time": "2026-11-05T10:00:00+0000",
                        "from": {"id": "IGSID1"},
                        "message": "",
                        "attachments": {
                            "data": [{"image_data": {"url": "https://cdn/x.jpg"}}]
                        },
                    },
                ],
                "paging": {"cursors": {"after": "c2"}, "next": "https://next"},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
        messenger = InstagramMessengerAdapter(
            inbox_ref=IG_REF,
            access_token=SecretStr("tkn"),
            session_provider=lambda: client,
            graph_api_version="v26.0",
            graph_base_url="https://graph.facebook.com",
        )
        reader = messenger.require_capability(IConversationHistoryReader)
        result = await reader.read_history("IGSID1", limit=2)
    assert result.outcome is ReadOutcome.FOUND
    page = result.value
    assert page.next_cursor == "c2"
    out, inn = page.thread.messages
    assert out.direction is HistoryDirection.OUTBOUND
    assert out.message.text_content == "answer"
    assert inn.direction is HistoryDirection.INBOUND
    assert inn.message_type is MessageType.IMAGE
    assert calls[0].url.params["user_id"] == "IGSID1"
    with pytest.raises(ValueError):
        await reader.read_history("IGSID1", limit=21)
