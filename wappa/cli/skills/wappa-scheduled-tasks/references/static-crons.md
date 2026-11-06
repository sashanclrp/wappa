# Static crons

For a fixed schedule declared in code. If you already run a scheduler, use it instead so all your schedules live in one place.

```python
from wappa import InboxRef, SchedulingPlugin

scheduling = SchedulingPlugin()
scheduling.add_cron(
    "daily_digest", "0 8 * * *", inbox_ref=InboxRef.whatsapp(PHONE_NUMBER_ID), payload={"kind": "digest"}
)
scheduling.add_cron("cleanup", "*/30 * * * *")     # System scope: database only
app.add_plugin(scheduling)
```

`add_cron(action, expr, *, inbox_ref=None, user_id=None, tags=None, payload=None, max_retries=0, retry_delay=5.0, timeout=120)`. `user_id` needs `inbox_ref`. Declare crons before the app is built; their scope is fixed.

- The hook receives `event.action`, a fresh copy of `event.payload`, and `event.metadata` with `cron_expr` and `tags`. `event.source` is `"static_cron"`.
- A raised exception reaches `max_retries`. With the default of 0 it's logged by the engine and the next firing still runs.
- Every worker fires every cron unless `SchedulingPlugin(cron_config=CronConfig(...))` turns on fastapi-crons' distributed locking (`from fastapi_crons import CronConfig`).
- Monitoring routes mount at `/crons`, behind your auth middleware. Turn them off with `include_cron_router=False`.
- For an app built with `WappaBuilder`, pass `SchedulingPlugin(event_handler=handler)`. `Wappa` supplies its own.
