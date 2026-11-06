---
status: draft (design proposed 2026-11-06; no code; needs a grill session before pending/)
origin: Symphonai runs its own APScheduler with runtime jobs; Wappa's cron lane only accepts crons declared at build time
related: Instagram conversations series (Gate C order), Platform Messengers on the handler, developer-skills refresh (I08)
---

# Scheduler-agnostic cron lane: any scheduler fires into `process_cron_event`

Wappa's cron lane today is one plugin that does two jobs. `CronPlugin` (`wappa/core/plugins/cron_plugin.py`) **schedules** jobs with fastapi-crons from registrations declared once at build time (`add_cron(cron_id, expr, *, inbox_ref, user_id, tags, payload, max_retries, retry_delay, timeout)`), and it **fires** them: it builds a `CronEvent`, builds the dispatch context through `WappaContextFactory`, clones the handler with `with_context()`, and dispatches through `CronEventDispatcher` to `process_cron_event`. Because the two are fused, a Host that needs runtime scheduling (a reminder two hours after this User's last message, a campaign window per Inbox, a job created by an operator) cannot use the cron lane at all. Symphonai already runs native APScheduler behind its own Scheduler service, which owns acceptance, task limits, readiness and drain (`symphonai/services/scheduler/ARCHITECTURE.md`); its job handlers therefore build Wappa context themselves instead of receiving a ready handler.

This PRD splits firing from scheduling. Wappa exposes one public way to fire a cron event with a fully built context, and every scheduler, including Wappa's own fastapi-crons plugin, becomes an adapter that calls it.

## Today

- Crons are static: declared before startup, each with a fixed Inbox and User. Per-User timers at runtime use the expiry/trigger cache (`EXPTRIGGER`) instead, which is a different lane (`process_expiry`-style triggers), not a scheduler.
- Every worker and host fires every cron unless `CronPlugin(config=CronConfig(...))` enables fastapi-crons distributed locking.
- An Inbox-scoped cron without a `user_id` gets **no Messenger**: `_create_request_handler` calls `create_context(..., include_messenger=reg.user_id is not None)`, so an Inbox-wide job (a daily broadcast to many Users) cannot send. This is a bug to fix here.
- The firing logic (`_fire_cron_event`, `_create_request_handler`) is private to the plugin and needs its startup state (`app.state.wappa_context_factory`, the dispatcher, the handler prototype held by the plugin).

## Goals

1. One public, documented entry point that fires a cron event into `process_cron_event` with the same context a webhook dispatch gets: `self.messenger`, the Platform Messengers (`self.whatsapp` / `self.instagram`), caches, `self.db` / `self.db_read`.
2. Any scheduler can drive it: Wappa's fastapi-crons `CronPlugin`, a Host's APScheduler (Symphonai), Celery beat, a cloud scheduler calling an HTTP endpoint, or a one-off call from Host code.
3. Runtime scheduling becomes possible without Wappa owning a scheduler: the Host's scheduler holds the jobs, Wappa only fires them.
4. Inbox-scoped crons get a Messenger with or without a `user_id`.
5. Handler code is identical whichever scheduler fired the event.

## Non-goals

- Wappa does not ship or own a runtime job store, recurrence engine or distributed scheduler in this PRD. Deduplication, persistence, misfire policy, retries across restarts and drain stay with the scheduler that owns the job.
- No change to the expiry/trigger cache lane.
- A ready-made APScheduler plugin is deferred (see Phase 3): with Symphonai as the only Host needing it, it would be a one-adapter abstraction.

## Design

### 1. The public entry point: `CronEvents`

A small public object in `wappa/core/events/cron_events.py`, exported from `wappa` (name to settle in the grill session; `CronEvents` mirrors `OutboundRuntime.from_app`):

```python
cron_events = CronEvents.from_app(app)          # FastAPI app built by Wappa
result = await cron_events.fire(
    "nudge_followup",
    inbox_ref=inbox_ref,                         # optional; None = system cron (db-only)
    user_id=user_id,                             # optional; requires inbox_ref
    payload={"episode_id": "..."},
    tags=["nudges"],
    cron_expr=None,                              # informational: the schedule that fired, if any
    fired_at=None,                               # defaults to now (UTC)
)
```

- `from_app` reads what startup already placed on `app.state`: the `WappaContextFactory`, the event handler prototype (stored by the app at startup, no longer only inside `CronPlugin`) and a `CronEventDispatcher`. It raises a clear error if called before startup.
- `fire` builds the `CronEvent` (`cron_id`, `cron_expr`, `tags`, `inbox_ref`, `user_id`, `payload`, `timestamp`, `metadata.actual_time`), builds the context, clones the handler with `with_context()`, and dispatches. The context rules:
  - `inbox_ref` set: full context, including the Messenger and the Platform Messengers **whether or not** `user_id` is set; with `user_id`, the user-scoped caches too.
  - `inbox_ref` unset: system cron, database-only context (`self.db`, `self.db_read`); `self.messenger` and the Platform Messengers are `None`.
  - `user_id` without `inbox_ref`: `ValueError`, as `add_cron` does today.
