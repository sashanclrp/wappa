# External Webhook Runtime architecture

## Responsibilities

- Admit External Webhook Source requests before returning success.
- Keep processors responsible for provider authentication, request validation,
  and payload translation.
- Let a Host strategy resolve optional Inbox context from the authenticated
  event, headers, database state, or trusted FastAPI request state.
- Bind a handler with database-only context when the event has no Inbox.
- Dispatch admitted events through tracked background work.
- Provide reusable HMAC verification and event-type routing tools.

## Boundaries

`WebhookPlugin` owns HTTP routes and response mapping. The External Webhook
Runtime owns admission and dispatch. Host Applications own business mappings,
including any relation between an external resource and a Wappa Inbox.

Messaging Platform webhook intake remains in the Inbound Runtime. External
webhook persistence, retries, idempotency, and delivery ledgers remain Host
responsibilities.

## Admission and dispatch

```text
request body and optional webhook_id
  -> processor authenticates and parses
  -> Wappa writes the route webhook_id onto ExternalEvent
  -> Host context resolver runs, when configured
  -> handler gets database-only or Inbox-scoped capabilities
  -> HTTP 200 {"status": "accepted"}
  -> tracked background handler dispatch
```

Admission finishes before Wappa acknowledges the sender. A processor or
resolver may raise `HTTPException` to control an expected HTTP failure. Wappa
maps validation and contradictory Inbox resolution to 400, unavailable Inbox
infrastructure to 503, and unexpected admission failures to 500. No background
work starts after failed admission.

Handler failures happen after acknowledgment. The background result reports
`accepted_dispatch` or `dispatch_failure`; it does not change the HTTP response.

## Identity rules

`webhook_id` is an optional opaque route value. Wappa passes it to
`IWebhookProcessor.parse_event()` and then assigns the route value to
`ExternalEvent.webhook_id`. A processor cannot replace that value. Webhook ID
never selects an Inbox and grants no authority.

`ExternalEvent` carries no `inbox_id` or `user_id`. Those values belong to the
Dispatch Context. An `IExternalWebhookContextResolver` returns either:

- `ResolvedExternalWebhookContext(inbox_ref, user_id=None)` for Inbox-scoped
  dispatch; or
- `None` for deliberate Inbox-independent dispatch.

The resolution type requires an `InboxRef`, so a resolver cannot return a User
without an Inbox. Wappa builds a Messenger whenever it receives an Inbox
resolution and adds a user-scoped Cache Factory when `user_id` is present.

Resolvers run after processor authentication. FastAPI middleware or dependencies
may put candidate routing evidence on `request.state`, but Wappa does not trust
that evidence before authentication. Middleware that performs privileged context
resolution must authenticate the request itself.

## Supporting modules

- `runtime.py` owns admission, context binding, and background dispatch.
- `signature.py` contains `HMACSignatureVerifier`. Processors decide which
  secret, canonical input, header, and failure response apply.
- `registry.py` contains the Host-driven `(source, event_type)` handler registry.
  Registry dispatch remains transport-free and best-effort per subscriber.
