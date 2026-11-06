"""Meta rate limits: one governor for both Platforms (wappa.resilience.rate_limits).

Short limits wait and retry inside the call; long ones block their scope and
answer ``rate_limited`` without calling Meta again; nothing is ever sent twice.
"""

import json

import httpx
import pytest
from pydantic import SecretStr

from wappa.domain.inbox import InboxRef
from wappa.domain.results import OperationOutcome, message_outcome
from wappa.messaging import DeliveryAddresses, DirectMessage
from wappa.messaging.instagram.client import InstagramClient
from wappa.messaging.whatsapp.client.whatsapp_client import WhatsAppClient
from wappa.messaging.whatsapp.messenger.whatsapp_messenger import (
    WhatsAppMessengerAdapter,
)
from wappa.resilience.rate_limits import (
    RateLimitGovernor,
    RateLimitHit,
    RateLimitPolicy,
    RateTarget,
    use_rate_governor,
)
from wappa.schemas.core.types import PlatformType


class FakeTime:
    def __init__(self) -> None:
        self.now = 1000.0
        self.slept: list[float] = []

    def clock(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


@pytest.fixture
def fake_time() -> FakeTime:
    t = FakeTime()
    use_rate_governor(
        RateLimitGovernor(
            RateLimitPolicy(send_rates=None), clock=t.clock, sleep=t.sleep
        )
    )
    return t


def _meta_error(code: int, status: int = 400) -> httpx.Response:
    return httpx.Response(status, json={"error": {"code": code, "message": "x"}})


def _ig_client(responses: list[httpx.Response], calls: list[httpx.Request]):
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return responses.pop(0) if len(responses) > 1 else responses[0]

    session = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return InstagramClient(
        inbox_ref=InboxRef(platform=PlatformType.INSTAGRAM, inbox_id="1784"),
        access_token=SecretStr("EAAtoken"),
        session_provider=lambda: session,
        graph_api_version="v26.0",
        graph_base_url="https://graph.facebook.com",
    )


async def test_instagram_app_limit_blocks_every_account_without_calling_meta(
    fake_time,
):
    calls: list[httpx.Request] = []
    graph = _ig_client([_meta_error(4, 403)], calls)
    first = await graph.request("POST", "1784/messages", json={}, operation="send")
    assert first.outcome is OperationOutcome.RATE_LIMITED
    assert first.error_code == "4" and first.retry_after == 300.0
    assert len(calls) == 1  # a long limit is never retried in the call

    other = _ig_client([httpx.Response(200, json={"message_id": "m"})], calls)
    other.graph.inbox_ref = InboxRef(platform=PlatformType.INSTAGRAM, inbox_id="9999")
    blocked = await other.request("POST", "9999/messages", json={}, operation="send")
    assert blocked.outcome is OperationOutcome.RATE_LIMITED
    assert "still active" in (blocked.error or "")
    assert len(calls) == 1  # the app scope covers every Instagram Inbox

    fake_time.now += 301
    again = await other.request("POST", "9999/messages", json={}, operation="send")
    assert again.ok and len(calls) == 2


async def test_instagram_cooldown_doubles_and_uses_metas_regain_hint(fake_time):
    calls: list[httpx.Request] = []
    graph = _ig_client([_meta_error(4, 403)], calls)
    await graph.request("GET", "x", operation="read")
    fake_time.now += 301
    second = await graph.request("GET", "x", operation="read")
    assert second.retry_after == 600.0  # consecutive block: doubled
    fake_time.now += 601

    buc = {"1784": [{"type": "instagram", "call_count": 100,
                     "estimated_time_to_regain_access": 7}]}  # fmt: skip
    hinted = _ig_client(
        [
            httpx.Response(
                400,
                json={"error": {"code": 80002}},
                headers={"x-business-use-case-usage": json.dumps(buc)},
            )
        ],
        calls,
    )
    result = await hinted.request("GET", "y", operation="read")
    assert result.retry_after == 420.0  # 7 minutes, from Meta


async def test_short_limit_waits_and_retries_inside_the_call(fake_time):
    calls: list[httpx.Request] = []
    graph = _ig_client(
        [_meta_error(613), httpx.Response(200, json={"message_id": "m1"})], calls
    )
    result = await graph.request("POST", "1784/messages", json={}, operation="send")
    assert result.ok and len(calls) == 2
    assert fake_time.slept == [1.0]


async def test_short_limit_gives_up_past_max_wait(fake_time):
    use_rate_governor(
        RateLimitGovernor(
            RateLimitPolicy(send_rates=None, max_wait=4.0),
            clock=fake_time.clock,
            sleep=fake_time.sleep,
        )
    )
    calls: list[httpx.Request] = []
    graph = _ig_client([_meta_error(613)], calls)
    result = await graph.request("POST", "1784/messages", json={}, operation="send")
    assert result.outcome is OperationOutcome.RATE_LIMITED
    assert len(calls) == 2  # 1 s, then 4 s would pass max_wait: stop
    assert result.retry_after == 4.0


async def test_retried_upload_sends_the_file_again(fake_time):
    seen: list[bytes] = []
    responses = [_meta_error(613), httpx.Response(200, json={"attachment_id": "a"})]

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.read())
        return responses.pop(0)

    session = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    graph = InstagramClient(
        inbox_ref=InboxRef(platform=PlatformType.INSTAGRAM, inbox_id="1784"),
        access_token=SecretStr("t"),
        session_provider=lambda: session,
        graph_api_version="v26.0",
        graph_base_url="https://graph.facebook.com",
    )
    import io

    content = io.BytesIO(b"VIDEOBYTES")
    result = await graph.request(
        "POST",
        "1784/message_attachments",
        data={"message": json.dumps({"attachment": {"type": "video"}})},
        files={"filedata": ("v.mp4", content, "video/mp4")},
        operation="upload",
    )
    assert result.ok
    assert all(b"VIDEOBYTES" in body for body in seen) and len(seen) == 2


