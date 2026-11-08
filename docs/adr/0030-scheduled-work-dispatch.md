# Scheduled work uses Wappa context; Hosts own scheduler engines

Accepted 2026-11-06, implemented in Wappa. The user approved the final responsibility table in the [grilling session](../sasha/grilling-sessions/261106-scheduling-domain.md#q26-final-question-wappa-versus-host-responsibilities). Shipped in 0.34.0.

## Context

Host expiry handlers, scheduled jobs, Episodes, reminders and heartbeats repeatedly assemble Wappa Messengers, cache scope and SSE identity. Existing cron dispatch is private and expiry business callbacks sit outside WappaEventHandler. Making that context reusable does not require Wappa to replace APScheduler, Celery or a Host's scheduler. An earlier proposal expanded into native durable scheduling, claims, replay and history; the user rejected those mechanisms because they did not solve the stated context-construction problem.

## Decision

Wappa exposes one scheduled-event dispatch entry point and `process_scheduled_event` on WappaEventHandler. Each invocation uses the shared DispatchContextBuilder to prepare a fresh handler with the appropriate qualified Inbox/User identity, Messenger/Platform Messenger, scoped cache access, optional DB factories, middleware and SSE/lifecycle scope. The Host supplies task subjects and canonical identity evidence, initializes typed domain dependencies in its common hook/wrapper, and routes feature actions there.

Redis TTL remains a Redis-only source in the existing expiry pool. Since 0.34.6, an observed loss during a dev reload requires recovery of this native source: arm/renew atomically writes a durable pending due index with generation and Redis-clock due time. Startup and two-second ticks admit bounded overdue batches whose TTL keys are gone through the same scheduled lane; Pub/Sub is the prompt path. A short claim deadline permits at-least-once recovery after crash/failure; success removes only its own generation, preserving renewals. Cancel/rebind update TTL and pending data together. The due set/record hash retain pending occurrences, not payloads or execution history. This deliberately extends the earlier no-index decision for Redis expiry only. Memory/JSON do not gain timer engines, and Wappa does not become a general scheduler.

Hosts and their selected engines own one-time/recurring/heartbeat scheduling, datastore/schema setup, job registration and lifecycle, retry policies, timeouts, overlap, external-engine recovery, business idempotency, history, administration and business coordination. Wappa supplies the supported async callback mechanism and tested integration examples; awaited dispatch failures propagate to the caller. Existing built-in static cron callbacks also use the shared dispatcher rather than a separate capability-building path.

The public contract changes cleanly: scheduled-event names replace cron-specific hook/event names and free-function expiry business callbacks. Wappa updates its callers, public contract, CHANGELOG, skills, scaffolds and examples, without compatibility aliases or dual runtimes. Wappa owns the explicit live expiry-index migration tool; it preserves existing values and remaining TTLs rather than re-arming keys. Symphonai is a reference Host; actual adoption belongs to a separate Host PRD before Gate C.

## Consequences

All five task behaviors can reuse one ready-context handler without introducing five scheduler implementations. Indexed Redis expiry now promises at-least-once recovery while Redis retains its data; it does not remove Host-owned idempotency/send fences. Pre-upgrade keys have no index entry; the explicit dry-run-by-default expiry-index migration indexes still-live qualified keys without changing their timer. Already vanished unindexed keys cannot be reconstructed. Native timer data and identity remain explicit; arbitrary message identifiers never imply a User. There are no new deployed services, SQL objects, HTTP management routes or execution-history stores in this deliverable.

## Implementation choices

- `SchedulingPlugin` replaces `CronPlugin` and `ExpiryPlugin`, because both only ran trigger sources for the one lane. A Host scheduler needs no plugin.
- An expired key's identifier is never read as a User. Without an `ExpirySubjectBinding`, expiry is Inbox-only work, and SSE identity no longer classifies the identifier by shape (ADR-0022): a Host refines it with `update_identity`.
- Awaited dispatch runs as tracked work, so shutdown drains it and a draining runtime refuses it with `RuntimeError`. Resolver failures propagate instead of falling back to the armed identifier; a Host that prefers that fallback applies it inside its resolver.
- `self.scope(...)` clones the handler prototype, not the current clone, so Host state set for one subject cannot reach another. It is available on handlers bound by `DispatchContextBuilder`: scheduled and Platform webhook dispatch.
- `IExpiryCache.rebind` uses an atomic Lua transition: TTL, generation and due time preserved; a live or pending destination raises ExpiryKeyConflictError without changing either occurrence. The expiry source starts at priority 95 after ordinary dependency hooks so startup recovery does not capture incomplete capabilities.

- Inbox-bound `scope()` construction defers send credentials until the first Messenger operation (0.34.2). Credential outages must not prevent non-sending timer work from running. The scope exposes credential-free identity and discovery; a per-scope async lock retains one successfully resolved pipeline. Failure propagates with its original Directory type and is not retained. Focused capabilities resolve through that same pipeline, preserving once-per-send middleware. The MessengerFactory cache and eviction subscriptions remain the cross-scope authority; webhook/API admission is unchanged.

- Since 0.34.7, generic Wappa cache delete/expire/rename operations preserve the reserved due/record index keys. Intended timer cancellation still goes through the expiry adapter's atomic operations; Wappa never changes server persistence or eviction policy.
