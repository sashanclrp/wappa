"""Messenger middleware pipeline.

A :class:`MessengerPipeline` implements :class:`IMessenger` once. Every
outbound call is captured into a :class:`SendInvocation` and dispatched
through a priority-ordered chain of :class:`MessengerMiddleware` instances,
ASGI-style. Higher priority = closer to the caller (outer); lower priority
= closer to the raw transport (inner).

Adding a new :class:`IMessenger` method requires a one-method addition in
``messenger.py``; middleware code stays untouched.
"""

from __future__ import annotations

from .invocation import (
    PRIORITY_CACHE,
    PRIORITY_LIFECYCLE,
    PRIORITY_NOTIFICATIONS,
    PRIORITY_OBSERVABILITY,
    PRIORITY_RELIABILITY,
    MessengerMiddleware,
    MiddlewareEntry,
    SendInvocation,
    SendNext,
    _to_serializable,
)
from .messenger import MessengerPipeline

__all__ = [
    "PRIORITY_CACHE",
    "PRIORITY_LIFECYCLE",
    "PRIORITY_NOTIFICATIONS",
    "PRIORITY_OBSERVABILITY",
    "PRIORITY_RELIABILITY",
    "MessengerMiddleware",
    "MessengerPipeline",
    "MiddlewareEntry",
    "SendInvocation",
    "SendNext",
    "_to_serializable",
]
