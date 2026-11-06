---
status: draft (design proposed 2026-11-06, revised 2026-11-06 with the Symphonai expiry-trigger inventory; no code; needs a grill session and an ADR before pending/; implement after Instagram Gate C)
origin: Symphonai runs its own APScheduler with runtime jobs and rebuilt Wappa context for Redis expiry triggers; Wappa's cron lane only accepts crons declared at build time
related: Instagram conversations series (Gate C order), Platform Messengers on the handler, developer-skills refresh (I08), wappa/core/expiry, wappa/core/plugins/cron_plugin.py
---

# Crons domain: scheduled work with Inbox and User context, on any scheduler

A Host often needs to say "this process will send something to this User through this Inbox, later or repeatedly". Wappa has two unrelated mechanisms for that today, and neither gives the work the context a webhook gets. This PRD makes scheduled work one Wappa domain, the **Crons domain**: one model for every kind of scheduled work (timers, one-time tasks, recurring tasks that expire, recurring tasks that run until killed, heartbeats), one firing path into `WappaEventHandler.process_cron_event` with the full dispatch context, a prebuilt Host API on the handler, and a reliable default backend that also lets external schedulers (APScheduler, Celery beat, a cloud scheduler) drive it.

Wappa owns the infrastructure: scheduling, durable storage, single-claimant firing, context building, concurrency control, parent and child links, querying and cancelling. What a task means, who may create it, which Users it reaches and what it sends is the Host's business. The domain is deliberately not opinionated beyond that line.

## Today

**Crons** (`wappa/core/plugins/cron_plugin.py`). `CronPlugin.add_cron(cron_id, expr, *, inbox_ref, user_id, tags, payload, max_retries, retry_delay, timeout)` registers crons once at build time on fastapi-crons. A firing builds a `CronEvent`, builds context through `WappaContextFactory`, clones the handler with `with_context()` and dispatches to `process_cron_event`. Limits:

- Static only: no way to create, change or cancel a cron at runtime.
- An Inbox-scoped cron without a `user_id` gets no Messenger (`include_messenger=reg.user_id is not None` in `_create_request_handler`), so an Inbox-wide job cannot send. Bug.
- Every worker and host fires every cron unless fastapi-crons `CronConfig` locking is configured.
- Firing is private to the plugin, so a Host's own scheduler cannot fire into the handler.

**Expiry triggers** (`wappa/core/expiry/`). The Host writes a Redis key `{inbox}:EXPTRIGGER:{action}:{identifier}` with a TTL. Redis publishes an `expired` keyspace event; the listener resolves a free function registered with `@expiry_registry.on_expire_action("action")` and runs `handler(identifier, full_key)` as a fire-and-forget task. Their strength is the one this PRD keeps: each trigger is scoped to an Inbox and, through the identifier, a User. Their problems:

| Problem | Effect |
| --- | --- |
| Outside `WappaEventHandler` | no `self.messenger`, no Platform Messengers, no middleware unless wrapped by hand, no shared Dispatch Context; handlers rebuild context through a global `AppContext` and `create_expiry_messenger` / `create_expiry_cache_factory` / `parse_inbox_ref_from_expired_key` |
| Keyspace events reach every subscriber | with N workers every one receives the event and Wappa has no claim, so a nudge can be sent N times unless the Host adds leases |
| Pub/sub is at most once | events during a deploy, restart or listener reconnect are lost; nothing replays them |
| The value is gone at expiry | no payload travels with the trigger; Hosts encode it in the identifier or keep shadow keys |
| Imprecise timing | Redis emits `expired` when it actually deletes the key, which can lag on a large keyspace |
| Redis only | memory and JSON Hosts have no timers |

Symphonai shows the cost: `symphonai/engine/expiry/` carries a `handler_shell`, its own context helpers, a manual `MessengerPipeline(...)` wrap and run-serialization leases, and its recurring jobs run on native APScheduler behind its own Scheduler service (acceptance, task limits, readiness, drain). Its trigger families are message buffering before processing (debounce), Engagement Episodes and Nudges, and several reconciliation and housekeeping jobs.

## Use cases this domain must serve

