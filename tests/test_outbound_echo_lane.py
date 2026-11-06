"""OutboundEchoWebhook: one lane for messages the business sent outside Wappa."""

from __future__ import annotations

from wappa.domain.inbox.identity import InboxRef
from wappa.processors.whatsapp_processor import WhatsAppWebhookProcessor
from wappa.schemas.core.types import MessageType, PlatformType
from wappa.webhooks import EchoOrigin, OutboundEchoWebhook

PHONE_ID = "1234567890"
REF = InboxRef(platform=PlatformType.INSTAGRAM, inbox_id="17841400000000000")


def _wa_echo(message: dict) -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "102290129340398",
                "changes": [
                    {
                        "field": "smb_message_echoes",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "15550001111",
                                "phone_number_id": PHONE_ID,
                            },
                            "contacts": [
                                {"profile": {"name": "Ana"}, "wa_id": "573001112233"}
                            ],
                            "message_echoes": [message],
                        },
                    }
                ],
            }
        ],
    }


async def test_whatsapp_text_echo_is_typed_with_the_inbound_model():
    echo = await WhatsAppWebhookProcessor().translate(
        _wa_echo(
            {
                "from": "15550001111",
                "to": "573001112233",
                "id": "wamid.HBgLNTczMDAxMTEyMjMzFQIAERgSQUJD",
                "timestamp": "1776696189",
                "type": "text",
                "text": {"body": "I'll take it from here"},
            }
        ),
        inbox_id=INBOX_ID,
    )
    assert isinstance(echo, OutboundEchoWebhook)
    assert echo.origin is EchoOrigin.BUSINESS_APP and echo.is_from_business_app
    assert echo.message_type is MessageType.TEXT
    assert echo.get_text() == "I'll take it from here"
    assert echo.user.user_id == "573001112233"
    assert echo.inbox.inbox_id == PHONE_ID


async def test_whatsapp_outbound_only_shape_keeps_native_type_without_raw_dict():
    echo = await WhatsAppWebhookProcessor().translate(
        _wa_echo(
            {
                "from": "15550001111",
                "to": "573001112233",
                "id": "wamid.HBgLNTczMDAxMTEyMjMzFQIAERgSQUJE",
                "timestamp": "1776696189",
                "type": "interactive",
                "interactive": {"type": "button", "body": {"text": "Pick one"}},
            }
        ),
        inbox_id=INBOX_ID,
    )
    assert isinstance(echo, OutboundEchoWebhook)
    assert echo.native_type == "interactive"
    assert echo.message is None


async def test_instagram_echo_starts_unknown_until_the_runtime_proves_it():
    from wappa.processors.instagram_processor import InstagramWebhookProcessor

    echo = await InstagramWebhookProcessor().translate(
        {
            "object": "instagram",
            "entry": [
                {
                    "id": REF.inbox_id,
                    "time": 1793710000,
                    "messaging": [
                        {
                            "sender": {"id": REF.inbox_id},
                            "recipient": {"id": "IGSID1"},
                            "timestamp": 1793710000123,
                            "message": {"mid": "m1", "text": "hi", "is_echo": True},
                        }
                    ],
                }
            ],
        },
        inbox_id=INBOX_ID,
    )
    assert isinstance(echo, OutboundEchoWebhook)
    assert echo.origin is EchoOrigin.UNKNOWN  # proven by the runtime
    assert not echo.is_from_business_app
    assert echo.get_text() == "hi" and echo.user.user_id == "IGSID1"


# ── fixed filter (ADR-0023) ──────────────────────────────────────────────

from datetime import UTC, datetime  # noqa: E402
from types import SimpleNamespace  # noqa: E402

import pytest  # noqa: E402

