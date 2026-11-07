# Scheduled work uses Wappa context; Hosts own scheduler engines

Accepted 2026-11-06, implemented in Wappa. The user approved the final responsibility table in the [grilling session](../sasha/grilling-sessions/261106-scheduling-domain.md#q26-final-question-wappa-versus-host-responsibilities). Shipped in 0.34.0.

## Context

Host expiry handlers, scheduled jobs, Episodes, reminders and heartbeats repeatedly assemble Wappa Messengers, cache scope and SSE identity. Existing cron dispatch is private and expiry business callbacks sit outside WappaEventHandler. Making that context reusable does not require Wappa to replace APScheduler, Celery or a Host's scheduler. An earlier proposal expanded into native durable scheduling, claims, replay and history; the user rejected those mechanisms because they did not solve the stated context-construction problem.

## Decision

Wappa exposes one scheduled-event dispatch entry point and `process_scheduled_event` on WappaEventHandler. Each invocation uses the shared DispatchContextBuilder to prepare a fresh handler with the appropriate qualified Inbox/User identity, Messenger/Platform Messenger, scoped cache access, optional DB factories, middleware and SSE/lifecycle scope. The Host supplies task subjects and canonical identity evidence, initializes typed domain dependencies in its common hook/wrapper, and routes feature actions there.

Redis TTL remains Wappa's existing Redis-only SETEX/keyspace-notification infrastructure and pool, with its current key disappearance and delivery behavior. Its adapter maps notifications and Host-provided subject facts into the shared handler lane. No native due indexes, replay, claims/leases, persistent Run/attempt state, shadow payload keys or history archive are introduced. Memory and JSON do not gain TTL engines.

Hosts and their selected engines own one-time/recurring/heartbeat scheduling, datastore/schema setup, job registration and lifecycle, retries, timeouts, overlap, recovery, idempotency, history, administration and business coordination. Wappa supplies the supported async callback mechanism and tested integration examples; awaited dispatch failures propagate to the caller. Existing built-in static cron callbacks also use the shared dispatcher rather than a separate capability-building path.

The public contract changes cleanly: scheduled-event names replace cron-specific hook/event names and free-function expiry business callbacks. Wappa updates its callers, public contract, CHANGELOG, skills, scaffolds and examples, without compatibility aliases, dual runtimes or armed-key transfer tools. Symphonai is a reference Host; actual adoption belongs to a separate Host PRD before Gate C.

## Consequences

All five task behaviors can reuse one ready-context handler without introducing five scheduler implementations. Wappa does not promise stronger Redis notification delivery or remove Host-owned Agency/send fences. Native timer data and identity remain explicit; arbitrary message identifiers never imply a User. There are no new deployed services, SQL objects, HTTP management routes or execution-history stores in this deliverable.

## Implementation choices

- `SchedulingPlugin` replaces `CronPlugin` and `ExpiryPlugin`, because both only ran trigger sources for the one lane. A Host scheduler needs no plugin.
- An expired key's identifier is never read as a User. Without an `ExpirySubjectBinding`, expiry is Inbox-only work, and SSE identity no longer classifies the identifier by shape (ADR-0022): a Host refines it with `update_identity`.
- Awaited dispatch runs as tracked work, so shutdown drains it and a draining runtime refuses it with `RuntimeError`. Resolver failures propagate instead of falling back to the armed identifier; a Host that prefers that fallback applies it inside its resolver.
- `self.scope(...)` clones the handler prototype, not the current clone, so Host state set for one subject cannot reach another. It is available on handlers bound by `DispatchContextBuilder`: scheduled and Platform webhook dispatch.
- `IExpiryCache.rebind` uses RENAMENX: atomic, TTL preserved, and a destination conflict raises `ExpiryKeyConflictError` with both keys unchanged.

- Inbox-bound `scope()` construction defers send credentials until the first Messenger operation (0.34.2). Credential outages must not prevent non-sending timer work from running. The scope exposes credential-free identity and discovery; a per-scope async lock retains one successfully resolved pipeline. Failure propagates with its original Directory type and is not retained. Focused capabilities resolve through that same pipeline, preserving once-per-send middleware. The MessengerFactory cache and eviction subscriptions remain the cross-scope authority; webhook/API admission is unchanged.
