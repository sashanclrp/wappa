# Runtime lifecycle: HTTP client ownership and graceful drain

Accepted, 2026-11-06. Consolidates the HTTP client lifecycle decision (2026-05-26, amended 2026-08-03) and the graceful shutdown decision (2026-05-27). This ADR states the whole current decision; the earlier ADRs it absorbed were deleted.

## Context

Wappa creates lifespan-scoped HTTP clients at startup. Earlier, a raw client published through application state let consumers and cached Messengers outlive their ownership boundary, and Hosts detected closed sessions and rebound Wappa's internal transport themselves. Wappa also uses clients with different credential boundaries: one global client would send the Meta bearer token to arbitrary media URLs. Shutdown closed the HTTP session before background producers had drained, and fire-and-forget tasks were untracked.

## Decision

1. **`SessionLifecycle` is the only owner of Wappa HTTP clients.** Consumers receive provider callables (`get_session`, `get_media_download_client`), never raw client aliases on application state. It has three states: active (`get_session()` returns the client), recoverable (closed but the runtime is active; `recreate()` is serialized by a lock) and draining (every access raises `RuntimeDrainingError`).
2. **Messengers acquire the client on every build.** `MessengerFactory` asks the lifecycle for the authenticated client on every `create_messenger` call, and a cached Messenger with a stale session is evicted on access. `WappaCorePlugin.recreate_http_session()` is the supported recovery hook. Hosts never detect or repair Wappa's sessions; on `HTTPSessionClosedError` they call the hook or let the message fail.
3. **Each credential boundary gets its own client.**

| Traffic | Owner |
| --- | --- |
| Authenticated Meta API (sends, Template management) | `SessionLifecycle.get_session` (created at startup, pooled) |
| Downloads from arbitrary media URLs | `SessionLifecycle.get_media_download_client` (lazy, no bearer) |
| Host services (databases, external APIs) | the Host |
| Batch uploads (e.g. header media refresh) | a batch-scoped Host adapter |

4. **Shutdown drains before it closes.** Hooks run highest priority first: 90 marks the runtime draining (no new background work or Messenger construction); 85 stops the cron scheduler (15 s bounded drain); 80 cancels the expiry listener and clears AppContext; 70 drains every remaining tracked task (30 s, then cancels stragglers); 25 and below close database, SSE and Redis; 10 closes the HTTP session and cleans up app state.
5. **Framework background work is tracked.** `BackgroundWorkTracker` replaces untracked `asyncio.create_task()` in framework code: it registers tasks, removes them on completion, rejects new work after `begin_drain()` and offers `drain(timeout)`.
6. **`engine.dispose(close=False)`** is the database shutdown: waiting for remote TCP graceful closes has no useful outcome, and the drain guarantees no active operations.

## Consequences

- In-flight background work completes or times out before resources close; work submitted after shutdown begins fails loudly.
- `HTTPSessionClosedError` and `RuntimeDrainingError` are errors callers may meet after shutdown begins; silent failure would be worse.
- `app.state.session_lifecycle` exposes the lifecycle owner to Wappa composition paths; raw client aliases are not public contract.

## Alternatives rejected

- One process-wide client for all traffic (leaks bearer tokens to media hosts; different services need different timeouts).
- A fresh session per request (destroys pooling for high-volume sends).
- Hosts repairing Wappa's session (crosses ownership boundaries).
- Lazy creation of the authenticated pool (startup ownership makes readiness explicit; only the unauthenticated media pool is lazy).
