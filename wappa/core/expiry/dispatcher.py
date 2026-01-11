"""
Expiry Dispatcher - Dispatches handlers asynchronously for expired keys.

Single Responsibility: Fire-and-forget handler dispatch with completion tracking.
"""

import asyncio
import logging
from dataclasses import dataclass

from .parser import ExpiryEvent

logger = logging.getLogger(__name__)


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
            event.handler(event.identifier, event.expired_key),
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
