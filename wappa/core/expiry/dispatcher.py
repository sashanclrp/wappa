"""
Expiry Dispatcher - Dispatches handlers asynchronously for expired keys.

Single Responsibility: Fire-and-forget handler dispatch with completion tracking.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from wappa.core.sse.context import classify_meta_identifier, sse_event_scope

from .parser import ExpiryEvent

if TYPE_CHECKING:
    from wappa.core.lifecycle import BackgroundWorkTracker

logger = logging.getLogger(__name__)


async def _run_with_sse_scope(
    event: ExpiryEvent, tracker: BackgroundWorkTracker | None = None
) -> None:
    """Wrap the handler so any SSE emitted from inside carries coherent identity.

    The expiry key only gives us ``(inbox, identifier)``. We classify
    ``identifier`` by shape into bsuid/phone; apps can refine via
    ``update_identity`` / ``update_metadata`` once they load cache state.
    """
    from wappa.core.expiry.context_helpers import parse_inbox_from_expired_key

    inbox_id = parse_inbox_from_expired_key(event.expired_key) or "unknown"
    bsuid, phone = classify_meta_identifier(event.identifier)
    async with sse_event_scope(
        inbox_id=inbox_id,
        user_id=event.identifier,
        bsuid=bsuid,
        phone_number=phone,
        tracker=tracker,
    ):
        await event.handler(event.identifier, event.expired_key)


class ExpiryDispatcher:
    """Dispatches expiry handlers via BackgroundWorkTracker for lifecycle-safe execution."""

    def __init__(self, tracker: BackgroundWorkTracker) -> None:
        self._tracker = tracker

    def dispatch(self, event: ExpiryEvent) -> asyncio.Task:
        """Dispatch handler as a tracked async task."""
        coro = _run_with_sse_scope(event, tracker=self._tracker)
        task_name = f"{event.handler_name}:{event.identifier}"

        try:
            task = self._tracker.track(coro, name=task_name)
        except RuntimeError:
            logger.warning(
                "Runtime draining — dropping expiry handler %s for %s",
                event.handler_name,
                event.identifier,
            )
            raise

        logger.info(
            "Dispatched handler: %s (action=%s, identifier=%s)",
            event.handler_name,
            event.action,
            event.identifier,
        )

        task.add_done_callback(
            lambda t: self._on_completion(t, event.action, event.identifier)
        )

        return task

    def _on_completion(
        self,
        task: asyncio.Task,
        action: str,
        identifier: str,
    ) -> None:
        """
        Log handler completion or errors.

        Args:
            task: Completed asyncio.Task
            action: Action name for logging
            identifier: Event identifier for logging
        """
        try:
            exception = task.exception()
            if exception:
                logger.error(
                    "Handler failed: action=%s, identifier=%s, error=%s",
                    action,
                    identifier,
                    exception,
                    exc_info=exception,
                )
            else:
                logger.debug(
                    "Handler completed: action=%s, identifier=%s",
                    action,
                    identifier,
                )
        except asyncio.CancelledError:
            logger.debug(
                "Handler cancelled: action=%s, identifier=%s",
                action,
                identifier,
            )
