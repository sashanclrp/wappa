"""Tracked background task lifecycle with drain capability."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DrainResult:
    """Outcome of a drain operation."""

    completed: int
    cancelled: int
    timed_out: bool


class BackgroundWorkTracker:
    """Tracks asyncio tasks created for accepted background work.

    All framework fire-and-forget callsites (inbound dispatch, expiry
    handlers, external webhooks) register tasks here.  During shutdown
    the tracker refuses new work and drains in-flight tasks with a
    bounded timeout.
    """

    def __init__(self) -> None:
        self._tasks: set[asyncio.Task] = set()
        self._draining = False

    def track(self, coro, *, name: str | None = None) -> asyncio.Task:
        """Create and track a background task.

        Raises RuntimeError if the runtime is draining.
        """
        if self._draining:
            raise RuntimeError(
                "Wappa runtime is draining — cannot accept new background work. "
                "This task was submitted after shutdown began."
            )
        task = asyncio.create_task(coro, name=name)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    def begin_drain(self) -> None:
        """Mark draining — new track() calls will be rejected."""
        self._draining = True
        logger.info(
            "Background work tracker entering drain state (%d tasks in flight)",
            len(self._tasks),
        )

    async def drain(self, timeout: float = 30.0) -> DrainResult:
        """Wait for tracked tasks to finish, cancel stragglers after timeout."""
        self.begin_drain()

        pending = set(self._tasks)
        if not pending:
            logger.info("No background tasks to drain")
            return DrainResult(completed=0, cancelled=0, timed_out=False)

        logger.info(
            "Draining %d background task(s) (timeout=%.1fs)", len(pending), timeout
        )

        done, still_pending = await asyncio.wait(pending, timeout=timeout)

        cancelled = 0
        for task in still_pending:
            task.cancel()
            cancelled += 1

        if still_pending:
            await asyncio.wait(still_pending, timeout=5.0)

        result = DrainResult(
            completed=len(done),
            cancelled=cancelled,
            timed_out=bool(still_pending),
        )

        if result.timed_out:
            logger.warning(
                "Background work drain timed out: %d completed, %d cancelled",
                result.completed,
                result.cancelled,
            )
        else:
            logger.info(
                "Background work drain completed: %d tasks finished", result.completed
            )

        return result

    @property
    def active_count(self) -> int:
        return len(self._tasks)

    @property
    def is_draining(self) -> bool:
        return self._draining
