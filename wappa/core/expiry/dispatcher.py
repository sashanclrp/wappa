"""
Expiry Dispatcher - Dispatches handlers asynchronously for expired keys.

Single Responsibility: Fire-and-forget handler dispatch with completion tracking.
"""

import asyncio
import logging
from dataclasses import dataclass

from wappa.core.sse.context import classify_meta_identifier, sse_event_scope

from .parser import ExpiryEvent

logger = logging.getLogger(__name__)


async def _run_with_sse_scope(event: ExpiryEvent) -> None:
    """Wrap the handler so any SSE emitted from inside carries coherent identity.

    The expiry key only gives us ``(tenant, identifier)``. We classify
    ``identifier`` by shape into bsuid/phone; apps can refine via
    ``update_identity`` / ``update_metadata`` once they load cache state.
    """
    # Lazy import — context_helpers imports listener which imports this
    # module, so anchor the dep at call time instead of import time.
    from wappa.core.expiry.context_helpers import parse_tenant_from_expired_key

    tenant_id = parse_tenant_from_expired_key(event.expired_key) or "unknown"
    bsuid, phone = classify_meta_identifier(event.identifier)
    async with sse_event_scope(
        tenant_id=tenant_id,
        user_id=event.identifier,
        bsuid=bsuid,
        phone_number=phone,
    ):
        await event.handler(event.identifier, event.expired_key)


@dataclass
class ExpiryDispatcher:
    """
    Dispatches expiry handlers asynchronously.

    Responsibilities:
        - Create async tasks for handlers (fire-and-forget)
        - Track task completion via callbacks
        - Log handler execution status

    Pattern:
        Fire-and-forget: Handlers run independently without blocking the listener.
        Completion callbacks provide observability into handler success/failure.

    Usage:
        dispatcher = ExpiryDispatcher()
        dispatcher.dispatch(event)  # Non-blocking
    """

    def dispatch(self, event: ExpiryEvent) -> asyncio.Task:
        """
        Dispatch handler as async task.

        Args:
            event: Parsed expiry event with handler and metadata

        Returns:
            Created asyncio.Task for optional monitoring
        """
        task = asyncio.create_task(
            _run_with_sse_scope(event),
            name=f"{event.handler_name}:{event.identifier}",
        )

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
