# CronPlugin

> Part of the Wappa Plugin Architecture. See [Architecture](./Architecture.md) for the plugin system overview, lifecycle, and patterns.

## What it does

`CronPlugin` schedules recurring background tasks that fire events into the `WappaEventHandler` pipeline with full Wappa infrastructure access (messenger, cache, database). It wraps [fastapi-crons](https://pypi.org/project/fastapi-crons/) and bridges cron execution into the Wappa event system.

Crons are registered at plugin level before app startup — these are **system crons**. When a cron fires, the plugin creates a `CronEvent`, bootstraps a `WappaContext`, clones the handler via `with_context()`, and dispatches to `process_cron_event()`. Users identify which cron to handle via `event.cron_id`.

## How to activate

```python
from wappa import Wappa, WappaEventHandler, CronEvent
from wappa.core.plugins import CronPlugin

class MyHandler(WappaEventHandler):
    async def process_message(self, webhook):
        await self.messenger.send_text(webhook.user.user_id, "Hello!")

    async def process_cron_event(self, event: CronEvent):
        match event.cron_id:
            case "daily_report":
                await self.messenger.send_text(
                    text="Here's your daily report!",
                    recipient=event.user_id,
                )
            case "cleanup":
                async with self.db() as session:
                    await cleanup_expired_sessions(session)

handler = MyHandler()
app = Wappa(cache="redis", ...)
app.register_handler(handler)

cron_plugin = CronPlugin(event_handler=handler)
cron_plugin.add_cron(
    cron_id="daily_report",
    expr="0 9 * * *",
    tenant_id="acme",
    user_id="5551234567",
    tags=["reports"],
    payload={"report_type": "summary"},
)
cron_plugin.add_cron(
    cron_id="cleanup",
    expr="0 */6 * * *",
    tags=["maintenance"],
)
app.add_plugin(cron_plugin)
```

Fluent API alternative:

```python
cron_plugin = (
    CronPlugin(event_handler=handler)
    .add_cron(cron_id="hourly_sync", expr="0 * * * *", tags=["sync"])
    .add_cron(cron_id="daily_cleanup", expr="0 3 * * *", tags=["maintenance"])
    .add_cron(cron_id="weekly_report", expr="0 9 * * 1",
              tenant_id="acme", user_id="5551234567", tags=["reports"])
)
app.add_plugin(cron_plugin)
```

## Configuration options

### CronPlugin constructor

| Parameter | Type | Default | Description |
|---|---|---|---|
| `event_handler` | `WappaEventHandler` | (required) | Handler prototype for cloning per cron execution |
| `include_router` | `bool` | `True` | Mount fastapi-crons monitoring endpoints at `/crons` |
| `config` | `CronConfig \| None` | `None` | fastapi-crons config (distributed locking, etc.) |

### add_cron()

| Parameter | Type | Default | Description |
|---|---|---|---|
| `cron_id` | `str` | (required) | Unique job name — primary dispatch key in `process_cron_event()` |
| `expr` | `str` | (required) | Cron expression (e.g., `"0 9 * * *"`) |
| `tenant_id` | `str \| None` | `None` | Tenant scope — if set, full context (messenger, cache, db) available |
| `user_id` | `str \| None` | `None` | User scope — for messenger/cache targeting |
| `tags` | `list[str] \| None` | `None` | Tags for secondary filtering |
| `payload` | `dict \| None` | `None` | Static data available in the CronEvent |
| `max_retries` | `int` | `0` | Retry attempts on failure |
| `retry_delay` | `float` | `5.0` | Initial retry delay in seconds |
| `timeout` | `int` | `120` | Execution timeout in seconds |

Returns `self` for fluent API chaining.

## Cron expressions

Standard 5-field format:

```
* * * * *
│ │ │ │ └─ Day of week (0-6, Sunday=0)
│ │ │ └─── Month (1-12)
│ │ └───── Day of month (1-31)
│ └─────── Hour (0-23)
└───────── Minute (0-59)
```

| Expression | Schedule |
|-----------|----------|
| `* * * * *` | Every minute |
| `*/15 * * * *` | Every 15 minutes |
| `0 * * * *` | Every hour |
| `0 9 * * *` | Daily at 9 AM |
| `0 0 * * 0` | Weekly on Sunday at midnight |
| `0 0 1 * *` | Monthly on the 1st |
| `30 8 * * 1-5` | Weekdays at 8:30 AM |

## Context rules

| Registration | Infrastructure Available |
|-------------|------------------------|
| `tenant_id` + `user_id` set | `self.messenger`, `self.cache_factory`, `self.db` |
| `tenant_id` set, no `user_id` | `self.db` only (messenger/cache require user_id) |
| No `tenant_id` (system cron) | `self.db` only (no tenant isolation) |

Always check availability before using:

```python
async def process_cron_event(self, event: CronEvent):
    if event.cron_id == "send_reminder" and self.messenger:
        await self.messenger.send_text("Reminder!", event.user_id)

    if event.cron_id == "cleanup" and self.db:
        async with self.db() as session:
            await cleanup(session)
```

## CronEvent model

```python
class CronEvent(BaseModel):
    cron_id: str              # Unique job name — primary dispatch key
    cron_expr: str            # Cron expression ("0 9 * * *")
    tags: list[str]           # Tags from registration
    tenant_id: str | None     # Tenant scope (None for system crons)
    user_id: str | None       # User scope (None if not set)
    payload: dict[str, Any]   # Static data from registration
    metadata: dict[str, Any]  # Runtime info (actual_time)
    timestamp: datetime       # When the event fired
```

## Dispatch patterns

### By cron_id (primary)

```python
async def process_cron_event(self, event: CronEvent):
    match event.cron_id:
        case "daily_report": await self.send_report(event)
        case "cleanup": await self.run_cleanup(event)
        case "billing_check": await self.check_billing(event)
```

### By tags (secondary)

```python
async def process_cron_event(self, event: CronEvent):
    if "maintenance" in event.tags:
        await self.run_maintenance(event)
    elif "billing" in event.tags:
        await self.run_billing(event)
```

### Using payload

```python
cron_plugin.add_cron(
    cron_id="send_report",
    expr="0 9 * * *",
    tenant_id="acme",
    user_id="5551234567",
    payload={"report_type": "daily", "format": "pdf"},
)

async def process_cron_event(self, event: CronEvent):
    if event.cron_id == "send_report":
        report = await generate_report(
            event.payload["report_type"],
            event.payload["format"],
        )
        await self.messenger.send_document(report, event.user_id)
```

## Monitoring endpoints

When `include_router=True` (default), fastapi-crons monitoring endpoints are mounted at `/crons`:

| Method | Path | Description |
|--------|------|-------------|
| GET | `/crons` | List all jobs with status and schedule |
| GET | `/crons/health` | Scheduler health check |
| POST | `/crons/{job_name}/run` | Manually trigger a job |

## How it works internally

```
fastapi-crons fires job on schedule
    │
    └── CronPlugin._fire_cron_event(registration)
        ├── Creates CronEvent from registration data + timestamp
        ├── If tenant_id: WappaContextFactory → full context
        │   Else: WappaContextFactory → db-only context
        ├── handler.with_context(...) → cloned handler
        └── CronEventDispatcher → handler.process_cron_event(event)
```

The plugin registers each cron as an internal `fastapi-crons` job via a closure-captured callback. No user-defined callbacks are needed — users only implement `process_cron_event()` in their event handler.

Startup priority is 30 (after core=10, infra=20, listeners=25), ensuring all infrastructure is ready before crons start firing.

## Imports

```python
from wappa import CronEvent
from wappa.core.plugins import CronPlugin
```
