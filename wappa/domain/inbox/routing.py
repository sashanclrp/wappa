"""Inbox Routing Modes."""

from __future__ import annotations

from enum import StrEnum


class InboxRoutingMode(StrEnum):
    """Which Inbox credential authority one Wappa application uses.

    ``legacy`` is the single WhatsApp Inbox supplied by settings.
    ``explicit`` is the Inbox Directory fed by a Host source. The two never
    fall back to one another; an omitted mode defaults to ``legacy``.
    """

    LEGACY = "legacy"
    EXPLICIT = "explicit"


__all__ = ["InboxRoutingMode"]
