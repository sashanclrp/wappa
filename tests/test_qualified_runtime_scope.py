"""Qualified Inbox identity at cron and expiry runtime boundaries."""

from __future__ import annotations

import pytest

from wappa.core.events.event_handler import WappaEventHandler
from wappa.core.expiry.context_helpers import parse_inbox_ref_from_expired_key
from wappa.core.plugins.cron_plugin import CronPlugin
from wappa.domain.inbox import InboxRef
from wappa.schemas.core.types import PlatformType


class _Handler(WappaEventHandler):
    async def process_message(self, webhook: object) -> None:
        return None


def test_expiry_key_recovers_qualified_inbox_ref() -> None:
    assert parse_inbox_ref_from_expired_key(
        "telegram__123:EXPTRIGGER:reminder:user"
    ) == InboxRef(platform=PlatformType.TELEGRAM, inbox_id="123")
    assert parse_inbox_ref_from_expired_key("malformed") is None


def test_cron_registration_preserves_qualified_inbox_ref() -> None:
    plugin = CronPlugin(_Handler(), include_router=False)
    inbox_ref = InboxRef(platform=PlatformType.TELEGRAM, inbox_id="123")

    plugin.add_cron("report", "0 9 * * *", inbox_ref=inbox_ref)

    assert plugin._cron_registrations[0].inbox_ref == inbox_ref


def test_user_scoped_cron_requires_a_qualified_inbox_ref() -> None:
    plugin = CronPlugin(_Handler(), include_router=False)

    with pytest.raises(ValueError, match="requires inbox_ref"):
        plugin.add_cron("report", "0 9 * * *", user_id="user")
