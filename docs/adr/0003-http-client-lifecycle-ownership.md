# ADR-0003: HTTP Client Lifecycle Ownership

**Status:** Accepted  
**Date:** 2026-05-26

## Context

Wappa creates a lifespan-scoped `httpx.AsyncClient` at startup (`WappaCorePlugin._core_startup`) and shares it across all WhatsApp messenger instances via `app.state.http_session`. When the lifespan ends (shutdown, hot-reload), the client is closed — but nothing invalidated cached messengers holding references to it.

Downstream host applications (e.g., Symphonai) worked around this by detecting closed sessions inside their own engine/agency layers and rebinding Wappa's internal transport. This crosses ownership boundaries: agency code should not know that Wappa uses httpx or how to repair its session.

Additionally, Wappa uses multiple HTTP clients with different credential/trust boundaries:
- Authenticated Meta API client (bearer token) for WhatsApp sends
- Unauthenticated client for downloading media from arbitrary third-party URLs
- Host-application-owned clients for their own services (Supabase, external APIs)

A naive "use one global client" policy would leak bearer tokens to arbitrary media URLs.

## Decision

### Wappa owns messenger session validity

1. `validate_session()` in `wappa/domain/interfaces/session_provider.py` is the single guard. Every callsite that consumes `app.state.http_session` validates the session is open before use.

2. `MessengerFactory` validates its session on every `create_messenger` call. Cached messengers with stale sessions are evicted.

3. `WappaCorePlugin.recreate_http_session(app)` is the supported recovery hook for host applications that hot-reload or need to restore a closed transport.

4. Host applications must not detect or repair closed httpx sessions inside Wappa. If they encounter `HTTPSessionClosedError`, the correct action is to call the recreation hook or let the message fail with a clear error.

### Each credential/trust boundary gets its own HTTP client

| Traffic | Owner | Rationale |
|---------|-------|-----------|
| Authenticated Meta API (WhatsApp sends, template management) | Wappa lifespan client (`app.state.http_session`) | Connection pooling across high-volume sends |
| Downloads from arbitrary media URLs | Separate unauthenticated client (`whatsapp_media_handler.py`) | Bearer token must never be sent to third-party hosts |
| Host application services (Supabase, external APIs) | Host application | Different credentials, timeouts, retry semantics |
| Batch upload operations (e.g., header media refresh) | Host adapter, batch-scoped | Acceptable per-batch lifecycle; does not need to share the send client |

### DB engine shutdown policy

`engine.dispose(close=False)` is the correct shutdown behavior. During teardown, waiting for remote TCP graceful closes has no useful application outcome.

## Consequences

- `HTTPSessionClosedError` is a new error type callers may encounter if they attempt messaging after shutdown begins. This is intentional — silent failures are worse.
- Host applications that hot-reload should call `recreate_http_session()` rather than attempting to mutate Wappa internals.
- The messenger cache in `MessengerFactory` remains for performance but is now self-healing: stale entries are evicted on access rather than persisting indefinitely.
- Symphonai's temporary transport-repair workaround in `agency/` and `engine/expiry/` can be removed once this Wappa version is consumed.

## Alternatives Considered

1. **Single process-wide httpx client for all traffic** — Rejected. Leaks bearer tokens to media download URLs. Different services need different timeouts and retry semantics.

2. **Require host apps to always pass a fresh session per request** — Rejected. Destroys connection pooling which is critical for high-intensity messaging. Session reuse within the lifespan is the correct default.

3. **Let host apps repair Wappa's internal session** — Rejected (current state being fixed). Crosses ownership boundaries and creates tight coupling to Wappa's transport implementation.

4. **Lazy session creation on first use instead of lifespan startup** — Considered but deferred. Startup creation is simpler, validates connectivity early, and the recreation hook covers the hot-reload case.
