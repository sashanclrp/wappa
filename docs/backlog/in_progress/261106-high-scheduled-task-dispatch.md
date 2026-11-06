---
status: in progress (Wappa implementation in the working tree, not yet committed; Symphonai adoption is a separate PRD)
urgency: high (blocks Gate C and the next breaking release)
last_reviewed: 2026-11-06
grill_session: docs/sasha/grilling-sessions/261106-scheduling-domain.md
---

# Scheduled-task dispatch with a prebuilt WappaEventHandler context

## Code reality (2026-11-06)

Every Wappa deliverable below is implemented: the lane, all three sources, `self.scope`, `rebind`, the examples, skills and docs. Offline tests and real Redis TTL tests pass, and the example ran against a real `apscheduler==4.0.0a6` in a throwaway environment. Delete this file once the change is committed. The next dependency before Gate C is the separate Symphonai adoption PRD, which has not been written. Symphonai's handler shells, its `resolve_expiry_user_id` failure fallback and its APScheduler dispatcher are what it will replace.

## Origin

The [grilling session](../../sasha/grilling-sessions/261106-scheduling-domain.md#authoritative-scope-after-the-users-final-clarification) contains the source decisions and the three-agent code audit. Its latest scope correction overrides earlier proposals to build a durable scheduler, retained Run state or a general management API.

> What i need is a way to route all this through the WappaEventHandler and leverage it so I can already get everything ready to use in a single hook lane

> wappa objective is to enable them to use the hook lane on WappaEventHandler to get all the CONTEXT built already instead of violating DRY and CLEAN ARCHITECTURE PRICNIPLES!

> And this is an issue becasue when i want to create the hearbeat feature or allowing a user to scheduled a task reminer for example... I need to build for every feature (the 5 of them) the context every TIME! Instead here the idea is to leverage WappaEventHanlder as much as POSSIBLE!

## Context

A Host such as Symphonai reconstructs Wappa's Inbox/User context when Redis TTL triggers fire and when APScheduler jobs execute. The same reconstruction appears in message buffering, Agency triggers, Episodes, reminders and recurring work. Adding a heartbeat or another scheduled feature should reuse Wappa's runtime rather than require another path for credentials, Messengers, cache scoping, middleware and SSE identity.

The deliverable is one scheduled-work dispatch lane on `WappaEventHandler`. Every source invokes it through the same supported entry point. Wappa prepares a fresh scoped handler; the Host executes its business logic there.

Current code already supplies part of this foundation: `DispatchContextBuilder` builds the middleware-wrapped Messenger, cache factory and optional database factories; `with_context()` clones and binds a handler and builds the applicable Platform Messenger. User-scoped crons use that foundation, but Inbox-only crons omit the Messenger. Expiry handlers run outside the handler lane and can construct capabilities through helpers. Expiry dispatch already opens SSE scope and tracks background work; this PRD reuses those responsibilities instead of claiming they are absent.

There are two trigger sources to connect first: Wappa's existing Redis TTL mechanism and Host-owned schedulers. Redis expiry remains Redis-only and keeps its current delivery behavior. APScheduler, Celery or custom Host code supplies scheduling, persistence and execution policy as appropriate. Wappa does not implement their engines or mirror their jobs.

## Outcome and scope

### R1. One public scheduled-work lane

Use the agreed `process_scheduled_event(event: ScheduledEvent)` hook, with `handle_scheduled_event()` providing framework logging and lifecycle behavior. The naming follows the existing `process_*_event` pattern; the user's `process_scheduled_tasks or something` describes this same single lane. The public home is `wappa.scheduling`, with `Scheduling` as the supported dispatch entry point and `SchedulingPlugin` for lifecycle composition.

Every invocation gets a fresh handler clone. Redis expiry, existing declarative cron callbacks and external scheduler callbacks all reach that hook. An engine or feature must not implement its own Messenger/cache/DB/SSE assembly to use the lane.

### R2. Build capabilities once per invocation

| Explicit scope | Wappa prepares |
| --- | --- |
| Inbox and User | Qualified Inbox, canonical User, pipeline-wrapped Messenger, applicable Platform Messenger, scoped cache factory/User cache access, optional `db` and `db_read`, SSE identity and existing lifecycle tracking |
| Inbox only | Qualified Inbox, pipeline-wrapped Messenger and Platform Messenger, optional database factories; no invented User or User cache |
| System | Optional database factories and handler infrastructure; no invented Inbox, Messenger or User cache |

`user_id` requires an `InboxRef`. Credentials resolve through the existing Inbox runtime. Invalid or unavailable required context fails explicitly before Host processing; do not silently dispatch a scoped task with missing required capabilities. Optional database access stays optional, as in the current public contract.

Wappa prepares its cache infrastructure and scoped cache access. Symphonai's typed `UserCacheSchema`, domain cache services, Conversation state and Agent dependencies remain Host concepts. A Host can initialize its typed dependencies once in its scheduled hook or a shared Host wrapper, then route by action. Wappa does not import or construct Symphonai domain models.

### R3. A small event and a public dispatch method

`ScheduledEvent` replaces the cron-specific input model. Its contract contains `action`, `source`, optional qualified `inbox_ref`, optional subject `user_id`, optional opaque `identifier`, `payload`, optional `scheduled_for`, dispatch timestamp and optional external execution/correlation identity. Callers supply the subject identifier they know; dispatch applies the configured Host identity resolver and exposes the canonical User on the event and handler before building User-scoped caches. Timestamps crossing Wappa's interface are UTC. Cron expression, retry attempt or engine-specific identifiers may be supplied as opaque metadata; they are not required for Redis expiry or a custom caller.

`Scheduling.from_app(app).dispatch(event)` awaits shared context construction and handler execution. It accepts ordinary typed values and does not require a fabricated HTTP request. It returns on success and propagates context/handler failures to the caller, allowing the selected engine to apply its existing policy. Do not turn an exception into a successful scheduler callback. Use existing typed infrastructure errors; no new outcome taxonomy is required.

An external caller may carry its existing occurrence ID for correlation. Wappa neither requires every engine to share a Run model nor persists a second schedule, occurrence, attempt or history record. Redis expiry has no durable Run-ID contract.

### R4. Keep native Redis TTL operation

Keep the existing expiry pool, default logical Redis DB 3, the fourth database when counted from one. DB 4 is currently AI state. Explicit configured URLs remain authoritative. Do not create another Redis database/pool or rename deployed pool configuration solely for this feature.

Continue using `SETEX`/TTL keys, existing KeyFactory namespaces and Redis keyspace notifications. Keep the listener's notification setup, reconnect behavior and existing background-work tracking. Keys disappear on expiration as today. Do not add sorted-set due indexes, claim records, replay, retry persistence, shadow payload keys, leases or terminal retention.

Keep the native trigger-control behavior: set/create/renew, delete/cancel, existence and remaining-TTL reads. It works only with Redis; memory and JSON do not acquire timer engines. Preserve native TTL semantics instead of imposing the proposed create-conflict, pause/resume, queue, catch-up or recovery state machine.

Adapt an expired notification into `ScheduledEvent` and call the shared dispatch path. Native events carry the parsed Inbox, action and opaque identifier. A Host subject binding supplies whether that action's identifier is a User, or returns no User for Inbox-only work. It maps business identity only, never builds capabilities. Preserve namespaced action parsing; an unknown/invalid binding is observable and does not fabricate a User. A message ID such as `wamid` must not be treated as a User by shape.

No dynamic payload survives in an expired value. Native TTL callbacks use their identifier and Host state, as today; externally supplied payloads travel directly through the dispatch method. Do not introduce payload persistence to compensate for TTL deletion.

### R5. Connect any Host-owned scheduler

APScheduler, Celery or custom asynchronous Host code can call the public dispatch method with action, source, explicit scope and its own payload/metadata. This is the integration mechanism. Ship a tested APScheduler-shaped example based on the reference Host and a generic callback example; do not add a mandatory APScheduler/Celery dependency or a managed scheduling service to Wappa.

The Host configures its scheduler, database, tables/migrations, job registration, readiness, deployment ownership, recurrence, execution limits, retries, cancellation, single-flight and history. Existing built-in static cron support can retain its current engine while its callback and public naming are refactored onto the shared lane. It must not keep a second context-building or error-swallowing path.

All five requested behaviors use the same handler lane:

| Behavior | Trigger owner | What Wappa does |
| --- | --- | --- |
| Timer/debounce | Existing Wappa Redis TTL infrastructure | Expiry notification to prebuilt scoped handler |
| One-time task/reminder | Selected Host scheduler | Callback to the same handler |
| Recurring task with an end | Selected Host scheduler | Callback to the same handler; Host enforces end |
| Recurring task without an end | Selected Host scheduler | Callback to the same handler |
| Heartbeat | Selected Host scheduler or Host loop | Callback to the same handler; Host owns cadence/overlap |

### R6. Scope and identity mechanisms

The external entry point accepts explicit Inbox/User identity. Reuse the configured Host identity resolver before building User-scoped caches, with the correct Inbox. Do not infer identity from a Platform identifier's shape. A Host supplies the authoritative association between a task and its subject.

Keep a supported context accessor, `self.scope(...)`, backed by the same builder, for a task that discovers another User/Inbox while processing. It provides a lifecycle-scoped handler/capability bundle with isolated SSE identity, not another credential path. Sending within the same Inbox still uses the current Inbox-bound Messenger and an explicit target.

Host identity-change workflows can rebind Wappa-owned native expiry keys using existing key operations or a small helper over those operations. Preserve remaining TTL and reject overwriting an unrelated destination key; do not add an alias registry or rewrite external scheduler records. The Host owns authoritative old/new identities and its wider business-key migration.

### R7. Clean public-contract replacement and Host enablement

Rename the cron-specific hook/event/dispatcher surface to the scheduled-event contract. Replace the free-function expiry business callback path with the scheduled handler lane. Remove obsolete public aliases/context-construction helpers once Wappa's own callers use the new path. Retain Redis TTL internals that remain necessary. Every removed public import or helper is listed in the release notes, including any non-expiry use by Hosts; do not claim Host code was migrated by this Wappa PRD.

No compatibility aliases, dual callback runtime, armed-key importer or maintenance cutover tooling. No transfer/replay promise for already armed old-version keys. The release documentation describes fresh Host integration and setup without implementing it inside Symphonai.

Update public contract, relevant context/architecture docs, applicable ADRs, CHANGELOG, packaged developer skills, scaffolds and examples. Document how to initialize Host-specific dependencies once in the hook and reuse them across actions. Symphonai implementation/adoption is a separate PRD; Wappa delivery and that adoption precede Gate C.

## Out of scope

- A Wappa scheduler service, durable scheduling engine or general backend-management abstraction.
- New PostgreSQL tables, SQL schemas, columns or migrations; another Redis database/pool; execution-history storage.
- Native Redis claims, leases, fencing, retries, replay, due indexes, pollers, persistent Run/attempt models or new delivery guarantees.
- Timer engines for memory/JSON, or implementing all five behaviors independently in every cache backend.
- `/scheduling` administration routes, a dashboard, new authorization policy, static-definition revision stores or a job control plane.
- Cross-scheduler schedule management, parent/child workflow trees, cascading cancellation, generic queue/catch-up engines or another identity registry.
- Symphonai code changes, business Episode logic, typed domain models, takeover state, Agent orchestration or provider reconciliation.
- Replacing Host-owned Agency leases, send fences, runtime admission or scheduler supervision.

## Implementation notes

### One context path

Use `DispatchContextBuilder` for credentials/capabilities and `with_context()` for binding. Consolidate the scheduled dispatch orchestration rather than adding a parallel factory. Open/restore SSE scope around actual handler execution and use the existing BackgroundWorkTracker for Wappa-owned background callbacks. Await external dispatch so exceptions reach the scheduler. Drain through the current runtime lifecycle, without introducing scheduler ownership leases.

Construct only the capabilities appropriate to the declared scope. In particular, remove the current `include_messenger=user_id is not None` coupling for Inbox-only work. Required context failures must remain distinguishable from optional capabilities not configured by the Host.

### Source adapters stay small

The Redis adapter parses the existing notification and obtains subject identity through the configured Host binding. The static cron adapter translates its existing registration into `ScheduledEvent`. External examples show a normal async callback calling `Scheduling.from_app(app).dispatch(...)` with serializable job arguments and the app obtained through the Host's lifecycle. Adapters own source translation; shared dispatch owns all Wappa capability construction.

The event model has one canonical home and public export. Do not create native Schedule/Run persistence models because the event contains an optional external job ID. Do not add an adapter interface that promises recurrence or job-management operations merely to invoke this callback.

### Concrete reference scenarios

Use fake Host handlers and real Wappa entry points to demonstrate: User-scoped agent-trigger expiry; message-sync expiry; conversation-window expiry and native TTL read; Inbox-scoped rollback keyed by a message ID; an external one-time reminder; recurring report; expiring recurring report; heartbeat; and an Episode-style task carrying Host identifiers. The tests assert Wappa context and dispatch, not Symphonai business rules.

The Host subject mapper supplies User identity for User-action identifiers and leaves message-keyed actions Inbox-only. Host scope failures must be observable. The existing Redis notification behavior, including multiple subscribers and missed notifications while disconnected, remains unchanged; stronger coordination is a selected engine/Host concern.

## Requires

The `service` category below means in-process Python modules, not new deployed services. Documentation, fixtures and integration examples are included in each owning row. Zero new deployed services, database objects, environment variables, runtime settings or HTTP endpoints are required.

| Category | Item | Before | After | Requires |
| --- | --- | --- | --- | --- |
| term | Scheduling vocabulary | Cron-specific wording for general background work | Scheduled Event and common handler lane | Glossary/context map and Host skill updates |
| service | Scheduled dispatch | Private cron firing plus separate expiry capability assembly | Public async dispatch in wappa.scheduling through Scheduling.dispatch using the existing shared context builder | Existing identity resolver, three scope cases, SSE/background lifecycle, public exports, Wappa call sites, context/architecture/ADR updates, context tests and public contract |
| service | SchedulingPlugin composition | Existing cron/expiry lifecycle plugins | Compose the shared scheduled-event lane and its existing trigger sources | Configure/startup/shutdown wiring, reuse current infrastructure, plugin docs and lifecycle tests; no new deployed service |
| variant | ScheduledEvent input | CronEvent requires cron-specific fields | One replacement event suitable for every source, with optional engine metadata | Validation, canonical public export, import/scaffold/skill updates; no SQL schema |
| service | Scheduled handler lane | Cron hook plus free-function expiry callbacks | handle_scheduled_event/process_scheduled_event | Handler clone isolation, logging, pre/post behavior, removed-import break list, CHANGELOG/release notes, current Wappa call sites and packaged developer skill/scaffold updates |
| service | Redis expiry adapter and subject binding | Free-function business dispatch | Existing TTL notification translated to the shared hook | Namespaced key parsing, Host identity binding, no capability assembly in Host adapter, tests |
| cache | Existing Redis TTL keys | expiry pool, SETEX keys and native TTL reads | Same infrastructure, context-bound callback and TTL-preserving identity rebind mechanism | Existing operations, collision behavior, real Redis TTL integration checks; no extra key family or archive |
| service | Static cron adapter | Private callback with duplicate orchestration and swallowed failures | Existing engine callback routes through shared dispatch | Registration behavior, error propagation and clean contract rename |
| service | Scoped context accessor | Hosts reconstruct context to access another subject | self.scope using shared-builder-backed scoped capabilities | Scope/SSE isolation, credentials reuse and tests |
| dependency | Host scheduler integrations | Host APScheduler runtime and custom job bodies | Tested integration recipe using the public dispatch method | APScheduler-shaped fake/example, generic/external callback source, Host integration guidance and packaged examples; no new runtime dependency |
| endpoint | Scheduling administration | Previously proposed router | Removed from deliverable | Host routes call the dispatch mechanism if needed |
| service | Durable scheduler/history/workflow machinery | Previously proposed new engine | Removed from deliverable | No implementation |

## Complexity Budget

This budget records the user's explicit scope correction and final responsibility approval on 2026-11-06. No new database object or deployed service is authorized.

| Category | Item | Decision | Reason | Approval |
| --- | --- | --- | --- | --- |
| term | Scheduling vocabulary | keep | User approved complete scheduling-contract naming | |
| service | Scheduled dispatch | keep | The user's stated problem is repeated Wappa context construction | |
| service | SchedulingPlugin composition | simplified | Recompose existing plugin lifecycle/source wiring; no scheduler service or new infrastructure | |
| variant | ScheduledEvent input | simplified | One event replaces cron-specific input; optional engine metadata, no durable Run model | |
| service | Scheduled handler lane | keep | All five use cases need the same ready context | |
| service | Redis expiry adapter and subject binding | simplified | Preserve TTL delivery; change handler routing and supply subject facts | |
| cache | Existing Redis TTL keys | keep | User explicitly requires Redis-only expiry to continue as it works today | |
| service | Static cron adapter | simplified | Reuse its existing engine and the common dispatcher; no new scheduler | |
| service | Scoped context accessor | keep | User approved shared scoped access instead of manual capability construction | |
| dependency | Host scheduler integrations | simplified | Integration examples/callback mechanism; Host owns installed engine and datastore | |
| endpoint | Scheduling administration | cut | User approved Host-owned routes in the simplification review | |
| service | Durable scheduler/history/workflow machinery | cut | User explicitly rejected speculative native recovery, history and scheduling-engine expansion | |

The PRD's Complexity Budget is a hard limit. If your change needs a table, column, schema, migration, setting, endpoint, permission, service, env var or variant that the budget does not list as kept, stop and ask; do not build it.

## Exit criteria

- [x] Redis expiry, existing static crons and an external async scheduler callback invoke the same scheduled handler wrapper and Host hook.
- [x] Every supported scope receives a fresh isolated handler with the appropriate capabilities. Inbox-only work has its Messenger; User work has correctly scoped cache access; system work invents neither identity nor messaging capabilities.
- [x] A handler can use its scoped Messenger/Platform Messenger, cache factory and optional database factories without Host-side Wappa capability construction.
- [x] Every one of the five behaviors is demonstrated through the common lane, using a suitable trigger source rather than five native engines.
- [x] Native expiry remains Redis-only with the current pool, key TTL/control operations, notification setup and disappearance-on-expiry behavior. No native recovery/claim/history state or payload shadow keys are introduced.
- [x] User identifiers are explicit or supplied through Host subject binding/resolution; message identifiers do not create User contexts. Identity rebind preserves native TTL and handles destination collisions without a new registry.
- [x] Handler/context exceptions reach awaiting external/static callbacks. Redis background errors remain observable through existing tracking/logging. SSE identity is opened/restored correctly and concurrent User/Inbox dispatches remain isolated.
- [x] Scoped access to another subject uses the same context builder and restores the parent SSE scope afterwards.
- [x] Existing lifecycle/drain behavior is retained and tested; there are no new distributed coordination guarantees.
- [x] Old public cron/expiry business callback entry points and aliases are removed as documented. Current Wappa call sites, exports, examples/scaffolds and packaged skills use the replacement contract.
- [x] CHANGELOG and integration guidance cover APScheduler-shaped dispatch, generic/custom scheduler dispatch, all representative Redis actions, Host identity mapping, typed Host dependency initialization and all removed imports.
- [x] Applicable offline tests, real Redis TTL integration checks and repository implementation gates pass.
- [x] No Symphonai code change is required for this Wappa PRD's completion. Its separate adoption PRD is identified as the next dependency before Gate C.

## Open questions

None. The user confirmed the final Wappa-versus-Host responsibility table on 2026-11-06 and authorized promotion and commit. The [accepted design ADR](../../adr/0030-scheduled-work-dispatch.md) records the boundary. Earlier scheduler-engine policy questions are closed by Host ownership, not new Wappa defaults.

Implementation choices inside the approved budget do not reopen the design.
