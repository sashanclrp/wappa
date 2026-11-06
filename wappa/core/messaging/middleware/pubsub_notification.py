"""Pub/Sub bot-reply notification middleware.

Publishes a compact notification (message_id + message_type) on the
``wappa:notify:{inbox_id}:{user_id}:bot_reply`` channel after every
successful outgoing send. Identity comes from the active
``SSEEventContext`` (set once per request at the framework entry point)
so the middleware is constructed once at app startup and shared across
all requests.

Failures in ``publish_notification`` are swallowed by the handler itself —
they must never propagate and break the user-visible send.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ....domain.messaging_targets import DirectMessage
from ...pubsub.handlers import publish_notification
from ...sse.context import get_sse_context
from ..pipeline import MessengerMiddleware, SendInvocation, SendNext

if TYPE_CHECKING:
    from wappa.domain.results import MessageResult


class PubSubNotificationMiddleware(MessengerMiddleware):
    """Emit ``bot_reply`` pub/sub notifications after successful outbound sends.

    Registered by :class:`wappa.core.plugins.redis_pubsub_plugin.RedisPubSubPlugin`
    at priority ``30`` (notifications band) so it runs inside the SSE
    lifecycle band — notifications go out before the SSE ``outgoing_bot_message``
    envelope, preserving the order subscribers were already observing.
    """

    name = "pubsub_notification"

    async def handle(
        self,
        invocation: SendInvocation,
        call_next: SendNext,
    ) -> MessageResult:
        result = await call_next(invocation)

        if not result.success:
            return result

        ctx = get_sse_context()
        if ctx is None:
            # No request scope — nothing to key the notification on.
            return result

        await publish_notification(
            event_type="bot_reply",
            inbox_id=ctx.inbox_id,
            user_id=_destination_user(invocation, ctx.user_id),
            platform=ctx.platform,
            data={
                "message_id": result.message_id or "",
                "message_type": invocation.message_type,
            },
        )

        return result


def _destination_user(invocation: SendInvocation, request_user: str | None) -> str:
    """Attribute the reply to its destination, not the ambient webhook User.

    A send to the webhook's own User keeps its canonical ``user_id`` key (the
    BSUID even when the phone delivered it); a send to anyone else is keyed
    by that destination's address (ADR-0022).
    """
    target = invocation.target
    if isinstance(target, DirectMessage):
        if request_user and request_user in target.addresses.values:
            return request_user
        return target.address
    return request_user or invocation.recipient
