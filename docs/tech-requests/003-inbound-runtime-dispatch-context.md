---
id: 003
title: Deep Inbound Runtime and Dispatch Context
status: proposed
request_type: architecture-prd
model_fit:
  primary_100_percent:
    - GPT-5.5
    - GPT-5.4
    - GPT-5.3-Codex
  delegatable_with_review:
    - Claude Opus 4.6
    - Claude Sonnet 4.6
  not_recommended_for_autonomous_execution:
    - small/fast models without codebase-wide refactor support
execution_note: >
  This PRD describes a breaking implementation refactor. The PRD file itself is
  documentation, but the requested follow-up work is code, tests, and docs.
---

# Tech Request: Deep Inbound Runtime and Dispatch Context

## Why This Matters

Wappa currently has a real inbound runtime, but the code language still hides it inside webhook controller, processor, and request-context terminology.

The inbound path is bigger than HTTP webhook handling. It turns an accepted platform webhook into a context-bound handler dispatch with:

- `inbox_id`
- `user_id`
- Messenger
- Cache Factory
- DB access
- SSE identity
- cloned `WappaEventHandler`
- event dispatch

That bundle is the **Dispatch Context**. Calling it request context is misleading because webhook processing can continue after the HTTP request has returned.

## Canonical Language

| Term | Meaning |
|------|---------|
| **Inbound Runtime** | The Wappa module that turns an accepted platform webhook into a context-bound handler dispatch. |
| **Dispatch Context** | The per-event runtime bundle containing identity, Messenger, Cache Factory, DB access, SSE identity, and the cloned handler. |
| **Processor** | Pure platform payload translator. Parses a platform webhook payload into a Universal Model. |
| **InboundMessageWebhook** | Target name for the user-sent-message Universal Model. Replaces `IncomingMessageWebhook`. |
| **Clean Breaking Change** | Intentional rename/removal that forces Host Applications to adopt canonical Wappa language. |

## What To Build

This PRD proposes a future implementation change. Do not implement it while writing this PRD.

1. Create or rename a module that explicitly owns the Inbound Runtime.
2. Move orchestration logic out of the current webhook controller into this module:
   - validate URL `inbox_id`
   - validate routed `inbox_id` through the configured `IInboxCredentialStore`
   - call the platform Processor
   - validate payload inbox metadata against URL `inbox_id`
   - build Dispatch Context
   - open SSE scope
   - dispatch to `WappaEventDispatcher`
3. Introduce an explicit `DispatchContext` value object or small internal structure.
4. Rename `IncomingMessageWebhook` to `InboundMessageWebhook` everywhere.
5. Keep the HTTP route/controller thin: parse JSON, validate route params, delegate to Inbound Runtime, return accepted/failed HTTP response.

## What NOT To Build

- No compatibility alias for `IncomingMessageWebhook`.
- No gradual dual-name period.
- No Processor access to ContextVars, Messenger, Cache Factory, DB sessions, or handler cloning.
- No business-tenancy language.
- No route shape change unless required by the implementation.

## How

1. Add the Inbound Runtime module near the current orchestration boundary.
2. Extract handler-context creation from `WebhookController._create_request_handler()` into Dispatch Context construction.
3. Make Processor calls return Universal Models only.
4. Rename inbound message model and imports from `IncomingMessageWebhook` to `InboundMessageWebhook`.
5. Update tests to assert the Inbound Runtime:
   - rejects payload inbox mismatch
   - builds the right Dispatch Context per inbox
   - dispatches messages, statuses, errors, system events, and custom webhooks correctly

## Acceptance Criteria

- [ ] Inbound Runtime exists as a named module/class/function boundary.
- [ ] Dispatch Context is explicit in code or as a clearly named internal structure.
- [ ] `IncomingMessageWebhook` is removed.
- [ ] `InboundMessageWebhook` is the only public inbound-message Universal Model name.
- [ ] Processors do not mutate ContextVars.
- [ ] Processors do not build Messenger, Cache Factory, DB sessions, or handlers.
- [ ] URL `inbox_id` wins over payload metadata.
- [ ] Payload `phone_number_id` mismatch is rejected.
- [ ] Tests cover multi-inbox dispatch in a single process.

## Affected Files

- `wappa/api/controllers/webhook_controller.py`
- `wappa/api/routes/webhooks.py`
- `wappa/processors/base_processor.py`
- `wappa/processors/whatsapp_processor.py`
- `wappa/webhooks/core/webhook_interfaces/universal_webhooks.py`
- `wappa/webhooks/__init__.py`
- `wappa/core/events/event_handler.py`
- `wappa/core/events/event_dispatcher.py`
- `wappa/core/sse/handlers.py`
- `wappa/core/pubsub/handlers.py`
- CLI examples importing `IncomingMessageWebhook`
- tests for webhook processing and handler context