async def test_instagram_video_is_paced_at_ten_per_second():
    t = FakeTime()
    use_rate_governor(RateLimitGovernor(clock=t.clock, sleep=t.sleep))
    calls: list[httpx.Request] = []
    graph = _ig_client([httpx.Response(200, json={"message_id": "m"})], calls)
    video = {"message": {"attachment": {"type": "video", "payload": {}}}}
    for _ in range(3):
        await graph.request("POST", "1784/messages", json=video, operation="send")
    assert t.slept == pytest.approx([0.1, 0.1])
    t.slept.clear()
    await graph.request("POST", "1784/messages", json={"message": {"text": "hi"}})
    assert t.slept == []  # text has its own 100/s lane


async def test_usage_near_the_limit_logs_a_warning(fake_time, caplog):
    calls: list[httpx.Request] = []
    usage = {"x-app-usage": json.dumps({"call_count": 91, "total_time": 3})}
    graph = _ig_client([httpx.Response(200, json={"id": "1"}, headers=usage)], calls)
    with caplog.at_level("WARNING"):
        await graph.request("GET", "me", operation="read")
    assert any("usage at 91%" in r.getMessage() for r in caplog.records)


def _wa(responses: list[httpx.Response], calls: list[dict]):
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content or b"{}"))
        return responses.pop(0) if len(responses) > 1 else responses[0]

    client = WhatsAppClient(
        session=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        access_token="EAAtoken",
        phone_number_id="pnid",
    )
    return WhatsAppMessengerAdapter(
        client=client,
        media_handler=None,  # type: ignore[arg-type]
        interactive_handler=None,  # type: ignore[arg-type]
        template_handler=None,  # type: ignore[arg-type]
        specialized_handler=None,  # type: ignore[arg-type]
        inbox_id="pnid",
    )


WA_OK = httpx.Response(
    200,
    json={
        "messages": [{"id": "wamid.1"}],
        "contacts": [{"input": "573001112233", "wa_id": "573001112233"}],
    },
)
DM = DirectMessage(
    inbox_ref=InboxRef.whatsapp("pnid"), addresses=DeliveryAddresses.of("573001112233")
)


async def test_whatsapp_pair_limit_backs_off_4_to_the_x_then_sends(fake_time):
    calls: list[dict] = []
    wa = _wa([_meta_error(131056), _meta_error(131056), WA_OK], calls)
    result = await wa.send_text("hi", DM)
    assert result.success and len(calls) == 3
    assert fake_time.slept == [1.0, 4.0]


