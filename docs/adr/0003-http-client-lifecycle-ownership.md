# ADR-0003: HTTP Client Lifecycle Ownership

**Status:** Accepted
**Date:** 2026-05-26
**Amended:** 2026-08-03

## Context

Wappa creates lifespan-scoped HTTP clients at startup. Earlier implementations
published a raw client through application state, which allowed consumers and
cached messengers to outlive its ownership boundary. When the lifespan ended,
those consumers retained a closed client.

Downstream host applications (e.g., Symphonai) worked around this by detecting closed sessions inside their own engine/agency layers and rebinding Wappa's internal transport. This crosses ownership boundaries: agency code should not know that Wappa uses httpx or how to repair its session.

Additionally, Wappa uses multiple HTTP clients with different credential/trust boundaries:
- Authenticated Meta API client (bearer token) for WhatsApp sends
- Unauthenticated client for downloading media from arbitrary third-party URLs
- Host-application-owned clients for their own services (Supabase, external APIs)

A naive "use one global client" policy would leak bearer tokens to arbitrary media URLs.

## Decision

### Wappa owns messenger session validity

1. `SessionLifecycle` is the only owner of Wappa HTTP clients. Consumers receive
   provider callables (`get_session` and `get_media_download_client`), never raw
   application-state client aliases.

2. `MessengerFactory` acquires the authenticated client from the lifecycle on
   every `create_messenger` call. Cached messengers with stale sessions are evicted.

3. `WappaCorePlugin.recreate_http_session()` is the supported recovery hook for
   an active runtime whose transport was closed. The plugin already owns the
   lifecycle; callers do not pass an application object.

4. Host applications must not detect or repair closed httpx sessions inside Wappa. If they encounter `HTTPSessionClosedError`, the correct action is to call the recreation hook or let the message fail with a clear error.

### Each credential/trust boundary gets its own HTTP client

| Traffic | Owner | Rationale |
|---------|-------|-----------|
| Authenticated Meta API (WhatsApp sends, template management) | `SessionLifecycle.get_session` | Connection pooling across high-volume sends |
| Downloads from arbitrary media URLs | `SessionLifecycle.get_media_download_client` | Bearer token must never be sent to third-party hosts |
| Host application services (Supabase, external APIs) | Host application | Different credentials, timeouts, retry semantics |
| Batch upload operations (e.g., header media refresh) | Host adapter, batch-scoped | Acceptable per-batch lifecycle; does not need to share the send client |

### DB engine shutdown policy

`engine.dispose(close=False)` is the correct shutdown behavior. During teardown, waiting for remote TCP graceful closes has no useful application outcome.

## Consequences

- `HTTPSessionClosedError` is a new error type callers may encounter if they attempt messaging after shutdown begins. This is intentional — silent failures are worse.
- Active runtimes may call `recreate_http_session()` rather than mutating Wappa internals.
- The messenger cache in `MessengerFactory` remains for performance but is now self-healing: stale entries are evicted on access rather than persisting indefinitely.
- Raw authenticated and media-download client aliases are not part of application state or Wappa's public contract.

## Alternatives Considered

1. **Single process-wide httpx client for all traffic** — Rejected. Leaks bearer tokens to media download URLs. Different services need different timeouts and retry semantics.

2. **Require host apps to always pass a fresh session per request** — Rejected. Destroys connection pooling which is critical for high-intensity messaging. Session reuse within the lifespan is the correct default.

3. **Let host apps repair Wappa's internal session** — Rejected (current state being fixed). Crosses ownership boundaries and creates tight coupling to Wappa's transport implementation.

4. **Lazy authenticated-session creation on first use instead of lifespan startup** — Rejected for the authenticated pool. Startup ownership makes readiness explicit. The unauthenticated media pool remains lazy because many applications never download third-party media.
