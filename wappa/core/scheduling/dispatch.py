"""One dispatch path from any trigger source to the Host's scheduled hook."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from wappa.core.dispatch.context_builder import DispatchContextBuilder
from wappa.domain.events.scheduled_event import ScheduledEvent

if TYPE_CHECKING:
    from fastapi import FastAPI

    from wappa.core.events.event_handler import WappaEventHandler


class Scheduling:
    """Run Scheduled Events on a fresh, fully prepared handler.

    Wappa prepares the context and the Host's ``process_scheduled_event`` does
    the work. Every failure reaches the awaiting caller, so the engine that
    fired the task applies its own retry policy.

    Example:
        async def run_job(action: str, inbox_id: str, user_id: str) -> None:
            await Scheduling.from_app(app).dispatch(
                ScheduledEvent(
                    action=action,
                    source="apscheduler",
                    inbox_ref=InboxRef.whatsapp(inbox_id),
                    user_id=user_id,
                )
            )
    """

    def __init__(
        self,
        *,
        context_builder: DispatchContextBuilder,
        event_handler: WappaEventHandler,
    ) -> None:
        self._context_builder = context_builder
        self._event_handler = event_handler

    @classmethod
    def from_app(cls, app: FastAPI) -> Scheduling:
        """Return the app's dispatcher; call it once startup has finished."""
        existing = getattr(app.state, "scheduling", None)
        if isinstance(existing, cls):
            return existing
        event_handler = getattr(app.state, "wappa_event_handler", None)
        if event_handler is None:
            raise RuntimeError(
                "No WappaEventHandler is available for scheduled dispatch: call "
                "Wappa.set_event_handler() or pass SchedulingPlugin(event_handler=...)"
            )
        scheduling = cls(
            context_builder=DispatchContextBuilder.from_app(app),
            event_handler=event_handler,
        )
        app.state.scheduling = scheduling
        return scheduling

    async def dispatch(self, event: ScheduledEvent) -> None:
        """Run ``event`` to completion and propagate any failure.

        The work counts as tracked background work, so shutdown drains it. Once
        the runtime is draining this raises ``RuntimeError`` without running it.
        """
        tracker = self._context_builder.capabilities.background_work_tracker
        if tracker is None:
            await self.run(event)
            return
        await tracker.track(
            self.run(event), name=f"scheduled:{event.source}:{event.action}"
        )

    async def run(self, event: ScheduledEvent) -> None:
        """Build the context and call the hook in the caller's own task.

        For trigger sources already inside tracked work; everything else uses
        :meth:`dispatch`.
        """
        async with self._context_builder.scope(
            self._event_handler, inbox_ref=event.inbox_ref, user_id=event.user_id
        ) as handler:
            await handler.handle_scheduled_event(
                event.model_copy(
                    update={
                        "user_id": handler.user_id,
                        "dispatched_at": datetime.now(UTC),
                    }
                )
            )
