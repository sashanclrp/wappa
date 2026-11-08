---
name: wappa-scheduled-tasks
description: Runs a Host's timed work through Wappa's single scheduled hook, process_scheduled_event, on a handler with the Messenger, caches, database and SSE identity already prepared. Covers reminders, debounce and inactivity timers, recurring tasks with or without an end, heartbeats, Scheduling.dispatch from APScheduler, Celery or a custom loop, SchedulingPlugin, Redis expiry triggers and subject bindings, static crons, self.scope, identity rebinding, and moving off CronPlugin, ExpiryPlugin and expiry_registry. Use when a Wappa app needs anything to happen later or repeatedly, or when upgrading scheduled code to Wappa 0.34. Not for cache design (wappa-state-and-storage) or conversation logic (wappa-apps).
---

# Scheduled Tasks on Wappa

Every feature that fires later, whatever fires it, runs in one hook. Wappa prepares the handler; the Host decides what happens. A new reminder or heartbeat adds one `case`, never another way to build a Messenger.

Requires Wappa 0.34 or later. Check with `uv run python -c "import wappa; print(wappa.__version__)"`.

```python
from wappa import ScheduledEvent, WappaEventHandler

class Handler(WappaEventHandler):
    async def process_scheduled_event(self, event: ScheduledEvent) -> None:
        deps = await build_host_dependencies(self)     # once per invocation; a field is None if its scope lacks it
        match event.action:
            case "appointment_reminder":
                await send_reminder(self, deps, event)
            case "weekly_report":
                await send_reports(self, deps, event)
            case _:
                raise ValueError(f"Unknown scheduled action: {event.action}")
```

## Workflow

```
Progress:
- [ ] 1. Pick the trigger source for each behavior
- [ ] 2. State each task's scope: Inbox and User, Inbox only, or System
- [ ] 3. Wire the source, using its reference
- [ ] 4. Route in process_scheduled_event; build Host dependencies once at the top
- [ ] 5. Verify: unit test the hook, then one real firing; report what wasn't proven
```

**1. Pick the source.**

| Behavior | Source | Load |
| --- | --- | --- |
| Timer or debounce, armed at runtime and reset on activity ("15 minutes after the last message") | Redis expiry | `references/expiry-triggers.md` |
| One-time reminder at a date | Your scheduler | `references/host-schedulers.md` |
| Recurring task with or without an end, created at runtime | Your scheduler | `references/host-schedulers.md` |
| Heartbeat | Your scheduler or loop | `references/host-schedulers.md` |
| Fixed schedule declared in code | Static cron, or your scheduler if you already run one | `references/static-crons.md` |
| Existing `CronPlugin`, `ExpiryPlugin` or `expiry_registry` code | Move it | `references/migrating.md` |

A Host scheduler calls `Scheduling.dispatch` directly and needs no `SchedulingPlugin`; the plugin only runs Redis expiry and static crons. Use Redis for a short timer you re-arm. Since 0.34.6 arming/renewal also indexes the pending occurrence in Redis; startup and short bounded ticks recover missed expirations at least once while Redis retains its data. Keep calendar/recurring jobs in your scheduler. Pre-upgrade keys need re-arming for recovery.

**2. State the scope.** It decides what exists on the handler, and it's explicit on every event:

| `ScheduledEvent` has | Handler has | `None` |
| --- | --- | --- |
| `inbox_ref` and `user_id` | Canonical `self.user_id`, `self.messenger`, `self.whatsapp` or `self.instagram`, `self.cache_factory` | The other Platform Messenger |
| `inbox_ref` only | `self.messenger`, `self.whatsapp` or `self.instagram` | `self.user_id`, `self.cache_factory` |
| neither | Nothing Inbox-related | `self.inbox_ref`, `self.user_id`, every Messenger, `self.cache_factory` |

`self.db` and `self.db_read` are set in every scope when the database plugin is configured, and `None` otherwise. Since 0.34.2 Inbox-bound scopes defer send credentials until the first Messenger operation: non-sending tasks run during credential outages. Identity and Platform Messenger binding need no credentials. A send raises the original typed Directory error; a failed resolution is not cached, so the next use retries. Concurrent first uses share one successful pipeline and middleware runs once per send.

**3–4. Build.** These rules hold for every source:

- **Never build context by hand.** No Messenger factories, cache factories or SSE scopes in a feature. If the handler lacks something, the event's scope is wrong or the task needs `self.scope`.
- **Don't swallow failures.** A raised exception reaches your scheduler or cron engine, and its retry policy is the only retry there is. Indexed Redis expiry has no caller: Wappa logs failures and retains the pending occurrence for recovery.
- **Every firing can repeat.** Workers receive the same expiry, engines retry, and Wappa doesn't deduplicate. Make side effects idempotent with a key you own. A Host scheduler supplies event.execution_id. Indexed Redis expiry supplies its pending generation and original scheduled_for; old unindexed notifications still have neither. Correlation is not an exactly-once or business-admission guarantee. If you claim the key before the side effect, release it when the side effect fails, or the retry finds the claim and silently does nothing.
- **Sending later isn't sending now.** A task can fire outside the Platform's 24-hour window, where free-form text is rejected. On WhatsApp, use an approved Template (`self.whatsapp.templates`, see the `wappa-apps` skill, its WhatsApp reference). Instagram has no Templates. Check `result.success`: a rejected send is a result, not an exception.
- **The Host owns the rest:** recurrence/end dates, external job storage, business retry policy, overlap, history, admin routes and send fences. Wappa owns its Redis expiry index, short admission claims, cancel/rebind and recovery; these do not replace business coordination.
- **A timer's value is empty.** Keep data in your cache or database. `event.payload` carries data only when your own caller passed it.
- **Never read a User from an identifier's shape.** A subject comes from `event.user_id`, which you supplied or your binding returned. A message ID stays in `event.identifier`.
- **Keep Host policy in the hook.** Admission checks, business state and Agent orchestration run after the prepared context, inside your code.

### Another subject mid-task

```python
async with self.scope(user_id=owner_id) as owner:      # or inbox_ref=other_inbox, user_id=...
    await owner.cache_factory.create_user_cache().upsert({"digest_sent": True})
```

`self.scope` prepares that subject through the same path, including your identity resolver, and restores the current SSE identity on exit. `owner` is a separate clone: dependencies you set on `self` aren't there, so build them for it if needed. To send within the same Inbox, `self.messenger` with an explicit target is enough.

### Identity

Your `IIdentityResolver` gets the task's `inbox_ref` and runs before any User cache exists, so `event.user_id` and `self.user_id` are canonical inside the hook. A resolver failure stops the task; if a stale identifier should still fire, catch the failure inside your resolver. SSE publishes the Inbox and canonical User: call `update_identity(bsuid=..., phone_number=...)` (`wappa.sse`) when subscribers need more.

**5. Verify.** Unit test the hook once per scope, using the pattern in `references/testing.md`. Then fire one real task and check the log line, the side effect, and a raised failure reaching your engine. Correct at most three times against specific failing evidence, and report what stays unproven.
