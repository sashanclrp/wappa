"""Raw quote ID research stays manual and makes no implicit sends/retries."""

import json
import runpy
from pathlib import Path

import httpx
import pytest

_module = runpy.run_path(
    str(Path(__file__).resolve().parents[1] / "scripts/instagram_reply_probe.py")
)
ProbeError = _module["ProbeError"]
probe = _module["probe"]


async def run_probe(send=None, *, reject=False):
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.path.endswith("/conversations"):
            return httpx.Response(200, json={"data": [{"id": "conversation"}]})
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"id": "different-history-mid", "from": {"id": "user"}},
                        {"id": "webhook-mid", "from": {"id": "user"}},
                    ]
                },
            )
        if reject:
            return httpx.Response(
                400,
                json={
                    "error": {
                        "code": 100,
                        "error_subcode": 2534002,
                        "message": "never print user or token",
                    }
                },
            )
        return httpx.Response(200, json={"message_id": "accepted-mid"})

    async with httpx.AsyncClient(
        base_url="https://graph.instagram.com/v25.0/",
        transport=httpx.MockTransport(handler),
    ) as client:
        try:
            result = await probe(
                client,
                node="account",
                recipient="user",
                webhook_mid="webhook-mid",
                send=send,
            )
        except ProbeError as exc:
            result = exc.summary
    return result, requests


async def test_default_reads_history_and_compares_opaque_ids_without_sending_or_printing_them():
    report, requests = await run_probe()
    assert len(requests) == 2 and all(r.method == "GET" for r in requests)
    assert [r["same_as_webhook"] for r in report["history"]] == [False, True]
    assert "different-history-mid" not in json.dumps(report)
    assert "webhook-mid" not in json.dumps(report)
    assert not report["sent"]


@pytest.mark.parametrize(
    "source,expected",
    [
        ("webhook", "webhook-mid"),
        ("history:0", "different-history-mid"),
        ("plain", None),
    ],
)
async def test_explicit_send_uses_the_exact_selected_id_once(source, expected):
    report, requests = await run_probe(source)
    posts = [r for r in requests if r.method == "POST"]
    assert len(posts) == 1 and report["provider_accepted"]
    payload = json.loads(posts[0].content)
    assert payload.get("reply_to") == ({"mid": expected} if expected else None)


async def test_invalid_mid_error_is_not_retried_or_leaked():
    report, requests = await run_probe("webhook", reject=True)
    assert len(requests) == 1
    assert report == {"http_status": 400, "code": 100, "subcode": 2534002}


async def test_history_selection_is_fenced_against_a_changed_candidate():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={"data": [{"id": "conversation"}]}
            if request.url.path.endswith("/conversations")
            else {"data": [{"id": "new-mid"}]},
        )

    async with httpx.AsyncClient(
        base_url="https://graph.instagram.com/v25.0/",
        transport=httpx.MockTransport(handler),
    ) as client:
        with pytest.raises(ProbeError) as error:
            await probe(
                client,
                node="account",
                recipient="user",
                webhook_mid="original",
                send="history:0",
                expected_fingerprint="000000000000",
            )
    assert error.value.summary["reason"] == "candidate_changed; no send attempted"
    assert all(request.method == "GET" for request in requests)


@pytest.mark.parametrize("field", ["node", "recipient", "webhook_mid"])
async def test_blank_ids_stop_before_any_graph_request(field):
    requests = []
    values = {"node": "account", "recipient": "user", "webhook_mid": "mid"}
    values[field] = " "
    async with httpx.AsyncClient(
        base_url="https://graph.instagram.com/v25.0/",
        transport=httpx.MockTransport(lambda r: requests.append(r)),
    ) as client:
        with pytest.raises(ProbeError):
            await probe(client, **values, send="webhook")
    assert requests == []


@pytest.mark.parametrize("data", [{"data": {}}, {"data": [{}]}, {"data": [None]}])
async def test_malformed_history_stops_with_a_safe_diagnostic(data):
    async with httpx.AsyncClient(
        base_url="https://graph.instagram.com/v25.0/",
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=data)),
    ) as client:
        with pytest.raises(ProbeError) as error:
            await probe(
                client,
                node="account",
                recipient="user",
                webhook_mid="mid",
                send="history:0",
            )
    assert error.value.summary == {"reason": "malformed_history; no send attempted"}
