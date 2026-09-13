# SSE / PubSub — Bounded Context Glossary

Terms specific to the SSE and PubSub bounded context. Shared kernel terms
(`inbox_id`, `user_id`, `Event Envelope`, `Subscription`, `Messenger Pipeline`)
are defined in the root `CONTEXT.md` and not repeated here.

| Term | Definition |
|---|---|
| **Event Scope** | A request-lifetime boundary, opened by `sse_event_scope`, within which every SSE publisher reads identity and metadata from a shared `SSEEventContext`. Cleared on exit even on exception. |
| **SSEEventContext** | The per-request `ContextVar` value carrying `inbox_id`, `user_id`, `bsuid`, `phone_number`, `platform`, and a free-form `metadata` bag. Set once by the framework entry point; enriched by pipeline middleware. |
| **Pending Incoming** | A staged `incoming_message` payload held on `SSEEventContext` until identity/metadata is ready. The first of `update_identity`, `update_metadata`, an outgoing send, or `post_process_message` claims and flushes it. |
| **Flush** | The act of emitting a Pending Incoming event. Idempotent — the first caller claims the payload; subsequent calls are no-ops. |
| **SSEHub** | The public structural contract used by routes, middleware, lifecycle hooks, and health. It is deliberately broker-neutral; a Host can implement it or decorate a local hub without subclassing Wappa internals. |
| **SSEEventHub** | Wappa's default in-memory `SSEHub`. It holds local Subscriptions and performs no external broadcast. |
| **SSESubscription** | One live client connection registered with a hub, optionally filtered by `platform`, `inbox_id`, `user_id`, and/or `event_type`. |
| **Local Delivery** | Delivery of an existing `SSEEventEnvelope` to matching Subscriptions on this process. It preserves the event identifier and never re-publishes to an external broker. |
| **Delivery Gap** | A Subscription queue overflow. The default hub discards queued data only to place a private close control, records `backpressure_gap`, and closes the stream so the client reconnects rather than continuing with unknown missing state. |
| **SSE Hub Metrics** | Typed, process-local connection and delivery counters returned by `snapshot_metrics()`. They are observability signals, not a durable event ledger. |
| **SSE Event Type** | A string classifying the event carried in the envelope. Built-in values: `incoming_message`, `outgoing_api_message`, `outgoing_bot_message`, `status_change`, `webhook_error`. Extensible via `register_sse_event_type`. |
| **SSELifecycleMiddleware** | Messenger Pipeline middleware (priority 70) that flushes any Pending Incoming event, awaits the outgoing send, then publishes `outgoing_bot_message` to the hub. This is the only supported SSE outbound integration point. |
| **PubSub Notification** | A compact Redis-backed signal (message id + type) broadcast on `wappa:notify:{inbox_namespace}:{user_id}:{event_type}` after a send. The Inbox Namespace is derived from `InboxRef`, preventing cross-Platform collisions. Carries less data than an SSE Event Envelope — intended for lightweight process-to-process wakeups. |
| **PubSubNotificationMiddleware** | Messenger Pipeline middleware (priority 30) that publishes a `bot_reply` PubSub Notification after every successful outgoing send. Reads identity from the active `SSEEventContext`. This is the only supported PubSub outbound integration point. |
| **`bsuid`** | A Meta-platform business-scoped user identifier matching `<CC>.<alnum>{1,128}`. Carried in the envelope alongside `phone_number`; derived from the Meta `wa_id` field when its shape matches the BSUID pattern. |
