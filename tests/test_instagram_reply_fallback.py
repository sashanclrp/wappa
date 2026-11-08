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
DROPPED = {"dropped": True, "error_code": "100/2534002"}


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
async def test_invalid_quote_retries_only_the_refused_part_and_preserves_evidence(
    family,
):
    result, sent, registry = await send_with_responses(
        [
            rejected(),
            httpx.Response(200, json={"message_id": "accepted-1"}),
            httpx.Response(200, json={"message_id": "accepted-2"}),
        ],
        family=family,
    )
    assert result.success
    assert sent[0]["reply_to"] == {"mid": MID}
    assert sent[1] == {
        key: value for key, value in sent[0].items() if key != "reply_to"
    }
    assert all("reply_to" not in body for body in sent[1:])
    assert len(sent) == (3 if family in {"caption", "split"} else 2)
    assert result.platform_response["wappa_reply_to"] == DROPPED
    expected_ids = (
        ["accepted-1", "accepted-2"]
        if family in {"caption", "split"}
        else ["accepted-1"]
    )
    assert [call.args[1] for call in registry.record.await_args_list] == expected_ids
    if family in {"caption", "split"}:
        assert result.platform_response["wappa_parts"]["message_ids"] == expected_ids


@pytest.mark.parametrize(
    "final",
    [
        rejected(),
        httpx.Response(503, json={"error": {"code": 2}}),
        httpx.Response(200, json={"recipient_id": "12345"}),
    ],
)
async def test_unquoted_retry_returns_its_failure_without_a_third_send(final):
    result, sent, registry = await send_with_responses([rejected(), final])
    assert not result.success
    assert len(sent) == 2
    assert result.platform_response["wappa_reply_to"] == DROPPED
    assert result.error_code == (
        "100/2534002" if final.status_code == 400 else "INDETERMINATE"
    )
    registry.record.assert_not_awaited()


@pytest.mark.parametrize(
    "response,reply",
    [
        (rejected(), None),
        (rejected(subcode=33), MID),
        (rejected(code=10), MID),
        (rejected(status=503), MID),
        (httpx.Response(200, json={"recipient_id": "12345"}), MID),
        (httpx.Response(200, json={"message_id": "ok"}), MID),
    ],
)
async def test_other_outcomes_do_not_drop_the_quote_or_add_a_retry(response, reply):
    result, sent, _ = await send_with_responses([response], reply=reply)
    assert len(sent) == 1
    assert "wappa_reply_to" not in (result.platform_response or {})
    if reply:
        assert sent[0]["reply_to"] == {"mid": MID}


async def test_fallback_evidence_survives_a_later_caption_failure():
    result, sent, _ = await send_with_responses(
        [
            rejected(),
            httpx.Response(200, json={"message_id": "image-1"}),
            rejected(subcode=33),
        ],
        family="caption",
    )
    assert not result.success and len(sent) == 3
    assert result.platform_response["wappa_reply_to"] == DROPPED
    assert result.platform_response["wappa_parts"]["message_ids"] == ["image-1"]
