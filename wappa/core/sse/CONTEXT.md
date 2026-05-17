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
| **SSEEventHub** | The in-process async fan-out bus. Holds all active Subscriptions and delivers events to matching ones via bounded `asyncio.Queue`s. |
| **SSESubscription** | One live client connection registered with the hub, optionally filtered by `inbox_id`, `user_id`, and/or `event_type`. |
| **Drop-oldest policy** | When a Subscription queue is full, the hub evicts the oldest queued event before inserting the new one. No back-pressure is applied to the publisher. |
| **SSE Event Type** | A string classifying the event carried in the envelope. Built-in values: `incoming_message`, `outgoing_api_message`, `outgoing_bot_message`, `status_change`, `webhook_error`, `stream_closed`. Extensible via `register_sse_event_type`. |
| **SSELifecycleMiddleware** | Messenger Pipeline middleware (priority 70) that flushes any Pending Incoming event, awaits the outgoing send, then publishes `outgoing_bot_message` to the hub. This is the only supported SSE outbound integration point. |
| **PubSub Notification** | A compact Redis-backed signal (message id + type) broadcast on `wappa:notify:{inbox_id}:{user_id}:{event_type}` after a send. Carries less data than an SSE Event Envelope — intended for lightweight process-to-process wakeups. |
| **PubSubNotificationMiddleware** | Messenger Pipeline middleware (priority 30) that publishes a `bot_reply` PubSub Notification after every successful outgoing send. Reads identity from the active `SSEEventContext`. This is the only supported PubSub outbound integration point. |
| **`bsuid`** | A Meta-platform business-scoped user identifier matching `<CC>.<alnum>{1,128}`. Carried in the envelope alongside `phone_number`; derived from the Meta `wa_id` field when its shape matches the BSUID pattern. |
