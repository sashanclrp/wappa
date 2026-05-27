# ADR-0004: Graceful Shutdown and Background Work Drain

**Status:** Accepted  
**Date:** 2026-05-27  
**Supersedes:** None  
**Extends:** ADR-0003 (HTTP Client Lifecycle Ownership)

## Context

Wappa v0.14.0 established that Wappa owns HTTP session validity (ADR-0003).
However, the shutdown hook priority scheme closed the HTTP session (priority 90, runs first) before background producers (expiry, cron, inbound dispatch) had a chance to drain. Fire-and-forget tasks created by `InboundRuntime`, `ExpiryDispatcher`, and `WebhookPlugin` were completely untracked — shutdown could cancel them mid-flight with no signal.

## Decision

### Shutdown dependency order

Shutdown hooks execute highest-priority-first. The new ordering:

1. **Priority 90** — Mark runtime as draining. Reject new background work and new messenger construction.
2. **Priority 85** — Stop cron scheduler with bounded drain (15s timeout).
3. **Priority 80** — Cancel expiry listener, clear AppContext.
4. **Priority 70** — Drain all remaining tracked background tasks (30s timeout).
5. **Priority ≤25** — Close infrastructure (database, SSE, Redis).
6. **Priority 10** — Close HTTP session and clean up app state.

### Tracked background work

`BackgroundWorkTracker` replaces all untracked `asyncio.create_task()` calls in framework code. It:
- Registers tasks and auto-removes them on completion.
- Rejects new work after `begin_drain()`.
- Provides `drain(timeout)` that waits then cancels stragglers.

### Unified session lifecycle

`SessionLifecycle` owns the HTTP session with three-state awareness:
- **Active** — session valid, `get_session()` returns it.
- **Recoverable** — session closed but runtime active, `recreate()` serialized via lock.
- **Draining** — runtime shutting down, all access raises `RuntimeDrainingError`.

All messenger construction paths consume `SessionLifecycle.get_session` as a session provider callable.

## Consequences

- In-flight background work completes (or times out) before resources close.
- Host applications no longer need to detect/repair Wappa's closed sessions.
- `app.state.http_session` remains set for backward compatibility.
- `engine.dispose(close=False)` remains correct — drain ensures no active operations at disposal time.
- Unauthenticated media download client remains separate per ADR-0003.