- `fire` returns the dispatcher's result (`success`, `error`, timing) and never raises for a handler failure, so the calling scheduler applies its own retry policy. It raises only for programming errors (unknown app state, invalid arguments).
- `fire` does not deduplicate: one call is one dispatch. Exactly-once is the scheduler's job (APScheduler with a shared job store, fastapi-crons with `CronConfig` locking).
- Credential resolution goes through the same Inbox Directory and resolver path as webhook intake, so a disconnected or unknown Inbox fails the same way (a failed result naming the Inbox, no send).

### 2. `CronPlugin` becomes one adapter

`CronPlugin.add_cron(...)` keeps its signature and stays the zero-setup option for static crons. Its fastapi-crons callback shrinks to `await CronEvents.from_app(app).fire(reg.cron_id, inbox_ref=reg.inbox_ref, user_id=reg.user_id, payload=reg.payload, tags=reg.tags, cron_expr=reg.expr)`; `_fire_cron_event` and `_create_request_handler` are deleted. The plugin still owns fastapi-crons startup, the `/crons` monitoring router and the bounded drain on shutdown.

### 3. Host schedulers call the same entry point

Symphonai keeps APScheduler and its Scheduler service unchanged; only the job body changes:

```python
async def nudge_job(inbox_ns: str, user_id: str, episode_id: str) -> None:
    result = await CronEvents.from_app(app).fire(
        "nudge_followup",
        inbox_ref=InboxRef.from_cache_namespace(inbox_ns),
        user_id=user_id,
        payload={"episode_id": episode_id},
    )
    if not result["success"]:
        ...  # Symphonai's own retry / acceptance policy

scheduler.add_job(nudge_job, trigger="date", run_date=when, args=[...], id=f"nudge:{episode_id}")
```

Job arguments must be serializable for persistent job stores, so they carry `InboxRef.cache_namespace` (or the Platform and Inbox ID) and the User ID, never a Wappa object. The handler side is the same as for any cron:

```python
async def process_cron_event(self, event):
    match event.cron_id:
        case "nudge_followup":
            target = DirectMessage(inbox_ref=self.inbox_ref, addresses=...)  # from Host-stored User addresses
            await self.messenger.send_text("Still there? 👋", target)
```

### 4. Optional HTTP trigger

For external schedulers (cloud scheduler, Kubernetes CronJob), an opt-in authenticated route `POST /crons/fire` with the same fields, protected by the existing Host auth for service routes (never public). Off by default; decided in the grill session.

## Phased rollout

1. `CronEvents` and the `app.state` handler prototype; `CronPlugin` refactored onto it; the Inbox-without-User Messenger fix. Breaking only for code that reached into the plugin's private methods (listed in the CHANGELOG).
2. Docs and skills: public contract section, the cron lane in the event-lanes tables, the runtime-scheduling recipe with APScheduler, the multi-worker warning.
3. Deferred: an `APSchedulerPlugin` with runtime `add_job` / `remove_job` and a Redis job store, only when a second Host needs it; and the optional HTTP trigger.

## Test plan

- `fire` with each context shape: system cron (db only, no Messenger), Inbox cron without User (Messenger present, the bug fix), Inbox + User cron (user caches); `user_id` without `inbox_ref` raises.
- A handler failure returns `success: false` and does not raise; a disconnected Inbox returns a failed result with no send.
- `CronPlugin` still fires static crons through `fire` (fastapi-crons callback test), and the `/crons` router still mounts.
- A fake external scheduler (plain asyncio task) calls `fire` at runtime and the handler receives the same `CronEvent` fields and Messengers as a plugin-fired cron.
- Calling `from_app` before startup raises a clear error.
- The Platform Messengers (`self.whatsapp` / `self.instagram`) are bound in cron context exactly as in webhook context.

## Open questions

- Name and home: `CronEvents.from_app(app)`, a method on the `Wappa` instance, or both?
- Should `fire` accept a `CronEvent` directly for schedulers that already build one?
- Opt-in HTTP trigger: worth shipping, and with which auth (Host service auth, a dedicated secret)?
- Should the event carry the scheduler's job ID (`metadata.job_id`) for correlation and idempotency in the handler?
- Does the deferred `APSchedulerPlugin` belong in Wappa at all, or only as a documented recipe?

## Exit criteria

- `process_cron_event` is reachable from any scheduler through one public entry point, with the same context as a webhook dispatch, Platform Messengers included.
- `CronPlugin` uses that entry point; no second firing path exists.
- Inbox-scoped crons without a User can send.
- Symphonai's APScheduler jobs fire through it in the Gate C migration, with no Wappa context building left in Symphonai.
- Public contract, `wappa/core/events` architecture doc, CHANGELOG and the developer skills describe the lane, the runtime-scheduling recipe and the multi-worker rule.
