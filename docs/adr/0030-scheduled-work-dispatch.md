# Scheduled work uses Wappa context; Hosts own scheduler engines

Accepted design, 2026-11-06. The user approved the final responsibility table in the [grilling session](../sasha/grilling-sessions/261106-scheduling-domain.md#q26-final-question-wappa-versus-host-responsibilities). This is planned work, not a claim that the interfaces have shipped; the [pending PRD](../backlog/pending/261106-high-scheduled-task-dispatch.md) owns implementation and exit criteria.

## Context

Host expiry handlers, scheduled jobs, Episodes, reminders and heartbeats repeatedly assemble Wappa Messengers, cache scope and SSE identity. Existing cron dispatch is private and expiry business callbacks sit outside WappaEventHandler. Making that context reusable does not require Wappa to replace APScheduler, Celery or a Host's scheduler. An earlier proposal expanded into native durable scheduling, claims, replay and history; the user rejected those mechanisms because they did not solve the stated context-construction problem.

## Decision

Wappa exposes one scheduled-event dispatch entry point and `process_scheduled_event` on WappaEventHandler. Each invocation uses the shared DispatchContextBuilder to prepare a fresh handler with the appropriate qualified Inbox/User identity, Messenger/Platform Messenger, scoped cache access, optional DB factories, middleware and SSE/lifecycle scope. The Host supplies task subjects and canonical identity evidence, initializes typed domain dependencies in its common hook/wrapper, and routes feature actions there.

Redis TTL remains Wappa's existing Redis-only SETEX/keyspace-notification infrastructure and pool, with its current key disappearance and delivery behavior. Its adapter maps notifications and Host-provided subject facts into the shared handler lane. No native due indexes, replay, claims/leases, persistent Run/attempt state, shadow payload keys or history archive are introduced. Memory and JSON do not gain TTL engines.

Hosts and their selected engines own one-time/recurring/heartbeat scheduling, datastore/schema setup, job registration and lifecycle, retries, timeouts, overlap, recovery, idempotency, history, administration and business coordination. Wappa supplies the supported async callback mechanism and tested integration examples; awaited dispatch failures propagate to the caller. Existing built-in static cron callbacks also use the shared dispatcher rather than a separate capability-building path.

The public contract changes cleanly: scheduled-event names replace cron-specific hook/event names and free-function expiry business callbacks. Wappa updates its callers, public contract, CHANGELOG, skills, scaffolds and examples, without compatibility aliases, dual runtimes or armed-key transfer tools. Symphonai is a reference Host; actual adoption belongs to a separate Host PRD before Gate C.

## Consequences

All five task behaviors can reuse one ready-context handler without introducing five scheduler implementations. Wappa does not promise stronger Redis notification delivery or remove Host-owned Agency/send fences. Native timer data and identity remain explicit; arbitrary message identifiers never imply a User. There are no new deployed services, SQL objects, HTTP management routes or execution-history stores in this deliverable.
