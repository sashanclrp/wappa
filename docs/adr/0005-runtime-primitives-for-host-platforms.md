# ADR-0005: Runtime Primitives for Host Platforms

**Status:** Accepted  
**Date:** 2026-07-25  
**Supersedes:** None  
**Extends:** ADR-0001 (Inbox ID Runtime Scope)

## Context

Host platforms building on Wappa (Symphonai, and the minimal Mimeia platform before it) kept re-implementing the same backend building blocks: verifying signed webhooks, routing one provider's many event types to handlers, namespacing and invalidating cached read models, correlating a request across logs, and retrying transient integration failures.

Each of those is generic. Implementing them per host means every host re-derives the same trade-offs — and gets them subtly different. The alternative to promoting them is worse: hosts grow a parallel framework layer above Wappa, reaching into `wappa.core.*` internals to stay consistent with it.

The constraint is that promoting them must not import host business language into Wappa. Wappa owns Platform webhook intake, sending, dispatch, runtime cache scoping, and contract stability. It does not own Owner, Channel, Campaign, or any host tenancy concept.

## Decision

Promote five primitives into Wappa behind shallow public imports, expressed entirely in Wappa runtime vocabulary (Inbox, External Webhook Source, Table Cache, Request ID).

### 1. Signature verification is a value object, not a runtime step

`HMACSignatureVerifier` is used *inside* a processor's `parse_event()`. The External Webhook Runtime does not call it, because only the processor knows which secret and header a given source uses, and some sources sign a canonical string rather than the raw body.

It returns a verdict rather than raising, so the processor keeps ownership of how a bad signature is reported. Misconfiguration (empty secret, unknown algorithm) raises at construction instead — a webhook "verified" against an empty secret is worse than no verification, so that failure must be loud and early.

### 2. Event routing is host-driven and transport-free

`ExternalEventRegistry` maps `(source, event_type)` to async handlers. Wappa does not install it into the External Webhook Runtime: doing so would make handler registration a framework concern and force a single global routing table on every host.

Dispatch is best-effort per handler, matching the existing best-effort delivery contract for External Webhook Sources. One raising subscriber cannot silence the others; failures surface through `DispatchReport` rather than an exception, because there is no meaningful HTTP response left to fail.

### 3. Read-model invalidation uses a generation counter, not key enumeration

`VersionedTableCache` suffixes its table with a generation (`agents@v3`) read from a counter row. Invalidation is one increment.

The rejected alternative — SCAN-and-delete across the key space — is slow on Redis and cannot be made atomic while writers are active: a writer racing the delete sweep resurrects a stale row.

Two consequences are deliberate:

- **One extra cache read per operation.** Caching the generation in-process would be faster and wrong: another worker's bump would be invisible, and that process would keep serving rows the system already invalidated.
- **`default_ttl` is required, not optional.** A bump orphans the previous generation rather than deleting it. TTL is the only reclamation path, so a versioned cache without one leaks.

The generation counter carries its own TTL, derived from `default_ttl` and refreshed on each bump. Backends apply a default TTL to every write, so the counter cannot simply be stored forever; instead it is stored with a margin above the data TTL. That guarantees it outlives the rows a bump orphans — the failure mode otherwise is the counter expiring back to `v1` and resurrecting them. Expiry after a long idle period is harmless: it costs a cold cache, not stale data.

### 4. Cache space is host-owned; Inbox scoping stays Wappa's

Inbox scoping is applied by the `ICacheFactory` and is not negotiable. A *cache space* is a second, optional segment the host passes explicitly (`{cache_space}:{table_name}`), letting two host modules share a table name inside one Inbox.

Wappa never invents or infers a cache space — inferring one would be Wappa modelling host structure. Omitting it leaves existing key shapes byte-identical, so this is additive for every current caller. Both segments reject `:` and `@` so a caller cannot smuggle extra key structure through a name.

### 5. Request IDs are outermost and reuse a trusted inbound header

`RequestIdMiddleware` is installed by `WappaCorePlugin` at the lowest middleware priority, making it outermost: the ID then exists for every inner middleware, route, log line, and error-handler response.

By default an inbound `X-Request-ID` is reused so a trace survives across service hops. That trusts the caller, so the value is bounded (non-empty, printable, ≤128 chars) before it reaches every downstream log line, and `trust_inbound=False` turns reuse off at an untrusted edge.

The ID lives in a ContextVar reset when the response is produced. Background work that outlives the request therefore has no request ID — correct, because it is no longer that request.

### 6. Transient-failure classification is centralised

`wappa.resilience` owns the single definition of "transient", and `PostgresSessionManager` now delegates to it instead of carrying its own copy.

Classification is the load-bearing part: retrying a contract failure turns a fast error into a slow one, and refusing to retry a blip turns it into an outage. Notably, SQLAlchemy pool checkout timeouts are classified **non**-transient despite a message that reads like a connectivity failure — the pool is already drained, so retrying parks the request and saturates the pooler further.

`asyncio.CancelledError` is never retried, and the final attempt's exception propagates unchanged so callers keep the original traceback.

## Consequences

- Host platforms consume these through `wappa`, `wappa.persistence`, `wappa.resilience`, `wappa.api.middleware`, and `wappa.core.logging` — no deep imports into internals.
- All six surfaces are public contract; changing them is a breaking change.
- `X-Request-ID` now appears on every response from a Wappa-built app, and `request_id` on JSON log records during a request. Both are additive.
- Retries and rate limiting remain per-process and in-memory. Distributed variants are deliberately out of scope until a host demonstrably needs them.
- Wappa does not provide retry policy, dead-letter storage, or idempotency for External Webhook Sources. `retry_*` helps a host build that; it is not that contract.