1. **Debounced message buffering.** Each inbound message pushes back a short timer for this User on this Inbox; when the User stops typing, the buffered messages are processed once.
2. **Nudges and Episodes.** A timer per User and Inbox with a payload (episode ID, step), cancelled when the User answers, rescheduled when the Episode advances.
3. **Admin-created recurring analysis.** An admin in a Host creates a cron that analyzes campaigns every morning and sends WhatsApp Templates to three coworkers: same Inbox, different Users per send, each send starting a new conversation.
4. **A report for its owner.** A User starts a process; when it finishes, a report goes to that User and to the Users the owner chose.
5. **Fan-out work.** A cron reads a tickets table, finds what is assigned, and creates one child task per ticket so several agents process tickets in parallel; sub-tickets of one ticket stay with the same agent, one at a time.
6. **Heartbeats.** A short-interval liveness or polling job that must never overlap itself and must not pile up runs after a stall.
7. **Static housekeeping.** Daily reports and reconciliation declared once at build time, as `add_cron` does today.

## The domain model

### Kinds

All five kinds are one entity, a **Schedule**, differing only in trigger and end. A firing of a Schedule is a **Run**.

| Kind | Trigger | Ends | Typical use |
| --- | --- | --- | --- |
| **Timer** | after a delay (`after=timedelta`); `reschedule` pushes it back (debounce) | after one Run, or on cancel | buffering, nudges, reminders |
| **One-time task** | at a time (`at=datetime`) or now (`at=None`) | after one Run (with retries) | fan-out children, deferred work, a report job |
| **Recurring, expiring** | cron expression (`cron="0 9 * * *", tz=...`) or interval (`every=timedelta`) | at `until=datetime` or after `max_runs` | a campaign window, a 30-day follow-up series |
| **Recurring, non-expiring** | cron expression or interval | only when cancelled (by a User, an admin or the Host) | admin analysis, standing reports |
| **Heartbeat** | short interval (`every=timedelta`) | when cancelled or on shutdown | liveness, polling; overlap `skip`, misfire `coalesce`, no run history by default |

### Schedule fields

