"""Qualified Inbox identity at static cron and expiry runtime boundaries."""

from __future__ import annotations

import pytest

from wappa.core.expiry import parse_expiry_notification
from wappa.core.plugins.scheduling_plugin import SchedulingPlugin
from wappa.domain.inbox import InboxRef
from wappa.schemas.core.types import PlatformType


def test_expiry_key_recovers_qualified_inbox_ref() -> None:
    notification = parse_expiry_notification(
        {"type": "message", "data": "telegram__123:EXPTRIGGER:reminder:user"}
    )
    assert notification is not None
    assert notification.inbox_ref == InboxRef(
        platform=PlatformType.TELEGRAM, inbox_id="123"
    )
    assert parse_expiry_notification({"type": "message", "data": "malformed"}) is None


def test_cron_registration_preserves_qualified_inbox_ref() -> None:
    plugin = SchedulingPlugin()
    inbox_ref = InboxRef(platform=PlatformType.TELEGRAM, inbox_id="123")

    plugin.add_cron("report", "0 9 * * *", inbox_ref=inbox_ref)

    assert plugin._crons_declared[0].to_event().inbox_ref == inbox_ref


def test_user_scoped_cron_requires_a_qualified_inbox_ref() -> None:
    plugin = SchedulingPlugin()

    with pytest.raises(ValueError, match="requires inbox_ref"):
        plugin.add_cron("report", "0 9 * * *", user_id="user")
