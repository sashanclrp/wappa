"""Messenger pipeline and composable middleware for outbound messaging.

A single :class:`MessengerPipeline` captures each outbound call into a
:class:`SendInvocation` and dispatches it through a priority-ordered chain
of :class:`MessengerMiddleware` instances.

Consumers and first-party plugins register middleware via
``WappaBuilder.add_messenger_middleware(mw, priority=...)``. The controller
stays agnostic — it only constructs the pipeline from the registered list.
"""

from .pipeline import (
    MessengerMiddleware,
    MessengerPipeline,
    MiddlewareEntry,
    SendInvocation,
    SendNext,
)

__all__ = [
    "MessengerMiddleware",
    "MessengerPipeline",
    "MiddlewareEntry",
    "SendInvocation",
    "SendNext",
]
