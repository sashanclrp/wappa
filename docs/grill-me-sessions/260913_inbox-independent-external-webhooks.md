# Inbox-independent external webhooks

Date: 2026-09-13

## Resolved language

- The optional URL value is **Webhook ID**, not Inbox ID or context ID.
- Webhook ID is opaque transport routing data and grants no authority.
- Inbox and User identity belong to Dispatch Context, not `ExternalEvent`.
- An **External Webhook Context Resolver** is a per-plugin Host strategy.

## Decisions

1. Each `WebhookPlugin` independently chooses an ID-less callback or a dynamic
   `{webhook_id}` callback. ID-less is the default.
2. `ExternalEvent` has no `inbox_id` or `user_id` fields.
3. A resolver returns one concrete `InboxRef` with an optional User, or `None`
   for deliberate Inbox-independent dispatch.
4. Wappa ships the resolver protocol, not generic header or payload-field
   resolvers. Those mappings belong to the Host Application.
5. The processor authenticates and parses before the resolver runs. Middleware
   and FastAPI dependencies may prepare request evidence, but unauthenticated
   evidence cannot select an Inbox.
6. Admission finishes before HTTP success. Resolver and authentication failures
   schedule no handler work. Successful handler dispatch remains asynchronous.
7. The change is clean-breaking. Wappa keeps no `include_inbox_id` alias and no
   old processor or event fields.

## Scenario check

A Mercado Pago callback at `/webhook/miia/mercado_pago` needs no WhatsApp value
in its URL. Its processor validates Mercado Pago's signature. A Host resolver
may then map the authenticated payment payload to an Inbox when business logic
needs Messenger or cache capabilities. If the payment has no messaging
relationship, the handler receives database access without a fabricated Inbox.
