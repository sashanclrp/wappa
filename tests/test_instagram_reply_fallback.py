"""An unavailable Instagram quote must not prevent delivery of the message."""

import json
from unittest.mock import AsyncMock

import httpx
import pytest
from pydantic import SecretStr

from wappa.domain.inbox import InboxRef
from wappa.messaging import DeliveryAddresses, DirectMessage
from wappa.messaging.instagram.messenger import InstagramMessengerAdapter
from wappa.schemas.core.types import PlatformType

REF = InboxRef(platform=PlatformType.INSTAGRAM, inbox_id="17890001")
DM = DirectMessage(inbox_ref=REF, addresses=DeliveryAddresses.of("12345"))
MID = "new_ig_dm_" + "x" * 157
DROPPED = {"dropped": True, "reason": "instagram_reply_quotes_disabled"}


def rejected(code=100, subcode=2534002, status=400):
    return httpx.Response(
        status,
        json={
            "error": {
                "code": code,
                "error_subcode": subcode,
                "message": "Invalid Message ID",
            }
        },
    )


async def send_with_responses(responses, *, family="text", reply=MID):
    sent = []

    def handler(request):
        sent.append(json.loads(request.content))
        return responses[min(len(sent) - 1, len(responses) - 1)]

    registry = AsyncMock()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = InstagramMessengerAdapter(
            inbox_ref=REF,
            access_token=SecretStr("dummy-token"),
            session_provider=lambda: client,
            graph_api_version="v25.0",
            graph_base_url="https://graph.instagram.com",
            sent_registry=registry,
        )
        if family == "text":
            result = await adapter.send_text("hello", DM, reply_to_message_id=reply)
        elif family == "split":
            result = await adapter.send_text(
                "hello " * 200, DM, reply_to_message_id=reply
            )
        else:
            result = await adapter.send_image(
                "https://example.com/image.jpg",
                DM,
                caption="caption" if family == "caption" else None,
                reply_to_message_id=reply,
            )
    return result, sent, registry


@pytest.mark.parametrize("family", ["text", "image", "caption", "split"])
async def test_quoted_sends_are_sent_unquoted_without_an_extra_graph_call(family):
    result, sent, registry = await send_with_responses(
        [
            httpx.Response(200, json={"message_id": "accepted-1"}),
            httpx.Response(200, json={"message_id": "accepted-2"}),
        ],
        family=family,
    )
    assert result.success
    assert all("reply_to" not in body for body in sent)
    assert len(sent) == (2 if family in {"caption", "split"} else 1)
    assert result.platform_response["wappa_reply_to"] == DROPPED
    assert result.parts[0].reply_to_dropped
    assert all(not part.reply_to_dropped for part in result.parts[1:])
    assert registry.record.await_count == len(sent)


@pytest.mark.parametrize(
    "response",
    [
        rejected(),
        rejected(subcode=33),
        httpx.Response(503, json={"error": {"code": 2}}),
        httpx.Response(200, json={"recipient_id": "12345"}),
    ],
)
async def test_unquoted_send_failures_return_without_retry_and_retain_quote_evidence(
    response,
):
    result, sent, registry = await send_with_responses([response])
    assert not result.success and len(sent) == 1
    assert "reply_to" not in sent[0]
    assert result.platform_response["wappa_reply_to"] == DROPPED
    assert "error_code" not in DROPPED  # no fabricated provider rejection
    assert result.parts[0].reply_to_dropped
    registry.record.assert_not_awaited()


async def test_no_quote_requested_has_no_dropped_quote_evidence():
    result, sent, _ = await send_with_responses(
        [httpx.Response(200, json={"message_id": "ok"})], reply=None
    )
    assert result.success and len(sent) == 1
    assert "wappa_reply_to" not in result.platform_response
    assert not result.parts[0].reply_to_dropped


async def test_suppression_evidence_survives_a_later_caption_failure():
    result, sent, _ = await send_with_responses(
        [httpx.Response(200, json={"message_id": "image-1"}), rejected(subcode=33)],
        family="caption",
    )
    assert not result.success and len(sent) == 2
    assert result.platform_response["wappa_reply_to"] == DROPPED
    assert result.platform_response["wappa_parts"]["message_ids"] == ["image-1"]
    assert result.parts[0].reply_to_dropped
