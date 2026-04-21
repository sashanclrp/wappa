# Messenger Middleware → Domain Event Bus (Piece 3)

## Context

The v0.4.0 messenger pipeline redesign (Pieces 1 + 2) replaced the
inheritance-based wrapper stack (`SSEMessengerWrapper`,
`PubSubMessengerWrapper`) with a priority-ordered `MessengerPipeline`
and `MessengerMiddleware` abstraction. Downstream apps now add
cross-cutting concerns (cache, retry, metrics, tracing) with one call
to `WappaBuilder.add_messenger_middleware(mw, priority)`, with no access
to private attributes.

The original redesign plan included a third piece — a
**`DomainEventBus`** — that would have converted every first-party
middleware (SSE lifecycle, pub/sub notifications) into a **subscriber**
of typed domain events (`OutgoingMessageDispatched`,
`IncomingMessageReceived`, `DeliveryStatusChanged`). We explicitly
deferred it at the time because:

1. The middleware pattern with ordered priority is *functionally* a
   synchronous ordered bus already. The SSE / pub/sub middleware each
   match the shape `result = await call_next(invocation); react(result); return result`
   — that is just a subscriber with one extra line of plumbing.
2. No concrete workload yet requires multiple observers of the same
   event (the trigger that would make the subscriber API worth its
   complexity).
3. Shipping it speculatively would add an indirection layer for zero
   present value — the anti-pattern the redesign was meant to remove.

This backlog captures the conditions under which we *should* promote
the current middleware surface into a true domain event bus, the
shape the promotion would take, and the non-goals that bound the work.

## Scope

Promote messenger observability from middleware-per-concern to a typed
domain event bus *when* the revisit triggers fire.

Deliverables:

1. **`DomainEvent`** hierarchy in `wappa/core/events/domain/`:
   - `OutgoingMessageDispatched(invocation, result, context)` — emitted
     after a successful raw send, before post-hooks unwind.
   - `IncomingMessageReceived(webhook, context)` — emitted at webhook
     entry, replacing the ad-hoc `SSEMessageHandler._pending_incoming`
     staging.
   - `DeliveryStatusChanged(status, context)` — emitted by the inbound
     status handler.
   - `WebhookProcessingFailed(error, context)` — mirror for errors.
2. **`DomainEventBus`** in `wappa/core/events/domain/bus.py`:
   - `async emit(event: DomainEvent) -> None`
   - `subscribe(event_type, handler, priority=50) -> SubscriptionHandle`
   - Subscribers are awaited in priority order (lower first / inner),
     matching the messenger pipeline convention so apps don't re-learn
     ordering semantics.
3. **First-party subscribers (rewrite, not wrap):**
   - `SSEEventsPlugin` subscribes `OutgoingMessageDispatched` →
     translates to SSE envelope and fans out via `SSEEventHub`.
     `SSEEventHub` becomes a pure transport, no longer co-owning
     "what counts as a bot reply".
   - `RedisPubSubPlugin` subscribes the same event →
     `publish_notification`.
   - `SSELifecycleMiddleware` and `PubSubNotificationMiddleware` are
     deleted; a single framework-owned
     `LifecycleEventsMiddleware(bus)` takes their place, emitting the
     domain event once.
4. **Inbound symmetry (land together):** inbound handler wrapping
   (`SSEMessageHandler`, `SSEStatusHandler`, `PubSubMessageHandler`,
   `PubSubStatusHandler`) is rewritten on top of the same bus — this
   finally kills the `event_handler._default_*_handler` private
   drilling inside `SSEEventsPlugin._startup_hook` and
   `RedisPubSubPlugin._startup_hook`.
5. **Public `WappaBuilder` surface:**
   ```python
   builder.on(OutgoingMessageDispatched, handler, priority=50)
   ```
   Plain-callable subscribers; no `call_next` noise for pure observers.

## Out of Scope

- Middleware as a concept. Middleware keeps its place for *doers*:
  retry, circuit-breaker, cache invalidation, rate-limit,
  recipient-rewrite. The bus is for *observers* only.
- Cross-tenant event routing. The bus stays in-process; distributed
  fan-out remains a pub/sub concern, with `RedisPubSubPlugin` bridging
  the in-process bus to Redis.
