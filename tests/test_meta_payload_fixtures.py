"""Replay every recorded Meta payload through Wappa's real intake path.

Each JSON file under ``tests/fixtures/meta_payloads/<platform>/`` goes
through the same steps as an authenticated callback: Platform routing
(``PlatformWebhooks.route``), then ``PlatformWebhooks.translate`` that
builds the Universal Webhook. Strict schema mode
(``SYSTEM_STRICT_META_SCHEMA=1``, ADR-0023) turns any field Wappa does not
model into a failure, so drift found live becomes a fixture that fails CI
until it is modelled. Add fixtures with ``scripts/promote_payload.py``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import SecretStr

from wappa.core.inbound.payload_capture import find_secrets
from wappa.domain.inbox import InboxRef, PlatformAccountRef
from wappa.domain.inbox.ports import IInboxCredentialResolver, ResolvedInboxCredentials
from wappa.platforms import PLATFORMS
from wappa.schemas.core.types import PlatformType
from wappa.webhooks import SystemEventType, SystemWebhook
from wappa.webhooks.core import schema_drift

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "meta_payloads"
FIXTURES = sorted(FIXTURE_ROOT.glob("*/*.json"))


class _FixtureResolver(IInboxCredentialResolver):
    """Accept the Inbox each fixture names, under its own Platform Account."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self._account_id = str(payload["entry"][0]["id"])

    async def resolve_credentials(self, ref: InboxRef) -> ResolvedInboxCredentials:
        account_id = (
            ref.inbox_id if ref.platform is PlatformType.INSTAGRAM else self._account_id
        )
        return ResolvedInboxCredentials(
            inbox_ref=ref,
            account_ref=PlatformAccountRef(
                platform=ref.platform, platform_account_id=account_id
            ),
            access_token=SecretStr("fixture-token"),
            credential_version=1,
        )

    async def list_inbox_refs_for_platform_account(
        self, account_ref: PlatformAccountRef
    ) -> tuple[InboxRef, ...]:
        return (InboxRef(platform=account_ref.platform, inbox_id="100000000000002"),)


def test_seed_fixtures_exist() -> None:
    names = {f"{path.parent.name}/{path.name}" for path in FIXTURES}
    assert "whatsapp/statuses-pricing-subtype.json" in names
    assert "whatsapp/messages-interactive-list_reply-description.json" in names
    assert any(name.startswith("instagram/") for name in names)


@pytest.mark.parametrize(
    "fixture", FIXTURES, ids=[f"{p.parent.name}/{p.stem}" for p in FIXTURES]
)
def test_fixture_holds_no_secrets(fixture: Path) -> None:
    assert find_secrets(json.loads(fixture.read_text(encoding="utf-8"))) == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fixture", FIXTURES, ids=[f"{p.parent.name}/{p.stem}" for p in FIXTURES]
)
async def test_fixture_parses_without_schema_drift(
    fixture: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(schema_drift.STRICT_SCHEMA_ENV, "1")
    platform = PlatformType(fixture.parent.name)
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    webhooks = PLATFORMS[platform].webhooks

    deliveries = await webhooks.route(payload, _FixtureResolver(payload))

    assert deliveries, f"{fixture.name} produced no deliveries"
    for delivery in deliveries:
        webhook = await webhooks.translate(delivery.payload, inbox_id=delivery.inbox_id)
        assert schema_drift.unmodelled_fields(webhook) == []
        assert not (
            isinstance(webhook, SystemWebhook)
            and webhook.system_event_type is SystemEventType.UNSUPPORTED_EVENT
        ), f"{fixture.name} fell through to UNSUPPORTED_EVENT"
