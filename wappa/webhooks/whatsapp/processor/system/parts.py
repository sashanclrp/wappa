"""The four values every system-webhook family produces."""

from __future__ import annotations

from datetime import datetime
from typing import NamedTuple

from wappa.webhooks.core.webhook_interfaces import (
    SystemEventDetail,
    SystemEventType,
    UserBase,
)


class SystemParts(NamedTuple):
    """What one system family hands back to the dispatch method."""

    event_type: SystemEventType
    detail: SystemEventDetail
    timestamp: datetime
    user: UserBase | None