- `schedule_id`: Wappa-generated, stable; also the idempotency base.
- `action`: the Host's name for the work (`"nudge"`, `"campaign_report"`, `"ticket"`); the handler dispatches on it (today's `cron_id`).
- `key`: optional Host identifier, unique per `(scope, action, key)`, so `schedule`, `reschedule` and `cancel` can address "the nudge for this User" without storing IDs (today's expiry `identifier`).
- **Scope**: `inbox_ref: InboxRef | None` and `user_id: str | None`. This is the context rule: a Schedule scoped to an Inbox and a User is "this process, for this User, through this Inbox". `user_id` requires `inbox_ref`. No scope is a system schedule.
- `payload`: JSON, opaque, stored with the Schedule and delivered on every Run (bounded size, proposed 16 KB; large data stays in the Host's store and the payload carries its ID).
- `labels`: optional `dict[str, str]`, opaque and indexed, so `list` and `cancel` can filter on them (for example `{"owner": admin_id, "episode": episode_id}`). Wappa never interprets a label. This replaces the `owner` field of the first draft: who created a Schedule, who may see it and who gets its report are Host concepts, and the only thing Wappa needs is a generic way to find Schedules again (see "Decisions so far").
- `parent_id`: optional link to the Schedule that created this one (fan-out); cancelling a parent can cascade to its children.
- `concurrency_key`: optional; Runs sharing a key never run at the same time across all workers (one ticket's sub-tickets stay serial while different tickets run in parallel).
- Policies: `overlap` (`skip` | `queue` | `allow`), `misfire` (`run_once` | `skip` | `catch_up`, with a grace period), `retries` (count and backoff), `timeout` (with lease renewal for long Runs).
- Debounce ceiling: `max_delay` on a Timer, optional. `reschedule` pushes the Timer back but never past `first_scheduled_at + max_delay` (debounce with a maximum wait). This is a generic scheduling rule, not a business one, and Symphonai's message sync needs it today (see the inventory).
- State: `status` (`scheduled`, `running`, `paused`, `completed`, `cancelled`, `failed`), `next_run_at`, `last_run_at`, `last_outcome`, `run_count`, `created_at`.

## Context: how a Run gets its Inbox and User

Every Run is dispatched through the **same Dispatch Context builder as webhook intake** (the shared `DispatchContextBuilder` behind `WappaContextFactory`), so a Run's handler looks exactly like a webhook's.

- **Inbox and User scope:** `self.inbox_ref`, `self.user_id`, `self.messenger`, the Platform Messengers (`self.whatsapp` / `self.instagram`), the Inbox's caches and the User's caches, `self.db` / `self.db_read`, and the middleware pipeline.
- **Inbox scope, no User:** the same minus the User caches. The Messenger is always present, fixing today's bug: a Messenger belongs to the Inbox, not to a User.
- **No scope (system):** `self.db` / `self.db_read` and the Crons API only.
- **The same SSE scope and identity rules as a webhook.** Run dispatch opens `sse_event_scope` exactly as `wappa/core/inbound/runtime.py` does for webhooks, and passes the scheduled `user_id` through the Host's `IIdentityResolver` before building the User caches, so a Timer armed under a phone number reaches the cache that now lives under the BSUID. Today Symphonai does both by hand (`resolve_expiry_user_id`, `apply_sse_identity_from_cache`); after this they are Wappa's.
- Credentials resolve through the Inbox Directory as for webhooks. A disconnected or unknown Inbox makes the Run fail with a clear outcome and no send; a recurring Schedule on a disconnected Inbox is paused, not silently retried forever.

**Reaching other Users and Inboxes in one Run.** The scope is the Run's default subject, not a limit. Sending to another User of the same Inbox needs nothing new: the Messenger is Inbox-bound and the target carries the User (`DirectMessage(inbox_ref=self.inbox_ref, addresses=...)`, or a Template to a phone number). To read or write another User's state, or to work through another Inbox, the handler asks the runtime for a scoped context instead of building one:

```python
coworker = await self.scope(user_id="573000000001")          # same Inbox, another User
await coworker.user_cache.set(...)
other_inbox = await self.scope(inbox_ref=InboxRef.whatsapp("5678"), user_id=...)
await other_inbox.messenger.send_text("...", target)
```

`self.scope(...)` returns a bound context (Messenger, Platform Messengers, caches) built by the same builder, so cross-User and cross-Inbox work never touches credentials or keys by hand. Whether a cron may act on a given User or Inbox is Host policy.

## Host API (prebuilt on the handler)

The runtime builds `self.crons` on every dispatch (webhook, Run, API or external event), scoped by default to the current Inbox and User, following the prebuilt-Messengers rule: a Host never constructs it.

```python
# Timer: debounce message buffering for this User on this Inbox
await self.crons.reschedule("buffer_flush", after=timedelta(seconds=4))

# Timer with payload, addressed by key; cancelled when the User answers
await self.crons.schedule("nudge", key=episode.id, after=timedelta(hours=2), payload={"step": 3})
await self.crons.cancel("nudge", key=episode.id)

# Recurring, non-expiring, created by an admin; system scope or one Inbox.
# Who the owner is and who gets notified are Host data: a label to find it again, a payload to act on.
await self.crons.schedule("campaign_report", cron="0 8 * * 1-5", tz="America/Bogota",
                          labels={"owner": admin_id}, payload={"notify": [u1, u2, u3]}, scope=None)

# Recurring, expiring
await self.crons.schedule("follow_up", every=timedelta(days=1), until=start + timedelta(days=30))

# Fan-out: one child per ticket, sub-tickets serialized per ticket
for ticket in tickets:
    await self.crons.schedule("ticket", key=ticket.id, payload={"ticket": ticket.id},
                              parent_id=event.schedule_id, concurrency_key=f"ticket:{ticket.root_id}")

# Heartbeat
await self.crons.schedule("poll_inbox_health", every=timedelta(seconds=30), overlap="skip", misfire="coalesce")

# Query and control
await self.crons.get(schedule_id); await self.crons.list(action="campaign_report", labels={"owner": admin_id})
await self.crons.pause(schedule_id); await self.crons.resume(schedule_id)
```

**Reading a Timer as state.** `await self.crons.get("conversation_window")` returns the Schedule (or `None`) with `next_run_at`, so "how long until this Timer fires" is `next_run_at - now`. This replaces reading a key's TTL. It must be one Redis read, because Symphonai reads the conversation window on every outbound send.

**Bulk control by filter.** `cancel` and `list` accept filters (`action`, `key`, `key_prefix`, `labels`, scope), so "clear every Timer for this User" or "cancel every Timer of this Episode generation" is one call: `await self.crons.cancel(actions=["message_sync", "conversation_window", "agent_trigger"])` in the current scope, or `await self.crons.cancel(labels={"episode": eid, "generation": gen})`.

`schedule` accepts exactly one trigger (`after`, `at`, `cron`, `every`) and returns the Schedule. `scope=` overrides the default scope (`None` for system, or `(inbox_ref, user_id)`). Outside a handler (an admin HTTP route, a script), the same API comes from `Crons.from_app(app)`.

The handler side is one hook for every kind:

```python
async def process_cron_event(self, event: CronEvent) -> None:
    match event.action:
        case "buffer_flush": ...
        case "nudge": ...
        case "campaign_report":
            report = await build_report(self.db)              # Host logic
            for phone in event.payload["notify"]:             # coworkers: same Inbox, other Users
                await self.whatsapp.templates.send_text_template(phone, "daily_report", ...)
        case "ticket": ...
```

`CronEvent` carries `schedule_id`, `run_id`, `action`, `key`, `kind`, `inbox_ref`, `user_id`, `payload`, `labels`, `parent_id`, `scheduled_for`, `fired_at`, `attempt` and `run_count`. `run_id` (schedule ID plus the scheduled time) is the idempotency key the handler uses to make side effects safe under at-least-once delivery.

## Firing and backends

### One firing seam

Every backend fires through one internal entry point, also public for external schedulers: `Crons.from_app(app).fire(...)` with an action, scope and payload (an ad-hoc Run), or `fire(schedule_id, scheduled_for)` for a stored Schedule. It builds the context, clones the handler, dispatches to `process_cron_event`, records the outcome and returns it without raising for handler failures, so the caller applies its own retry policy.

### Default backend: Redis sorted set with claims

- Due index: a sorted set per cache namespace scope (score = next run time); the Schedule record in a hash; keys built only by `KeyFactory` with `InboxRef.cache_namespace`.
- A poller on every worker claims due Runs atomically (a Lua script moves the member to a claimed set with a lease and expiry), so exactly one worker fires each Run; lease renewal covers long Runs; an expired lease returns the Run to the due index (crash recovery).
- Survives restarts and deploys: a Run that came due while nothing was running fires late according to its `misfire` policy instead of being lost.
- **Wake on the earliest Run, not a fixed poll.** Each poller sleeps until the earliest score in the due index, and a `schedule` or `reschedule` that becomes the new earliest publishes a wake-up, so a 3-second debounce fires about 3 seconds later, not up to a poll interval later. Symphonai's agent trigger sits in front of every AI reply, so added latency there is user-visible. A fallback poll (proposed 5 seconds) covers a lost wake-up.
- Write cost: `schedule` and `reschedule` are one Lua call (hash write plus sorted-set update), the same order of cost as today's `SET ... EX`. Symphonai reschedules up to three Timers per inbound message (window, sync, agent trigger).
- `concurrency_key` is a lease per key: a Run whose key is held is deferred, not dropped.
- Delivery is at least once with a single claimant; `run_id` makes repeats detectable.
- Drain: on shutdown a poller stops claiming, lets in-flight Runs finish within the drain timeout and releases unfinished leases so another worker picks them up, through the same background-work tracking expiry handlers use today.

### Other backends

- **Memory and JSON** (Hosts without Redis): an in-process scheduler with the same API and semantics on one process; the JSON backend persists Schedules to the server folder so they survive restarts on one host. Startup logs say Redis is recommended for multi-worker and multi-host.
- **External schedulers** (Symphonai's Scheduler on APScheduler, Celery beat, cloud schedulers): the Host keeps its scheduler for recurrence and calls `fire(...)` from the job body; Wappa supplies context and dispatch only, and exactly-once is the external scheduler's job. Job arguments must be serializable (`InboxRef.cache_namespace`, User ID, payload), never Wappa objects.
- **Static registration:** `CronPlugin.add_cron(...)` stays as declarative sugar that upserts recurring Schedules at startup (idempotent by `action` and `key`), so build-time crons and runtime Schedules share one store and one firing path. fastapi-crons is no longer needed as the engine; whether it stays for its `/crons` monitoring router is an open question.

## What happens to expiry triggers

They are deleted in a clean cut (CHANGELOG plus migration guide), and their one essential property, a trigger scoped to an Inbox and a User, becomes the Timer kind's default scope. `@expiry_registry.on_expire_action`, `ExpiryPlugin`, `EXPTRIGGER` keys, the keyspace listener, `AppContext`, `create_expiry_messenger`, `create_expiry_cache_factory` and `parse_inbox_ref_from_expired_key` are replaced by `self.crons.schedule/reschedule/cancel/get` plus `process_cron_event`.

The mechanical mapping is the same for every trigger:

| Expiry triggers today | Crons domain |
| --- | --- |
| `expiry_cache.set(action, identifier, ttl_seconds=n)` (create or renew) | `self.crons.reschedule(action, key=..., after=timedelta(seconds=n))` (upsert by scope, action and key) |
| `expiry_cache.delete(action, identifier)` | `self.crons.cancel(action, key=...)` |
| `expiry_cache.get_ttl(action, identifier)` | `(await self.crons.get(action, key=...)).next_run_at - now` |
| `{inbox}` prefix of the key | the Schedule's `inbox_ref` scope |
| the identifier suffix, when it is a User | the Schedule's `user_id` scope (no `key` needed) |
| the identifier suffix, when it is not a User (a wamid) | `key=wamid`, Inbox scope |
| identity or data encoded in the action name or the identifier | `key`, `labels` and `payload` |
| `@expiry_registry.on_expire_action("x")` free function | `case "x":` in `process_cron_event` |
| key expiry is the event, and a wake-up rejected by a lease is spent | a Run stays claimed until it finishes; a Run held by a `concurrency_key` is deferred, not dropped |

### Symphonai's triggers, one by one

This inventory comes from a read of `symphonai/engine/expiry/`, `domains/user_runtime_cache/services/user_cache_service/_expiry.py`, `domains/engagement/`, `domains/human_takeover/services/` and `master_event/_status.py` on 2026-11-06. Symphonai is not changed by this PRD; it migrates at or after Gate C.

| Trigger | Scope today | Armed and cancelled by | Handler does | Crons domain |
| --- | --- | --- | --- | --- |
| `message_sync` | Inbox and User | renewed on every inbound message with TTL = sync TTL + agent-trigger delay + buffer; stops extending once the oldest unsynced message is older than `MESSAGE_SYNC_MAX_DEFER` (it reads the remaining TTL to decide); cleared with the cache | flushes cached messages to Postgres; Self-Heals when the Conversation is gone | Timer, `reschedule("message_sync", after=ttl, max_delay=MESSAGE_SYNC_MAX_DEFER)`; the debounce ceiling replaces the TTL read |
| `conversation_window` | Inbox and User | renewed on every inbound message (24 hours); read on every outbound send by the window-guard middleware and by the HTTP TTL projection | closes the Conversation (`reason="window_expired"`) | Timer, `reschedule("conversation_window", after=24h)`; the middleware and the projection read `get(...).next_run_at` |
| `agent_trigger` | Inbox and User | armed by the inbound Score with an adaptive delay (per message kind), inside the user-cache mutation lock; re-armed by the finished run when an Unbatched Message waits; also armed as `app_episode_run_*` for proactive nudge turns | runs the Agency under the Agency Run Lease (single flight per Conversation, fails closed), then re-arms | Timer, `reschedule("agent_trigger", after=delay)`, with `concurrency_key=f"agency:{inbox}:{user}"` as an option; the proactive variant becomes the same action with `payload={"nudge": ...}` instead of a generated action name |
| `human_takeover` | Inbox and User | set on activate (both the operator path and the Template path), cancelled on deactivate; TTL read by the FE countdown endpoint | publishes `HumanTakeoverChangedEvent(active=False)` and runs takeover hooks | Timer, `schedule("human_takeover", after=expires_in)`, `cancel` on deactivate, `get` for the countdown |
| `tpl_rollback` | Inbox, keyed on a wamid | set when a Template send fails (30 seconds), cancelled on `sent`/`delivered`/`read`, re-set by hand when cache cleanup fails; raises on purpose so failures are visible | rolls back the failed Template send record and its cache | Timer in Inbox scope, `schedule("tpl_rollback", key=wamid, after=30s, retries=...)`, `cancel(key=wamid)`; the retry policy replaces the hand-made re-arm; the handler reaches the User with `self.scope(user_id=record.user_id)` |
| Idle Nudge Ladder rungs (`app_*` per rung) | Inbox and User | `NudgeLadderService.arm` sets one key per rung with a TTL computed from quiet hours and the Owner's time zone, deletes dropped rungs; deadlines mirrored in `nudge_due_at` in the user cache because the key carries no data | checks the Conversation is open and the precondition, then arms a proactive `agent_trigger` | one Timer per rung, `schedule("nudge_rung", key=rung.name, at=due_at, payload=...)`; the `nudge_due_at` mirror can go because `next_run_at` and the payload travel with the Schedule |
| Episode timers (`app_episode_[run_]<conversation>_<episode>_<generation>_<rung>`) | Inbox and User | armed per pending work item, cleared per generation by rebuilding every known action name | parses identity back out of the action name and runs the rung or the run stage | `schedule("episode_rung", key=f"{episode}:{rung}", at=due_at, labels={"episode": ..., "generation": ...}, payload=identity)`; clearing a generation is `cancel(labels={"episode": ..., "generation": ...})` |
| App `ExpiryExtensionHandler` (`app_` prefix enforced) | Inbox and User | app profile factories | app logic with a hand-built `LifecycleContext` | app actions in `process_cron_event`; the `app_` namespace rule stays a Symphonai convention on the action name |
| `clear_expiry_triggers(user)` | Inbox and User | explicit cache deletion | deletes the three system triggers | `cancel(actions=["message_sync", "conversation_window", "agent_trigger"])` in the User's scope |

### What Symphonai deletes, keeps and gains

- **Deletes:** `handler_shell.py` (inbox recovery from the key, the `try/except` shell and `resolve_expiry_user_id`, because Run dispatch canonicalizes the User through the Host's `IIdentityResolver`), `system_handlers.py` aliases and `registry_utils.py`, the expiry context helpers, the manual `MessengerPipeline(...)` wrap and SSE identity bootstrapping (Run dispatch opens the same SSE scope and middleware as a webhook), `parse_inbox_from_expired_key`, the `EpisodeExpiry` action-name encoding, and the `nudge_due_at` mirror.
- **Keeps (business rules):** Self-Heal on a deleted Conversation (ADR-0014), the session-per-unit-of-work rule (ADR-0015), Runtime Owner admission at the top of `process_cron_event`, the adaptive delay calculation, Unbatched Message detection with `batched_message_ids`, the no-progress fuses, quiet hours, and the Agency Run Lease until `concurrency_key` is proven to give the same fail-closed guarantee.
- **Gains:** no duplicate firing across workers, no lost triggers across deploys, payloads on timers, and fewer moving parts in the re-arm path. The re-arm still exists, because a run that ends with an Unbatched Message waiting must schedule the next wake, but the failure that made it subtle goes away: a wake that meets a busy Conversation is deferred, not spent.

### Cutover for timers already armed

Expiry keys armed when the new version deploys would never fire, because the keyspace listener is gone. The cutover runs once, before the old listener stops: scan `*:EXPTRIGGER:*`, read each key's `PTTL`, schedule the matching Timer with `after=PTTL` (Inbox from the key prefix, User or key from the suffix, Episode identity from `EpisodeExpiry.from_action`), then delete the old key. Whether Wappa ships this as a migration helper (it knows the old key format) or the migration guide documents it as a Host script is an open question; for Symphonai the gap is up to 24 hours of conversation windows, so skipping the cutover would leave Conversations open past their window and is not acceptable.

### Symphonai's Scheduler

Symphonai's own Scheduler (APScheduler, persisted, one Scheduler Owner, acceptance and readiness, drain, `single_flight`, `coalesce`) already gives runtime, persistent schedules for reminders, sweeps and campaign ticks. It does not need replacing to adopt the Crons domain: its job bodies call `Crons.from_app(app).fire(action, scope=..., payload=...)` so they get Wappa's context instead of building a Template-send adapter and an SSE scope by hand. The likely split is that expiry-style Timers (seconds to hours, per User, high write rate) move to Wappa's Timers, and business schedules with domain history (reminders, campaigns) stay on Symphonai's Scheduler and fire through the seam. Folding the Scheduler into the Crons domain later is possible but not a goal.

## Boundaries (what stays the Host's)

Who may create, see or cancel a Schedule (admin authorization), what an action means, who the owner of a Schedule is, which Users a report reaches, how tickets are assigned and how agents work, campaign logic and business retries all stay in the Host. Wappa stores `labels` and `payload` opaquely: it indexes labels so the Host can find Schedules again, never reads either, and adds no domain concepts (no owners, tickets, campaigns, agents or reports) to the Crons domain.

## Phased rollout

1. **Firing seam and context:** `Crons.from_app(app).fire(...)`, the dispatch-context build for every scope, `self.scope(...)`, the Inbox-without-User Messenger fix, `CronPlugin` refactored onto the seam. External schedulers can drive `process_cron_event` from here on.
2. **Schedules and the Redis backend:** the Schedule model, the five kinds, `self.crons` on the handler, the sorted-set backend with claims, leases, misfire, overlap, retries, concurrency keys, parent and child links, querying and control; memory and JSON backends.
3. **Expiry triggers removed:** clean cut, migration guide, and Symphonai's migration during Gate C.
4. **Optional:** authenticated admin HTTP routes (`GET/POST/DELETE /crons/schedules`, behind Host service auth, off by default) and a run-history store beyond the last outcome.

## Test plan

- Context for each scope: system, Inbox, Inbox and User; the Messenger is present without a User; Platform Messengers and middleware match webhook dispatch; `self.scope(...)` builds another User's and another Inbox's context.
- Each kind: timer fires once and `reschedule` debounces; one-time with retries; recurring with `until` and `max_runs`; non-expiring until cancelled; heartbeat with overlap `skip` and misfire `coalesce`.
- Single claimant: two pollers (two workers) on one fake Redis fire each Run once; a crashed claimant's lease expires and the Run fires again with the same `run_id`.
- Restart: a Run due while no poller runs fires late per `misfire`.
- Concurrency key: two Runs with one key never overlap; different keys run in parallel.
- Fan-out: a parent creates children; cancel cascades when asked.
- Disconnected Inbox: Run fails with no send; recurring Schedule pauses.
- External scheduler: a plain asyncio task calls `fire(...)` and the handler receives the same event and context.
- Backend contract suite over Redis (fake), memory and JSON.
- Debounce ceiling: repeated `reschedule` with `max_delay` fires no later than the ceiling.
- Timer as state: `get(...).next_run_at` after `reschedule`, and `None` after the Run or a cancel.
- Filter cancel: by action list in a User's scope and by labels; other Users' Timers untouched.
- Run dispatch canonicalizes the User through a fake `IIdentityResolver` and opens the SSE scope; middleware sees the send.
- Wake-on-earliest: a 2-second Timer scheduled behind a 1-hour one fires in about 2 seconds.
- Drain: a shutdown mid-Run releases the lease and another poller completes the Run with the same `run_id`.
- Cutover: armed `EXPTRIGGER` keys with TTLs become Timers with matching due times.

## Decisions so far (discussion log, 2026-11-06)

1. **Scheduling is a Wappa domain, not a plugin feature.** It started as "can `process_cron_event` accept runtime crons, as Symphonai does with APScheduler?" and grew into one domain because expiry triggers are the same thing (scheduled work for an Inbox and a User) with a worse runtime.
2. **Infrastructure, not opinions.** Wappa owns scheduling, storage, claims, context, concurrency and querying; meaning, authorization and recipients stay with the Host (user direction: "not heavily opinionated").
3. **Five kinds, one entity.** Timers, one-time tasks, recurring expiring, recurring non-expiring and heartbeats are one Schedule with different triggers and ends (the user's list of kinds).
4. **Inbox and User scope is the default context, not a limit.** It keeps the expiry triggers' "this process sends something to this User through this Inbox"; `self.scope(...)` reaches other Users and Inboxes for admin crons and coworker sends.
5. **Expiry triggers are deleted** and become Timers, with a migration map and a cutover for armed keys. The user asked whether they should stay outside the handler or join Crons for architecture and maintainability; they join.
6. **Prebuilt API.** `self.crons` is built by the runtime on every dispatch, following the prebuilt-Messengers rule; a Host never constructs it.
7. **`owner` is not a Wappa field.** The first draft had an opaque `owner`; the user asked whether the owner is the Host's concern. It is: Wappa only needs a way to find Schedules again, so the field became generic indexed `labels`, and who owns a Schedule is a label the Host chooses.
8. **External schedulers stay first-class.** Symphonai may keep its Scheduler and fire through the seam; Wappa does not force a backend on a Host that already has one.
9. **Requirements found in the Symphonai inventory:** a debounce ceiling (`max_delay`), a cheap `get` for reading a Timer as state, filter-based `cancel`, wake-on-earliest firing so short debounces add no latency, User canonicalization and the SSE scope on Run dispatch, drain on shutdown, and a cutover for armed keys.
10. **Sequencing.** Implemented after Instagram Gate C; Symphonai needs it.

## Open questions

- Names and homes: `self.crons` and `Crons.from_app(app)`, one hook `process_cron_event` for every kind (proposed) or a separate `process_timer_event`?
- Should `fire` also accept a ready-made `CronEvent` for schedulers that already build one?
- Should the event carry an external scheduler's job ID (`metadata.job_id`) for correlation?
- `self.scope(...)` for cross-User and cross-Inbox work: name, and whether it also offers the Crons API for the other scope.
- Cancel cascade from parent to children: default on or off?
- Default policies per kind (misfire grace, overlap, retries), the fallback poll interval and the payload size limit.
- `labels`: how many indexed labels per Schedule, and whether `list` by label is exact match only.
- `reschedule` semantics: does the `max_delay` window restart after the Timer fires (proposed yes), and does `reschedule` on a missing Timer create it (proposed yes, upsert)?
- Does `concurrency_key` give the fail-closed single flight Symphonai's Agency Run Lease needs, so the lease can go later?
- Run history: keep only the last outcome (proposed) or a bounded history per Schedule?
- Cutover for armed expiry keys: a Wappa migration helper, or a documented Host script?
- Store placement: a dedicated Redis pool for Schedules (the expiry pool, DB 3, is free once triggers go) or a namespace in an existing pool?
- Keep fastapi-crons for its `/crons` monitoring router, or replace it with the optional admin routes?
- Opt-in HTTP admin routes and their auth (Host service auth, a dedicated secret)?
- Does an APScheduler adapter belong in Wappa, or only as a documented recipe calling `fire(...)`?
- Recurrence semantics for `cron` + `tz` across DST changes.

## Exit criteria

- One Crons domain: every kind of scheduled work is a Schedule, every firing goes through one seam into `process_cron_event` with the same context as a webhook dispatch, Platform Messengers included; no second firing path and no expiry-trigger code remain.
- Hosts schedule, reschedule, cancel, pause, query and fan out at runtime through the prebuilt `self.crons`, scoped by default to the current Inbox and User.
- Each Run fires on exactly one worker, survives restarts per its misfire policy, and carries a stable `run_id`.
- Inbox-scoped work without a User can send; `self.scope(...)` reaches other Users and Inboxes without hand-built context.
- External schedulers drive the same handler through `fire(...)`.
- Every Symphonai trigger in the inventory has a working Timer equivalent in a test (debounce with a ceiling, the window read as state, a keyed wamid Timer with retries, per-rung Timers, cancelling an Episode generation by label), armed keys survive the cutover, and Symphonai's migration leaves no Wappa context building in Symphonai.
- ADR accepted; public contract, `wappa/core` architecture docs, CONTEXT.md (Schedule, Run, Crons domain terms), CHANGELOG, migration guide and the developer skills updated.
