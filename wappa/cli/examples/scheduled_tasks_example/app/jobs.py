"""Connect a Host scheduler to Wappa with one ordinary async callback.

Scheduler engines persist a job as an importable function plus serializable
arguments, so ``run_scheduled_job`` is module-level and takes plain values. The
Host owns the engine, its datastore, recurrence, retries, overlap and history;
this callback only turns a firing into a ``ScheduledEvent``.
"""

import asyncio
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from fastapi import FastAPI

from wappa import InboxRef, ScheduledEvent, Scheduling
from wappa.schemas.core.types import PlatformType

_app: FastAPI | None = None


def bind_app(app: FastAPI | None) -> None:
    """Remember the app for job callbacks; the Host's lifecycle calls this."""
    global _app
    _app = app


async def run_scheduled_job(
    *,
    action: str,
    schedule_id: str,
    source: str = "apscheduler",
    platform: str | None = None,
    inbox_id: str | None = None,
    user_id: str | None = None,
    scheduled_for: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    """The one job body every schedule uses.

    Exceptions propagate on purpose: a job that reports success after a failure
    would defeat the engine's retry policy.
    """
    if _app is None:
        raise RuntimeError("bind_app() has not run; the application is not started")
    await Scheduling.from_app(_app).dispatch(
        ScheduledEvent(
            action=action,
            source=source,
            inbox_ref=(
                InboxRef(platform=PlatformType(platform), inbox_id=inbox_id)
                if platform and inbox_id
                else None
            ),
            user_id=user_id,
            scheduled_for=(
                datetime.fromisoformat(scheduled_for) if scheduled_for else None
            ),
            execution_id=schedule_id,
            payload=payload or {},
        )
    )


async def register_schedules(
    scheduler: Any,
    *,
    date_trigger: Callable[..., Any],
    interval_trigger: Callable[..., Any],
    inbox_id: str,
    user_id: str,
    owners: list[str],
    now: datetime,
) -> None:
    """Register the task shapes using APScheduler 4's ``add_schedule`` call.

    The trigger classes are parameters so this file imports no engine. All of
    these behaviors come from the engine: Wappa only receives the callbacks.
    """
    inbox = {"platform": "whatsapp", "inbox_id": inbox_id}

    # One-time task.
    await scheduler.add_schedule(
        run_scheduled_job,
        date_trigger(run_time=now + timedelta(hours=1)),
        id="reminder-A17",
        kwargs={
            "action": "appointment_reminder",
            "schedule_id": "reminder-A17",
            "user_id": user_id,
            "scheduled_for": (now + timedelta(hours=1)).isoformat(),
            "payload": {"text": "Appointment at 3 PM"},
            **inbox,
        },
    )
    # Recurring task without an end.
    await scheduler.add_schedule(
        run_scheduled_job,
        interval_trigger(weeks=1),
        id="weekly-report",
        kwargs={
            "action": "weekly_report",
            "schedule_id": "weekly-report",
            "payload": {"owners": owners},
            **inbox,
        },
    )
    # Recurring task with an end: the engine stops firing at end_time.
    await scheduler.add_schedule(
        run_scheduled_job,
        interval_trigger(days=1, end_time=now + timedelta(days=30)),
        id="campaign-report",
        kwargs={
            "action": "campaign_report",
            "schedule_id": "campaign-report",
            "payload": {"owners": owners},
            **inbox,
        },
    )
    # Heartbeat: System work with no Inbox or User.
    await scheduler.add_schedule(
        run_scheduled_job,
        interval_trigger(minutes=1),
        id="heartbeat",
        kwargs={"action": "heartbeat", "schedule_id": "heartbeat"},
    )


async def heartbeat_loop(
    interval_seconds: float, *, beats: int | None = None, source: str = "custom_loop"
) -> None:
    """The same lane without any engine: a plain Host asyncio loop.

    A dispatch failure ends the loop here; a Host decides its own policy.
    """
    count = 0
    while beats is None or count < beats:
        count += 1
        await run_scheduled_job(
            action="heartbeat", schedule_id=f"beat-{count}", source=source
        )
        await asyncio.sleep(interval_seconds)
