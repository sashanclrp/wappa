"""SSE outgoing-message lifecycle middleware.

Replaces the legacy ``SSEMessengerWrapper``. Semantics preserved exactly:

    flush staged incoming_message  →  await send  →  publish outgoing_bot_message

Identity for the envelope comes from the active ``SSEEventContext`` — the
controller sets it once per request so this middleware stays identity-free
and request-agnostic.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...sse.context import flush_incoming_sse
from ...sse.event_hub import SSEEventHub
from ...sse.handlers import publish_sse_event
from ..pipeline import MessengerMiddleware, SendInvocation, SendNext, _to_serializable

if TYPE_CHECKING:
    from ....messaging.whatsapp.models.basic_models import MessageResult


class SSELifecycleMiddleware(MessengerMiddleware):
    """Flush pending ``incoming_message`` then publish ``outgoing_bot_message``.

    Registered by :class:`wappa.core.plugins.sse_events_plugin.SSEEventsPlugin`
    at priority ``70`` (lifecycle band) so it runs after domain notifications
    (pub/sub, cache) and before the raw transport on the inbound leg, and
    publishes the SSE event after the transport returns — which also means
    after any inner middleware (cache, notifications) has completed.
    """

    name = "sse_lifecycle"

    def __init__(self, event_hub: SSEEventHub) -> None:
        self._event_hub = event_hub

    async def handle(
        self,
        invocation: SendInvocation,
        call_next: SendNext,
    ) -> MessageResult:
        # Ordering guard: emit any staged incoming_message before outgoing.
        flush_incoming_sse()

        result = await call_next(invocation)

        await publish_sse_event(
            self._event_hub,
            event_type="outgoing_bot_message",
            source="bot_messenger",
            payload={
                "message_type": invocation.message_type,
                "request": invocation.to_request_payload(),
                "result": _to_serializable(result),
            },
        )

        return result
