"""Opt-in raw webhook capture: redacted, DEV-only, never breaks intake."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from pydantic import SecretStr

import wappa.api.controllers.webhook_controller as webhook_controller
from wappa.api.routes.webhooks import create_webhook_router
from wappa.core.config.meta_application import MetaApplicationConfig
from wappa.core.config.settings import settings
from wappa.core.events.event_dispatcher import WappaEventDispatcher
from wappa.core.events.event_handler import WappaEventHandler
from wappa.core.factory.inbox_assembly import InboxRuntimeConfiguration
from wappa.core.inbound import SIGNATURE_HEADER, MetaCallbackAuthenticator
from wappa.core.inbound.payload_capture import (
    MASKED_TEXT,
    REDACTED,
    capture_kind,
    capture_payload,
    find_secrets,
    redact_payload,
)
from wappa.core.lifecycle import BackgroundWorkTracker, SessionLifecycle
from wappa.domain.inbox import InboxRoutingMode, SettingsInboxCredentialResolver
from wappa.webhooks import InboundMessageWebhook

APP_SECRET = SecretStr("app-secret")
FAKE_META_TOKEN = "EAA" + "B" * 40


def _wa_text(body: str = "my private words") -> dict[str, Any]:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "1111111111",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "15551234567",
                                "phone_number_id": "123",
                            },
                            "contacts": [
                                {"wa_id": "573001234567", "profile": {"name": "U"}}
                            ],
                            "messages": [
                                {
                                    "from": "573001234567",
                                    "id": "wamid.capture",
                                    "timestamp": "1710000000",
                                    "type": "text",
                                    "text": {"body": body},
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }


# ── redaction ────────────────────────────────────────────────────────


def test_redaction_masks_text_and_secrets_but_keeps_structure() -> None:
    payload = _wa_text()
    value = payload["entry"][0]["changes"][0]["value"]
    value["access_token"] = "plain-secret"
    value["media_url"] = f"https://x.test/m?access_token={FAKE_META_TOKEN}&a=1"
    value["note"] = f"leaked {FAKE_META_TOKEN} here"

    redacted = redact_payload(payload)
    out = redacted["entry"][0]["changes"][0]["value"]

    assert out["messages"][0]["text"]["body"] == MASKED_TEXT
    assert out["access_token"] == REDACTED
    assert FAKE_META_TOKEN not in json.dumps(redacted)
    assert out["metadata"]["phone_number_id"] == "123"
    assert out["contacts"][0]["wa_id"] == "573001234567"
    assert out["messages"][0]["id"] == "wamid.capture"
    assert find_secrets(redacted) == []
    assert payload["entry"][0]["changes"][0]["value"]["access_token"] == (
        "plain-secret"
    ), "redaction must not mutate the live payload"


def test_instagram_dm_and_comment_text_are_masked() -> None:
    dm = {"message": {"mid": "m1", "text": "hi"}}
    comment = {"field": "comments", "value": {"id": "c1", "text": "nice post"}}

    assert redact_payload(dm)["message"]["text"] == MASKED_TEXT
    assert redact_payload(comment)["value"]["text"] == MASKED_TEXT
    assert redact_payload(comment)["value"]["id"] == "c1"


def test_find_secrets_reports_paths_not_values() -> None:
    hits = find_secrets(
        {
            "a": {"app_secret": "s3cr3t"},
            "b": [f"Bearer {FAKE_META_TOKEN}"],
            "c": "sha256=" + "a" * 64,
        }
    )

    assert any(hit.startswith("$.a.app_secret") for hit in hits)
    assert any(hit.startswith("$.b[0]") for hit in hits)
    assert any(hit.startswith("$.c") for hit in hits)
    assert all("s3cr3t" not in hit and FAKE_META_TOKEN not in hit for hit in hits)


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (_wa_text(), "messages.text"),
        (
            {
                "entry": [
                    {"changes": [{"field": "messages", "value": {"statuses": [{}]}}]}
                ]
            },
            "statuses",
        ),
        (
            {
                "entry": [
                    {
                        "changes": [
                            {
                                "field": "messages",
                                "value": {
                                    "messages": [
                                        {
                                            "type": "interactive",
                                            "interactive": {"type": "list_reply"},
                                        }
                                    ]
                                },
                            }
                        ]
                    }
                ]
            },
            "messages.interactive.list_reply",
        ),
        ({"entry": [{"messaging": [{"postback": {}}]}]}, "messaging.postback"),
        (
            {"entry": [{"messaging": [{"message": {"is_echo": True}}]}]},
            "messaging.echo",
        ),
        ({"entry": [{"changes": [{"field": "comments"}]}]}, "comments"),
        ({}, "unknown"),
    ],
)
def test_capture_kind(payload: dict[str, Any], expected: str) -> None:
    assert capture_kind(payload) == expected


def test_capture_payload_writes_redacted_file(tmp_path: Path) -> None:
    path = capture_payload(
        _wa_text(),
        platform="whatsapp",
        log_dir=tmp_path,
        now=datetime(2026, 11, 5, 12, 0, 1, 2345, tzinfo=UTC),
    )

    assert path == (
        tmp_path / "payloads" / "whatsapp" / "messages.text-20261105T120001002345Z.json"
    )
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["entry"][0]["changes"][0]["value"]["messages"][0]["text"] == {
        "body": MASKED_TEXT
    }


# ── controller wiring ────────────────────────────────────────────────


class _Handler(WappaEventHandler):
    async def process_message(self, webhook: InboundMessageWebhook) -> None:
        return None


def _app() -> FastAPI:
    app = FastAPI()
    resolver = SettingsInboxCredentialResolver(
        access_token=SecretStr("test-token"),
        phone_number_id="123",
        business_account_id="1111111111",
    )
    app.state.inbox_runtime = InboxRuntimeConfiguration(
        mode=InboxRoutingMode.LEGACY,
        credential_resolver=resolver,
        default_inbox_ref=resolver.inbox_ref,
    )
    app.state.meta_application_config = MetaApplicationConfig(
        app_secret=APP_SECRET, whatsapp_webhook_verify_token=SecretStr("verify")
    )
    app.state.messenger_middleware = []
    app.state.wappa_cache_type = "memory"
    app.state.background_work_tracker = BackgroundWorkTracker()
    app.include_router(create_webhook_router(WappaEventDispatcher(_Handler())))
    return app


async def _post(app: FastAPI, body: bytes, *, signed: bool = True) -> httpx.Response:
    headers = {"Content-Type": "application/json"}
    if signed:
        headers[SIGNATURE_HEADER] = MetaCallbackAuthenticator(APP_SECRET).sign(body)
    app.state.session_lifecycle = SessionLifecycle(httpx.AsyncClient())
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            response = await client.post(
                "/webhook/inboxes/whatsapp", content=body, headers=headers
            )
        await app.state.background_work_tracker.drain(timeout=1)
    finally:
        await app.state.session_lifecycle.close()
    return response


@pytest.fixture
def capture_on(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setattr(settings, "capture_payloads", True)
    monkeypatch.setattr(settings, "environment", "DEV")
    monkeypatch.setattr(settings, "log_dir", str(tmp_path))
    return tmp_path


def _captured(root: Path) -> list[Path]:
    return sorted((root / "payloads").rglob("*.json"))


async def test_authenticated_post_is_captured(capture_on: Path) -> None:
    body = json.dumps(_wa_text()).encode()

    response = await _post(_app(), body)

    assert response.status_code == 200
    [path] = _captured(capture_on)
    assert path.parent.name == "whatsapp"
    assert "my private words" not in path.read_text(encoding="utf-8")


async def test_unauthenticated_post_is_never_captured(capture_on: Path) -> None:
    response = await _post(_app(), json.dumps(_wa_text()).encode(), signed=False)

    assert response.status_code == 401
    assert _captured(capture_on) == []


async def test_capture_failure_does_not_break_intake(
    capture_on: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*args: Any, **kwargs: Any) -> Path:
        raise OSError("disk full")

    monkeypatch.setattr(webhook_controller, "capture_payload", boom)

    response = await _post(_app(), json.dumps(_wa_text()).encode())

    assert response.status_code == 200


async def test_capture_is_off_in_production(
    capture_on: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "environment", "PROD")

    response = await _post(_app(), json.dumps(_wa_text()).encode())

    assert response.status_code == 200
    assert _captured(capture_on) == []