async def test_whatsapp_pair_limit_is_per_recipient(fake_time):
    governor = RateLimitGovernor(clock=fake_time.clock, sleep=fake_time.sleep)
    a = RateTarget("whatsapp", "pnid", recipient="573001112233")
    b = RateTarget("whatsapp", "pnid", recipient="573009998877")

    async def refused() -> str:
        return "131056"

    await governor.run(a, refused, lambda code: RateLimitHit(code))
    assert governor.blocked_for(a) is not None
    assert governor.blocked_for(b) is None


async def test_whatsapp_long_limit_returns_rate_limited_and_429_shape(fake_time):
    calls: list[dict] = []
    wa = _wa([_meta_error(80007)], calls)
    result = await wa.send_text("hi", DM)
    assert not result.success and result.error_code == "80007"
    assert message_outcome(result) is OperationOutcome.RATE_LIMITED
    assert result.retry_after == 300.0
    again = await wa.send_text("hi", DM)
    assert message_outcome(again) is OperationOutcome.RATE_LIMITED
    assert len(calls) == 1  # blocked locally: Meta not called


async def test_quality_restrictions_are_not_rate_limits(fake_time):
    calls: list[dict] = []
    wa = _wa([_meta_error(131048)], calls)
    result = await wa.send_text("hi", DM)
    assert message_outcome(result) is OperationOutcome.REJECTED
    assert result.retry_after is None


async def test_api_answers_429_with_retry_after():
    from fastapi import HTTPException

    from wappa.api.utils import raise_for_failed_result
    from wappa.domain.results import MessageResult

    limited = MessageResult(
        success=False,
        platform=PlatformType.WHATSAPP,
        error="rate limit",
        error_code="130429",
        retry_after=2.4,
    )
    with pytest.raises(HTTPException) as caught:
        raise_for_failed_result(limited, "send text")
    assert caught.value.status_code == 429
    assert caught.value.headers == {"Retry-After": "3"}


async def test_a_shorter_hit_never_shortens_a_block(fake_time):
    governor = RateLimitGovernor(clock=fake_time.clock, sleep=fake_time.sleep)
    target = RateTarget("instagram", "1784")

    async def refused() -> str:
        return "x"

    await governor.run(
        target, refused, lambda _r: RateLimitHit("80002", retry_after=900.0)
    )
    await governor.run(target, refused, lambda _r: RateLimitHit("17", retry_after=10.0))
    assert governor.blocked_for(target) == pytest.approx(900.0)


async def test_pair_limit_without_recipient_holds_the_inbox(fake_time):
    governor = RateLimitGovernor(
        RateLimitPolicy(send_rates=None, max_wait=0.5),
        clock=fake_time.clock,
        sleep=fake_time.sleep,
    )
    target = RateTarget("whatsapp", "pnid")  # no recipient known

    async def refused() -> str:
        return "131056"

    await governor.run(target, refused, lambda code: RateLimitHit(code))
    assert governor.blocked_for(target) == pytest.approx(1.0)


async def test_whatsapp_upload_5xx_is_indeterminate_not_rejected(fake_time, tmp_path):
    from wappa.messaging import MediaFamily
    from wappa.messaging.whatsapp.handlers.whatsapp_media_handler import (
        WhatsAppMediaHandler,
    )
    from wappa.messaging.whatsapp.media_library import WhatsAppMediaLibrary

    client = WhatsAppClient(
        session=httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _r: httpx.Response(500, json={}))
        ),
        access_token="t",
        phone_number_id="pnid",
    )
    handler = WhatsAppMediaHandler(
        client=client,
        inbox_id="pnid",
        media_download_client=None,  # type: ignore[arg-type]
    )
    photo = tmp_path / "a.jpg"
    photo.write_bytes(b"\xff\xd8\xff" + b"\x00" * 16)
    result = await WhatsAppMediaLibrary(handler, "pnid").upload(
        photo, MediaFamily.IMAGE
    )
    assert result.outcome is OperationOutcome.INDETERMINATE
