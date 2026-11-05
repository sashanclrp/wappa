"""ADR-0019: one explicit target carrying every known Delivery Address.

The WhatsApp adapter orders the addresses (phone, then BSUID) and moves to the
next one only when Meta rejects the address itself.
"""

from __future__ import annotations

import httpx
import pytest

from wappa.core.messaging.middleware.pubsub_notification import _destination_user
from wappa.core.messaging.pipeline import SendInvocation
from wappa.domain.inbox import InboxRef
from wappa.messaging import DeliveryAddresses, DirectMessage
from wappa.messaging.whatsapp.messenger.whatsapp_messenger import WhatsAppMessenger
from wappa.schemas.core.recipient import whatsapp_delivery_order
from wappa.schemas.core.types import PlatformType
from wappa.webhooks.core.webhook_interfaces.base_components import UserBase

PHONE = "573168227670"
BSUID = "CO.862165913565991"
WA = InboxRef.whatsapp("pnid")


def _rejection(code: int) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://graph.facebook.com/v26.0/pnid/messages")
    response = httpx.Response(
        400, request=request, json={"error": {"code": code, "message": "rejected"}}
    )
    return httpx.HTTPStatusError("400", request=request, response=response)


class _Client:
    """Rejects addresses listed in ``reject`` with the given Meta code."""

    def __init__(self, reject: dict[str, int] | None = None) -> None:
        self.reject = reject or {}
        self.posted: list[dict] = []

    async def post_request(self, payload: dict) -> dict:
        self.posted.append(payload)
        address = payload.get("to") or payload.get("recipient")
        if address in self.reject:
            raise _rejection(self.reject[address])
        return {"messages": [{"id": "wamid.out"}], "contacts": [{"input": address}]}


def _wa(client: _Client) -> WhatsAppMessenger:
    return WhatsAppMessenger(
        client=client,  # type: ignore[arg-type]
        media_handler=None,  # type: ignore[arg-type]
        interactive_handler=None,  # type: ignore[arg-type]
        template_handler=None,  # type: ignore[arg-type]
        specialized_handler=None,  # type: ignore[arg-type]
        inbox_id="pnid",
    )


def _both() -> DirectMessage:
    return DirectMessage(inbox_ref=WA, addresses=DeliveryAddresses.of(BSUID, PHONE))


def _sent_to(payload: dict) -> str:
    return payload.get("to") or payload["recipient"]


def test_webhook_user_yields_every_proven_address():
    wa_user = UserBase(phone_number=PHONE, bsuid=BSUID, parent_bsuid="CO.ENT.X1")
    assert wa_user.delivery_addresses().values == (BSUID, PHONE)
    assert UserBase(bsuid=BSUID).delivery_addresses().values == (BSUID,)
    ig_user = UserBase(platform_user_id="IGSID1")
    assert ig_user.delivery_addresses().values == ("IGSID1",)


def test_delivery_addresses_skip_unknowns_and_require_one():
    assert DeliveryAddresses.of(None, PHONE, " ", PHONE).values == (PHONE,)
    with pytest.raises(ValueError):
        DeliveryAddresses.of(None, "")


def test_whatsapp_order_is_phone_first_and_auth_is_phone_only():
    assert whatsapp_delivery_order((BSUID, PHONE)) == (PHONE, BSUID)
    assert whatsapp_delivery_order((BSUID, PHONE), phone_only=True) == (PHONE,)
    assert whatsapp_delivery_order((BSUID,), phone_only=True) == ()


async def test_phone_is_used_first_when_known():
    client = _Client()
    result = await _wa(client).send_text("hi", _both())
    assert result.success and result.attempted_recipients == ()
    assert [_sent_to(p) for p in client.posted] == [PHONE]


async def test_address_rejection_falls_back_to_the_next_address():
    client = _Client(reject={PHONE: 131030})  # test-number allow-list
    result = await _wa(client).send_text("hi", _both())
    assert result.success
    assert [_sent_to(p) for p in client.posted] == [PHONE, BSUID]
    assert client.posted[1]["recipient"] == BSUID and "to" not in client.posted[1]
    assert result.attempted_recipients == (PHONE, BSUID)


@pytest.mark.parametrize("code", [131047, 131056, 131051, 131026])
async def test_non_address_errors_never_retry(code: int):
    client = _Client(reject={PHONE: code})
    result = await _wa(client).send_text("hi", _both())
    assert not result.success and result.error_code == str(code)
    assert len(client.posted) == 1


async def test_every_address_rejected_returns_metas_last_error():
    client = _Client(reject={PHONE: 131030, BSUID: 131030})
    result = await _wa(client).send_text("hi", _both())
    assert not result.success and result.error_code == "131030"
    assert result.attempted_recipients == (PHONE, BSUID)


async def test_bsuid_only_user_is_sent_to_the_bsuid():
    client = _Client()
    target = DirectMessage(inbox_ref=WA, addresses=DeliveryAddresses.of(BSUID))
    assert (await _wa(client).send_text("hi", target)).success
    assert client.posted[0]["recipient"] == BSUID


def test_bot_reply_is_attributed_to_its_destination():
    own = SendInvocation("send_text", "text", _both(), args=())
    assert _destination_user(own, BSUID) == BSUID
    other = DirectMessage(inbox_ref=WA, addresses=DeliveryAddresses.of("573000000001"))
    cross = SendInvocation("send_text", "text", other, args=())
    assert _destination_user(cross, BSUID) == "573000000001"


def test_target_still_rejects_another_inbox():
    from wappa.domain.messaging_targets import TargetInboxMismatchError

    other = InboxRef(platform=PlatformType.WHATSAPP, inbox_id="other")
    with pytest.raises(TargetInboxMismatchError):
        _both().resolve_all(other)


def test_equivalent_phones_are_tried_once():
    assert whatsapp_delivery_order((PHONE, "+" + PHONE, BSUID)) == (PHONE, BSUID)


def test_serialized_target_validates_back():
    dumped = _both().model_dump(mode="json")
    assert DirectMessage.model_validate(dumped) == _both()


async def test_local_media_is_uploaded_once_across_fallback(tmp_path):
    class _Uploads:
        calls = 0

        async def upload_media(self, *args, **kwargs):
            type(self).calls += 1
            return type("R", (), {"success": True, "media_id": "m1"})()

    client = _Client(reject={PHONE: 131030})
    wa = _wa(client)
    wa.media_handler = _Uploads()  # type: ignore[assignment]
    image = tmp_path / "a.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n")
    result = await wa.send_image(image, _both())
    assert result.success and _Uploads.calls == 1
    assert [_sent_to(p) for p in client.posted] == [PHONE, BSUID]


async def test_error_text_mentioning_131062_is_not_an_address_rejection():
    class _Flaky(_Client):
        async def post_request(self, payload: dict) -> dict:
            self.posted.append(payload)
            raise RuntimeError("upstream said 131062 somewhere in a log line")

    client = _Flaky()
    result = await _wa(client).send_text("hi", _both())
    assert not result.success and result.error_code != "BSUID_RECIPIENT_NOT_SUPPORTED"
    assert len(client.posted) == 1  # no fallback on a non-Meta error