- Any change to the public SSE wire envelope. Subscribers must emit
  exactly the same `{event_type, source, payload, metadata}` shape
  v0.4.0 ships, so frontends don't need a migration.

## Revisit Triggers

Do not start this work until at least **one** of the following is true.
Re-evaluate quarterly.

| Trigger | Measurement | Why it matters |
|---------|-------------|----------------|
| ≥ 5 observers of `outgoing_bot_message` in production code (across Wappa + downstream apps) | `rg "priority=PRIORITY_\w+" --type py` + manual audit of downstream apps | Middleware-per-observer boilerplate stops being negligible |
| Any app needs a subscriber that reacts to a *combination* of events (e.g., `IncomingMessageReceived` → enrich → `OutgoingMessageDispatched` correlation) | Product ask; no tool-based signal | The messenger pipeline can't express cross-event workflows; a bus can |
| Inbound handler pipeline work gets prioritised (symmetric fix to D3 from the redesign plan) | Product planning | The bus subsumes that work; don't build two pipelines |
| Second platform adapter (Telegram / Instagram / iMessage) lands | `backlog/260420-platform-agnostic-incoming-webhook-abstraction.md` exits | Multi-platform makes the "SSE owns what counts as a bot reply" coupling actively painful — bus decouples transport from semantics |

## Implementation Notes

- The bus must preserve the strict ordering guarantees the middleware
  pipeline gives today (cache subscriber completes before SSE
  subscriber publishes). Use sequential `await` with priority sort, not
  `asyncio.gather`.
- Subscriber exceptions must be isolated: a failing SSE publish must
  not block the Redis publish or crash the inbound flow. Wrap each
  subscriber call in a per-subscription error boundary (log + metric,
  swallow).
- Preserve identity via `SSEEventContext` (or its successor — see
  `260420-platform-agnostic-sse-event-envelope.md`). Subscribers read
  from the context, just like middleware does today.
- Deprecation plan: in the release that ships the bus, keep
  `SSELifecycleMiddleware` and `PubSubNotificationMiddleware` as thin
  shims (single subscribe call in their `__init__`) so downstream code
  that imported them still works. Remove one release later.
- Test doubles: ship a `MemoryDomainEventBus` (synchronous, records
  events in a list) so apps can assert against emitted events without
  standing up the real bus.

## Open Questions

- Should the bus be **sync ordered** (current middleware semantics) or
  **async fan-out** (each subscriber a task) with an optional ordering
  constraint? Sync ordered keeps "cache before SSE" as the default
  with zero configuration; async fan-out scales better for many slow
  observers but forces every subscriber to declare its ordering
  dependencies explicitly. Lean sync-ordered.
- Do we expose the bus on `app.state`, on the request handler, or
  both? The messenger pipeline is request-scoped via `app.state`; the
  bus could follow the same pattern. But inbound handlers don't read
  from `app.state` today — they get injected. Decide alongside the
  inbound pipeline design.
- `SSEEventContext` is named after the transport that motivated it.
  When the bus lands, rename to `RequestIdentityContext` and move out
  of `wappa/core/sse/`. Out-of-scope here but worth mentioning in the
  exit criteria so we don't bake another SSE-named helper into a
  platform-agnostic layer.

## Exit Criteria

- [ ] `DomainEventBus` + typed events live in
      `wappa/core/events/domain/`; `SSEEventHub` is a pure transport
      with zero domain awareness.
- [ ] First-party middleware (`SSELifecycleMiddleware`,
      `PubSubNotificationMiddleware`) removed; a single
      `LifecycleEventsMiddleware` emits to the bus.
- [ ] Inbound handler drilling (`event_handler._default_*_handler`
      reassignment in `SSEEventsPlugin` / `RedisPubSubPlugin`) is gone;
      both plugins use `bus.subscribe`.
- [ ] `rg "_default_\w+_handler|_event_hub\s*=|messenger\._inner"
      wappa/` returns zero non-definition hits across the codebase.
- [ ] SSE wire envelope unchanged vs v0.4.0 (regression suite passes).
- [ ] `SSEEventContext` renamed to `RequestIdentityContext` and lifted
      out of `wappa/core/sse/`; the SSE transport imports it from the
      new location.
- [ ] `MessengerMiddleware.md` and `Architecture.md` updated to describe
      "middleware for doers, bus for observers" and when to pick which.
- [ ] Backlog file deleted.