import wappa.core.inbound.runtime as inbound_runtime  # noqa: E402
from wappa.core.inbound.runtime import InboundRuntime  # noqa: E402
from wappa.core.messaging.sent_message_registry import (  # noqa: E402
    CLAIMED_GRACE_SECONDS,
    SENT_MESSAGES_TABLE,
    TableSentMessageRegistry,
)
from wappa.domain.interfaces.sent_message_registry import (  # noqa: E402
    ISentMessageRegistry,
)
from wappa.webhooks.core.webhook_interfaces.base_components import (  # noqa: E402
    InboxBase,
    UserBase,
)

# The routed Inbox the runtime passes to translate().
INBOX_ID = "routed-inbox"


class _Registry(ISentMessageRegistry):
    def __init__(self, sent=(), fail=False):
        self.sent, self.fail = set(sent), fail

    async def record(self, inbox_ref, message_id):
        self.sent.add(message_id)

    async def claim(self, inbox_ref, message_id):
        if self.fail:
            raise ConnectionError("redis down")
        return message_id in self.sent


def _ig_echo(mid, origin=EchoOrigin.UNKNOWN):
    return OutboundEchoWebhook(
        inbox=InboxBase(
            inbox_id=REF.inbox_id, display_address="biz", platform_account_id="acc"
        ),
        user=UserBase(platform_user_id="IGSID1"),
        message_id=mid,
        native_type="text",
        origin=origin,
        timestamp=datetime.now(UTC),
        platform=PlatformType.INSTAGRAM,
        webhook_id=f"echo:{mid}",
    )


@pytest.fixture
def runtime(monkeypatch):
    monkeypatch.setattr(inbound_runtime, "ECHO_SETTLE_DELAYS_SECONDS", (0.01,))
    return InboundRuntime(SimpleNamespace(event_handler=None))


def _ctx(registry=None):
    return SimpleNamespace(inbox_ref=REF, sent_message_registry=registry)


async def test_registry_drops_own_send_and_proves_the_rest(runtime):
    registry = _Registry(sent={"mine"})
    assert await runtime._is_wappa_send(_ig_echo("mine"), _ctx(registry))
    theirs = _ig_echo("theirs")
    assert not await runtime._is_wappa_send(theirs, _ctx(registry))
    assert theirs.origin is EchoOrigin.BUSINESS_APP


async def test_registry_outage_delivers_unknown_instead_of_losing_it(runtime):
    echo = _ig_echo("x")
    assert not await runtime._is_wappa_send(echo, _ctx(_Registry(fail=True)))
    assert echo.origin is EchoOrigin.UNKNOWN


async def test_whatsapp_coexistence_echo_is_never_looked_up(runtime):
    echo = _ig_echo("x", origin=EchoOrigin.BUSINESS_APP)
    assert not await runtime._is_wappa_send(echo, _ctx(_Registry(fail=True)))


async def test_table_registry_one_key_per_send_retired_on_claim():
    ttls: dict[tuple[str, str], int] = {}

    class Table:
        async def upsert(self, table, pkid, data, ttl=None):
            assert table == SENT_MESSAGES_TABLE
            ttls[(table, pkid)] = ttl
            return True

        async def renew_ttl(self, table, pkid, ttl):
            if (table, pkid) not in ttls:
                return False
            ttls[(table, pkid)] = ttl
            return True

    registry = TableSentMessageRegistry(lambda ref: Table(), ttl_seconds=600)
    await registry.record(REF, "m1")
    await registry.record(REF, "m2")
    assert ttls == {(SENT_MESSAGES_TABLE, "m1"): 600, (SENT_MESSAGES_TABLE, "m2"): 600}
    assert await registry.claim(REF, "m1")
    assert ttls[(SENT_MESSAGES_TABLE, "m1")] == CLAIMED_GRACE_SECONDS  # retired
    assert ttls[(SENT_MESSAGES_TABLE, "m2")] == 600  # echo not seen yet
    assert not await registry.claim(REF, "never-sent")

    def broken(ref):
        raise RuntimeError("cache not ready")

    await TableSentMessageRegistry(broken).record(REF, "m1")  # swallowed
