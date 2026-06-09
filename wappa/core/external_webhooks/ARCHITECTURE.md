# External Webhook Runtime — Architecture

## Responsibilities

- Turn an accepted External Webhook Source request into a context-bound
  `WappaEventHandler.process_external_event()` dispatch.
- Keep External Webhook Source processors focused on request validation,
  signature checks, payload translation, and optional user identity resolution.
- Validate that the `ExternalEvent.inbox_id` produced by a processor matches the
  routed Inbox.
- Build the Dispatch Context in two phases: DB-only for identity lookup, then
  full Messenger and Cache Factory context when a `user_id` is resolved.
- Return an internal process result for tests and observability without changing
  the accepted HTTP delivery contract.

## Explicit Non-Responsibilities

- HTTP route mounting and OpenAPI tags — owned by `WebhookPlugin`.
- Messaging Platform webhook intake — owned by the Inbound Runtime.
- External source persistence, retries, and delivery ledgers — owned by Host
  Applications unless promoted through a separate decision.
- Business behavior after dispatch — owned by the Host Application's
  `WappaEventHandler`.

## Module Structure

```
wappa/core/external_webhooks/
├── __init__.py
└── runtime.py
```

`ExternalWebhookRuntime` is the deep module behind `WebhookPlugin`. It owns the
orchestration that would otherwise leak into every external webhook route:
processor parse, Inbox mismatch guard, Dispatch Context creation, handler clone,
and external event dispatch.

`ExternalWebhookRuntime.process()` returns `ExternalWebhookProcessResult` with
one of: `accepted_dispatch`, `inbox_mismatch`, `parse_failure`,
`unresolved_user`, or `dispatch_failure`. These statuses are internal
observability signals. `WebhookPlugin` still returns `{"status": "accepted"}`
once background work is submitted.

`clone_request_with_body()` creates a request snapshot for tracked background
work. The plugin reads the body before accepting the webhook, then passes the
snapshot to the runtime so processors can still use the normal `Request` API.
