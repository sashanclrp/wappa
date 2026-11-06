# SchedulingPlugin

> Part of the Wappa Plugin Architecture. See [Architecture](./Architecture.md) for the plugin system overview, lifecycle, and patterns.

## What it does

`SchedulingPlugin` starts and stops the two trigger sources Wappa runs itself: the Redis expiry listener and built-in static crons. Both reach `WappaEventHandler.process_scheduled_event` on a fresh handler with its context prepared.

A Host-owned scheduler needs no plugin. It calls `Scheduling.from_app(app).dispatch(event)`; see [ADR-0030](../../../../docs/adr/0030-scheduled-work-dispatch.md) and `wappa/cli/examples/scheduled_tasks_example/`.

## Usage

```python
from wappa import InboxRef, SchedulingPlugin, Wappa

USER_ACTIONS = {"agent_trigger", "message_sync"}


async def expiry_subject(*, inbox_ref: InboxRef, action: str, identifier: str) -> str | None:
    return identifier if action in USER_ACTIONS else None


app = Wappa(cache="redis")
app.add_plugin(
    SchedulingPlugin(redis_expiry=True, expiry_subjects=expiry_subject).add_cron(
        "daily_report", "0 9 * * *", inbox_ref=InboxRef.whatsapp("1234567890")
    )
)
```

## Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `event_handler` | `WappaEventHandler \| None` | `None` | Handler prototype for `WappaBuilder` apps. `Wappa` supplies the one from `set_event_handler`. |
| `redis_expiry` | `bool` | `False` | Listen for Expiry Keys. Requires Redis; startup fails without it. |
| `expiry_subjects` | `ExpirySubjectBinding \| None` | `None` | Maps an expired action and identifier to its subject User. Without it every expiry is Inbox-only work. |
| `expiry_alias` | `str` | `"expiry"` | Redis pool holding Expiry Keys. |
| `expiry_reconnect_delay` | `int` | `10` | Seconds to wait before reconnecting on error. |
| `expiry_max_reconnect_attempts` | `int \| None` | `None` | Reconnect limit; `None` is unlimited. |
| `include_cron_router` | `bool` | `True` | Mount fastapi-crons monitoring at `/crons` when crons are declared. |
| `cron_config` | `CronConfig \| None` | `None` | fastapi-crons configuration, such as distributed locking. |

`add_cron(action, expr, *, inbox_ref=None, user_id=None, tags=None, payload=None, max_retries=0, retry_delay=5.0, timeout=120)` declares a static cron before the app is built. `user_id` requires `inbox_ref`. A raised exception reaches the engine's retry policy.

## Lifecycle

| Hook | Priority | What runs |
|---|---|---|
| Startup | 20 | Publish the handler prototype on `app.state` |
| Startup | 25 | Verify the expiry pool, start the listener task (`redis_expiry=True`) |
| Startup | 30 | Register crons, start the engine, fill the `/crons` router (crons declared) |
| Shutdown | 85 | Stop the cron engine, with a 15-second bound |
| Shutdown | 80 | Cancel the listener task, with a 5-second bound |

In-flight scheduled work is tracked by `BackgroundWorkTracker`, which the core plugin drains after these hooks.

## Behaviour

The handler's capabilities depend on the event's scope:

| Scope | Handler has |
|---|---|
| Inbox and User | Canonical `self.user_id`, `self.messenger`, `self.whatsapp` or `self.instagram`, `self.cache_factory` |
| Inbox only | The Messengers; no User and no `self.cache_factory` |
| System | Neither; only the database factories |

`self.db` and `self.db_read` are set in every scope when the database plugin is configured.

Failures differ by source. A static cron or Host callback awaits the dispatch and receives the exception. Redis expiry has no awaiting caller, so a failure is logged with its action and identifier. Redis keeps its existing delivery behaviour: every listening process receives each expiry, a key that expires while none listens is missed, and the key is gone once it fires.

Listener startup enables `notify-keyspace-events Ex`. A managed Redis that forbids `CONFIG SET` needs that setting applied by hand.
