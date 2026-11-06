# Your own scheduler

APScheduler, Celery or a custom loop all use one call. Wappa adds no scheduler dependency and stores no job.

## Contents

- The callback
- APScheduler
- A plain loop
- Another process, such as Celery
- What the engine owns

## The callback

Engines persist a job as an importable function plus serializable arguments, so make it module-level with plain values:

```python
from datetime import datetime

from fastapi import FastAPI

from wappa import InboxRef, ScheduledEvent, Scheduling

_app: FastAPI | None = None


def bind_app(app: FastAPI | None) -> None:
    global _app
    _app = app


async def run_job(
    *,
    action: str,
    job_id: str,
    inbox_id: str | None = None,
    user_id: str | None = None,
    scheduled_for: str | None = None,
    payload: dict | None = None,
) -> None:
    await Scheduling.from_app(_app).dispatch(
        ScheduledEvent(
            action=action,
            source="apscheduler",
            inbox_ref=InboxRef.whatsapp(inbox_id) if inbox_id else None,
            user_id=user_id,
            execution_id=job_id,
            scheduled_for=datetime.fromisoformat(scheduled_for) if scheduled_for else None,
            payload=payload or {},
        )
    )
```

- `dispatch` returns on success and raises on failure. Let it raise: catching it reports success and defeats the engine's retries.
- A failed Inbox lookup or an unusable cache raises its typed error before the hook runs.
- If you serve several Platforms, store the Platform with the job and build `InboxRef(platform=PlatformType(platform), inbox_id=inbox_id)` (`from wappa.schemas.core.types import PlatformType`).
- Timestamps must be timezone-aware and become UTC. A naive `scheduled_for` is refused.
- `execution_id` is for your correlation and idempotency. Wappa doesn't deduplicate on it.

## APScheduler

Start the engine after Wappa's capabilities exist: Wappa's own startup hooks use priorities up to 30, and lower numbers run first. Stop it before they close: higher shutdown priority runs first. Hooks receive the FastAPI app:

```python
from apscheduler import AsyncScheduler
from apscheduler.triggers.date import DateTrigger

scheduler = AsyncScheduler()


async def start_scheduler(app) -> None:
    bind_app(app)
    await scheduler.__aenter__()
    await scheduler.add_schedule(
        run_job,
        DateTrigger(run_time=run_at),
        id="reminder-A17",
        kwargs={
            "action": "appointment_reminder",
            "job_id": "reminder-A17",
            "inbox_id": inbox_id,
            "user_id": user_id,
            "scheduled_for": run_at.isoformat(),
            "payload": {"text": "Appointment at 3 PM"},
        },
    )
    await scheduler.start_in_background()


async def stop_scheduler(app) -> None:
    await scheduler.__aexit__(None, None, None)
    bind_app(None)


app.add_startup_hook(start_scheduler, priority=40)
app.add_shutdown_hook(stop_scheduler, priority=90)
```

Arming from a conversation is the same `add_schedule` call. Your handler imports the scheduler and passes its own scope, and a job ID derived from the inbound message ID keeps a redelivered webhook from creating a second reminder:

```python
async def process_message(self, webhook) -> None:                  # on your handler
    run_at = parse_reminder_time(webhook)                          # your code; timezone-aware
    job_id = f"reminder-{webhook.message_id}"
    await scheduler.add_schedule(
        run_job,
        DateTrigger(run_time=run_at),
        id=job_id,
        kwargs={
            "action": "appointment_reminder",
            "job_id": job_id,
            "inbox_id": self.inbox_ref.inbox_id,
            "user_id": self.user_id,
            "scheduled_for": run_at.isoformat(),
            "payload": {"text": webhook.get_message_text()},
        },
    )
```

Cancelling goes through the engine with the same ID. Moving or renaming `run_job` can orphan persisted jobs, because the store references it by import path.

That targets APScheduler 4 (`add_schedule`); on 3.x the same `run_job` goes to `add_job`. The full project is `wappa examples` → `scheduled_tasks_example`, with one-time, recurring, ending and heartbeat schedules, checked against `apscheduler==4.0.0a6`.

Give a recurring schedule's firing its own identity when you need per-occurrence idempotency, for example the job ID plus `current_job`'s fire time.

## A plain loop

```python
async def heartbeat(interval: float) -> None:
    while True:
        await run_job(action="heartbeat", job_id="heartbeat")      # no Inbox, no User: System scope
        await asyncio.sleep(interval)
```

Decide what a failure does. As written, an exception ends the loop. Track the task and cancel it on shutdown yourself.

## Another process, such as Celery

`Scheduling.from_app(app)` needs a started app in the same process, because the handler, credentials and pools live there. A separate worker starts the lifespan itself:

```python
async def run_in_worker(event: ScheduledEvent) -> None:
    async with app.router.lifespan_context(app):
        await Scheduling.from_app(app).dispatch(event)
```

Starting it per task is simple and slow, and a long-lived worker should hold it open for the process lifetime. In-process state doesn't cross over: SSE subscribers on the web process won't see events published in the worker unless your SSE setup bridges processes. Run a sync task's coroutine with your engine's normal async bridge.

## What the engine owns

Recurrence and end dates, datastore and migrations, job registration, which replica runs the scheduler, retries and backoff, timeouts, overlap and single-flight, misfires, cancellation, history and admin routes.

During shutdown, once Wappa's runtime starts draining, `dispatch` raises `RuntimeError` without running the hook, which is why the engine stops first. In-flight dispatches are tracked and drained for up to 30 seconds, then cancelled.
