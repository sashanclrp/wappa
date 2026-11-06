"""
Wappa Scheduled Tasks Example - Main Application Entry Point

A Host-owned APScheduler drives reminders, reports and heartbeats through
Scheduling.dispatch into one process_scheduled_event hook. APScheduler is the
Host's dependency, not Wappa's: `uv add "apscheduler==4.0.0a6"` to run this.
"""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from wappa import Wappa
from wappa.core.config.settings import settings

from .jobs import bind_app, register_schedules
from .master_event import MasterEventHandler

if TYPE_CHECKING:
    from fastapi import FastAPI

    from wappa import WappaBuilder

# Replace with Users from your own data; a real Host reads these from its jobs.
USER_ID = "5551234567"
OWNERS = ["5551110000", "5552220000"]


def _apscheduler() -> tuple[Any, Callable[..., Any], Callable[..., Any]]:
    """Import the engine only when this Host actually starts it."""
    # The engine is the Host's dependency, so Wappa's own type check can't see it.
    from apscheduler import AsyncScheduler  # type: ignore[import-not-found]
    from apscheduler.triggers.date import DateTrigger  # type: ignore[import-not-found]
    from apscheduler.triggers.interval import (  # type: ignore[import-not-found]
        IntervalTrigger,
    )

    return AsyncScheduler(), DateTrigger, IntervalTrigger


class HostSchedulerPlugin:
    """A Host plugin: the scheduler's lifecycle stays outside Wappa."""

    def __init__(
        self,
        engine: Callable[[], tuple[Any, Callable[..., Any], Callable[..., Any]]],
    ) -> None:
        self._engine = engine
        self._scheduler: Any = None

    def configure(self, builder: "WappaBuilder") -> None:
        # After every Wappa capability exists, and stopped before they close.
        builder.add_startup_hook(self._start, priority=40)
        builder.add_shutdown_hook(self._stop, priority=90)

    async def _start(self, app: "FastAPI") -> None:
        if settings.wp_phone_id is None:
            raise RuntimeError("Set WP_PHONE_ID to the Inbox these tasks belong to")
        bind_app(app)
        self._scheduler, date_trigger, interval_trigger = self._engine()
        await self._scheduler.__aenter__()
        await register_schedules(
            self._scheduler,
            date_trigger=date_trigger,
            interval_trigger=interval_trigger,
            inbox_id=settings.wp_phone_id,
            user_id=USER_ID,
            owners=OWNERS,
            now=datetime.now(UTC),
        )
        await self._scheduler.start_in_background()

    async def _stop(self, app: "FastAPI") -> None:
        await self._scheduler.__aexit__(None, None, None)
        bind_app(None)


app = Wappa()
app.add_plugin(HostSchedulerPlugin(_apscheduler))
app.set_event_handler(MasterEventHandler())
