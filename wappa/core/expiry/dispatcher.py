"""Turn an expired Redis key into a Scheduled Event on tracked background work."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import TYPE_CHECKING, Protocol

from wappa.domain.events.scheduled_event import SOURCE_REDIS_EXPIRY, ScheduledEvent
from wappa.domain.inbox.identity import InboxRef

from .parser import ExpiryNotification

if TYPE_CHECKING:
    from wappa.core.lifecycle import BackgroundWorkTracker

logger = logging.getLogger(__name__)


class ExpirySubjectBinding(Protocol):
    """The Host's answer to: whose User, if any, is this expired key about?

    An Expiry Key has only an action and an opaque identifier, which may be a
    User or a message ID. Only the Host knows which, so Wappa never guesses from
    its shape. Return the subject User, or ``None`` for Inbox-only work. Raise
    for an action the Host does not recognize: the failure is logged and the
    hook does not run. A binding maps identity only; it builds no capabilities.
    """

    def __call__(
        self, *, inbox_ref: InboxRef, action: str, identifier: str
    ) -> Awaitable[str | None]: ...


class ExpiryDispatcher:
    """Adapts expiry notifications to the shared scheduled-event path."""

    def __init__(
        self,
        *,
        run_event: Callable[[ScheduledEvent], Awaitable[None]],
        tracker: BackgroundWorkTracker,
        subjects: ExpirySubjectBinding | None = None,
    ) -> None:
        self._run_event = run_event
        self._tracker = tracker
        self._subjects = subjects

    def dispatch(
        self,
        notification: ExpiryNotification,
        *,
        recovered: bool = False,
        scheduled_for: datetime | None = None,
        execution_id: str | None = None,
        on_success: Callable[[], Awaitable[None]] | None = None,
    ) -> asyncio.Task[None]:
        """Run tracked work; acknowledge durable occurrences only after success."""
        task_name = f"expiry:{notification.action}:{notification.identifier}"
        try:
            task = self._tracker.track(
                self._run(
                    notification, recovered, scheduled_for, execution_id, on_success
                ),
                name=task_name,
            )
        except RuntimeError:
            logger.warning(
                "Runtime draining: refusing expiry action %s for %s",
                notification.action,
                notification.identifier,
            )
            raise
        task.add_done_callback(lambda done: self._on_completion(done, notification))
        return task

    async def _run(
        self,
        notification: ExpiryNotification,
        recovered: bool,
        scheduled_for: datetime | None,
        execution_id: str | None,
        on_success: Callable[[], Awaitable[None]] | None,
    ) -> None:
        await self._run_event(
            ScheduledEvent(
                action=notification.action,
                source=SOURCE_REDIS_EXPIRY,
                inbox_ref=notification.inbox_ref,
                user_id=await self._subject(notification),
                identifier=notification.identifier,
                metadata={
                    "expired_key": notification.expired_key,
                    "recovered": recovered,
                },
                scheduled_for=scheduled_for,
                execution_id=execution_id,
            )
        )

        if on_success is not None:
            await on_success()

    async def _subject(self, notification: ExpiryNotification) -> str | None:
        if self._subjects is None:
            return None
        return await self._subjects(
            inbox_ref=notification.inbox_ref,
            action=notification.action,
            identifier=notification.identifier,
        )

    @staticmethod
    def _on_completion(
        task: asyncio.Task[None], notification: ExpiryNotification
    ) -> None:
        """Expiry has no awaiting caller, so this log is where a failure surfaces."""
        if task.cancelled():
            logger.debug(
                "Expiry action cancelled: action=%s, identifier=%s",
                notification.action,
                notification.identifier,
            )
            return
        exception = task.exception()
        if exception is not None:
            logger.error(
                "Expiry action failed: action=%s, identifier=%s, error=%s",
                notification.action,
                notification.identifier,
                exception,
                exc_info=exception,
            )
