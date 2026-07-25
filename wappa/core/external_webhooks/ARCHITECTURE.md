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
- Provide the reusable pieces a processor would otherwise re-implement: HMAC
  signature verification and event-type-to-handler routing.

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
├── runtime.py      # ExternalWebhookRuntime — accepted request → dispatch
├── signature.py    # HMACSignatureVerifier — generic signed-webhook verification
└── registry.py     # ExternalEventRegistry — event type → handler routing
```

`HMACSignatureVerifier` covers the shape shared by most signed webhook
providers: an HMAC of the raw body under a shared secret, carried in a header,
optionally algorithm-prefixed, hex or base64 encoded. It is a value object used
*inside* a processor's `parse_event()`; the runtime never calls it, because only
the processor knows which secret and header a given source uses. It returns
booleans rather than raising, so the processor keeps ownership of how a bad
signature is reported.

`ExternalEventRegistry` is the routing table a Host Application uses inside
`process_external_event()` when one source emits many event types. It is
transport-free by design — no HTTP, no signature checks, no Dispatch Context —
so it can be unit tested without a request and reused outside the webhook path.
Dispatch is best-effort per handler: one raising subscriber cannot silence the
others, and the returned `DispatchReport` carries the failures.

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
