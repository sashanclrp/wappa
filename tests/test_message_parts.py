"""One Host send exposes ordered evidence of accepted, refused and skipped parts."""

import json
from unittest.mock import AsyncMock

import httpx
import pytest
from pydantic import SecretStr
from test_interactive_header import BUTTONS, IG_DM, IG_REF, SECTIONS, WA_DM, _wa
from test_messenger_parameter_reach import _card

from wappa.domain.interactive import InteractiveHeader
from wappa.domain.interfaces.media_library import UploadResult
from wappa.domain.message_parts import message_part, with_message_parts
from wappa.domain.results import MessageResult, OperationOutcome
from wappa.messaging.instagram.messenger import InstagramMessengerAdapter
from wappa.messaging.meta.graph import GraphResponse, MetaGraphError


async def instagram_send(case, *, fail_at=2, status=400, quote=False):
    sent = []

    def handler(request):
        sent.append(json.loads(request.content))
        if len(sent) == fail_at:
            return httpx.Response(
                status,
                json={
                    "error": {"code": 100, "error_subcode": 2534002 if quote else 33}
                },
            )
        return httpx.Response(200, json={"message_id": f"mid.{len(sent)}"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        messenger = InstagramMessengerAdapter(
            inbox_ref=IG_REF,
            access_token=SecretStr("dummy-token"),
            session_provider=lambda: client,
            graph_api_version="v26.0",
            graph_base_url="https://graph.facebook.com",
        )
        reply = "original-mid" if quote else None
        if case == "split":
            result = await messenger.send_text(
                "word " * 650, IG_DM, reply_to_message_id=reply
            )
        elif case == "caption":
            result = await messenger.send_image(
                "https://example.com/image.jpg",
                IG_DM,
                caption="😀" * 300,
                reply_to_message_id=reply,
            )
        elif case == "buttons":
            result = await messenger.send_button_message(
                BUTTONS,
                IG_DM,
                "Body",
                header=InteractiveHeader.of_image(url="https://example.com/image.jpg"),
            )
        elif case == "nested":
            result = await messenger.send_button_message(
                BUTTONS,
                IG_DM,
                "b" * 640,
                header=InteractiveHeader.of_image(url="https://example.com/image.jpg"),
                footer="f" * 60,
            )
        elif case == "quick_replies":
            result = await messenger.send_list_message(
                SECTIONS, IG_DM, "😀" * 600, "Open"
            )
        elif case == "carousel":
            result = await messenger.send_carousel([_card(1), _card(2)], IG_DM, "Intro")
        else:
            result = await messenger.send_text("one", IG_DM, reply_to_message_id=reply)
    return result, sent


def assert_evidence(result, sent):
    evidence = result.platform_response["wappa_parts"]
    parts = evidence["parts"]
    assert [p["index"] for p in parts] == list(range(len(parts)))
    accepted = [p["message_id"] for p in parts if p["outcome"] == "accepted"]
    assert evidence["message_ids"] == accepted
    assert evidence["delivered"] == len(accepted)
    attempted = [p for p in parts if p["outcome"] != "not_attempted"]
    assert len(attempted) == len(sent)
    for part, body in zip(attempted, sent, strict=True):
        message = body["message"]
        text = message.get("text")
        if (
            message.get("attachment", {}).get("payload", {}).get("template_type")
            == "button"
        ):
            text = message["attachment"]["payload"]["text"]
        assert part["text"] == text
    return parts


@pytest.mark.parametrize(
    "case,roles",
    [
        ("split", ["text_chunk"] * 4),
        ("caption", ["media", "caption", "caption"]),
        ("buttons", ["media", "buttons"]),
        ("nested", ["media", "text_chunk", "buttons"]),
        ("quick_replies", ["text_chunk", "text_chunk", "quick_replies"]),
        ("carousel", ["carousel_intro", "carousel"]),
    ],
)
async def test_later_refusal_records_exact_content_and_every_skipped_part(case, roles):
    result, sent = await instagram_send(case)
    assert not result.success and result.error_code == "100/33"
    parts = assert_evidence(result, sent)
    assert [p["role"] for p in parts] == roles
    assert [p["outcome"] for p in parts] == ["accepted", "rejected"] + [
        "not_attempted"
    ] * (len(parts) - 2)
    assert parts[1]["error_code"] == "100/33"
    assert all(p["message_id"] is None for p in parts[1:])


@pytest.mark.parametrize("platform", ["whatsapp", "instagram"])
async def test_single_message_uses_the_same_contract_on_every_platform(platform):
    if platform == "instagram":
        result, sent = await instagram_send("single", fail_at=None)
        assert_evidence(result, sent)
    else:
        messenger, client = _wa()
        result = await messenger.send_text("one", WA_DM)
        assert len(client.posted) == 1
    assert result.success
    assert result.platform_response["wappa_parts"]["parts"] == [
        {
            "index": 0,
            "role": "text_chunk",
            "text": "one",
            "content": None,
            "message_id": result.message_id,
            "outcome": "accepted",
        }
    ]


@pytest.mark.parametrize(
    "case", ["caption", "buttons", "nested", "quick_replies", "carousel"]
)
async def test_first_refusal_includes_all_remaining_planned_parts(case):
    result, sent = await instagram_send(case, fail_at=1)
    parts = assert_evidence(result, sent)
    assert parts[0]["outcome"] == "rejected"
    assert all(p["outcome"] == "not_attempted" for p in parts[1:])
    assert len(sent) == 1


async def test_indeterminate_part_is_not_classified_as_rejected_or_retried():
    result, sent = await instagram_send("split", status=503)
    parts = assert_evidence(result, sent)
    assert parts[1]["outcome"] == "indeterminate"
    assert result.error_code == "INDETERMINATE"


async def test_quote_fallback_is_one_part_with_dropped_quote_evidence():
    result, sent = await instagram_send("single", fail_at=1, quote=True)
    assert len(sent) == 2 and result.success
    part = result.platform_response["wappa_parts"]["parts"][0]
    assert part["reply_to_dropped"] is True
    assert part["message_id"] == "mid.2"
    assert result.platform_response["wappa_reply_to"]["dropped"] is True


async def test_upload_failure_records_unattempted_media_and_caption(tmp_path):
    async with httpx.AsyncClient() as client:
        messenger = InstagramMessengerAdapter(
            inbox_ref=IG_REF,
            access_token=SecretStr("dummy"),
            session_provider=lambda: client,
            graph_api_version="v26.0",
            graph_base_url="https://graph.facebook.com",
        )
        messenger._media.upload = AsyncMock(
            return_value=UploadResult(
                outcome="rejected",
                error_code="UPLOAD_FAILED",
                error="no",
                platform=IG_REF.platform,
                inbox_id=IG_REF.inbox_id,
            )
        )
        result = await messenger.send_image(
            tmp_path / "image.jpg", IG_DM, caption="caption"
        )
    assert not result.success
    parts = result.platform_response["wappa_parts"]["parts"]
    assert [p["role"] for p in parts] == ["media", "caption"]
    assert [p["outcome"] for p in parts] == ["not_attempted", "not_attempted"]


def test_rate_limited_outcome_and_root_fields_are_preserved():
    original = MessageResult(
        success=False, platform="whatsapp", error_code="4", retry_after=10
    )
    result = with_message_parts(
        original, [message_part("text_chunk", "hello", original)]
    )
    assert result.model_dump(exclude={"parts"}) == original.model_dump(
        exclude={"parts"}
    )
    assert result.parts[0].retry_after == original.retry_after
    assert (
        result.platform_response["wappa_parts"]["parts"][0]["outcome"] == "rate_limited"
    )


async def test_whatsapp_refusal_is_one_part_and_does_not_change_the_result():
    messenger, client = _wa()

    async def reject(payload):
        client.posted.append(payload)
        raise MetaGraphError(
            GraphResponse(
                outcome=OperationOutcome.REJECTED,
                status_code=400,
                error="refused",
                error_code="100/33",
            )
        )

    client.post_request = reject
    result = await messenger.send_text("exact body", WA_DM)
    assert not result.success and len(client.posted) == 1
    part = result.platform_response["wappa_parts"]["parts"][0]
    assert part["role"] == "text_chunk" and part["text"] == "exact body"
    assert part["outcome"] == "rejected" and part["message_id"] is None
    assert part["error_code"] == result.error_code
