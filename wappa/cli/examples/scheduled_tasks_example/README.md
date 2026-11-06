# Wappa Scheduled Tasks Example

A Host-owned scheduler runs reminders, reports and heartbeats through one `process_scheduled_event` hook. Wappa prepares the handler on every firing: the Inbox, canonical User, Messengers, caches and database factories are ready, so no feature rebuilds them.

## The two pieces

`app/jobs.py` holds the one callback every schedule uses. It is a module-level function with plain arguments, which is what a persistent job store needs, and it does one thing:

```python
await Scheduling.from_app(app).dispatch(
    ScheduledEvent(action=action, source="apscheduler", inbox_ref=inbox_ref, user_id=user_id, execution_id=schedule_id, payload=payload)
)
```

`app/master_event.py` routes by action. The scope is explicit on each event:

| Task | Scope | The handler has |
| --- | --- | --- |
| One-time reminder | Inbox and User | Messenger, `self.whatsapp`, User cache, canonical `self.user_id` |
| Recurring report, with or without an end | Inbox | Messenger, `self.whatsapp`; `self.scope(user_id=...)` for each recipient |
| Heartbeat | System | Database factories only |

## What stays with your scheduler

Recurrence and end dates, job storage and migrations, registration, retries, overlap, misfires, cancellation and history all belong to the engine and the Host. Wappa stores no job. `dispatch` returns on success and raises on failure, so the engine's retry policy sees the real outcome.

`heartbeat_loop` in `jobs.py` shows the same lane with no engine at all, and Celery or a custom worker calls the same method.

## Run it

APScheduler is your dependency, not Wappa's:

```bash
uv add "apscheduler==4.0.0a6"
uv run wappa dev app/main.py
```

Timers that belong in Redis, such as debounce and inactivity, use `wappa_expiry_example` instead.
