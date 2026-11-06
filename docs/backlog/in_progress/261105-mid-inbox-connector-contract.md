---
status: in_progress (contract shipped per ADR-0017 and hardened per ADR draft 0026; open Wappa items below)
origin: ADR-0016 contract map (2026-11-05); refreshed 2026-11-06 (architecture hardening H-31)
---

# Inbox Connector: open Wappa items

The contract shape lives in [ADR-0017](../../adr/0017-inbox-connector-contract.md) and the public contract (`wappa.connections`): `begin(host_subject)`, `complete(state, host_subject, code, …)`, `activate(grant, inbox_ref, *, credentials, previous)` and `disconnect(inbox_ref, account_ref, token)`, implemented by `InstagramConnector` (Unified Login) and `WhatsAppConnector` (Embedded Signup) on the shared `MetaBusinessLogin` core. This draft tracks only what Wappa still owes.

## Open

- **Instagram live leftovers.** Gate B passed live on 2026-11-05 (B-01, B-02, B-03, B-04 and B-06 pass; B-05 and B-07 not applicable to Unified Login; see the [Gate B results](./261103-instagram-conversations/tests/live-test-plan.md#gate-b-results-2026-11-05--closed-b-01-b-02-b-03-b-04-b-06-pass-b-05-b-07-not-applicable-to-unified-login-b-08-not-run)). Still open: B-08 (connect a Creator account, not run for lack of one), plus an optional live rerun of `InstagramSubscriptions.subscribe`, `subscribed_fields` and `unsubscribe` now that H-30 routes them through `graph_request`.
- **An Embedded Signup run for WhatsApp.** Connect a coexistence number through the JavaScript SDK popup (code exchanged without `redirect_uri`), confirm WABA discovery from `debug_token`, WABA `subscribed_apps` and per-WABA disconnect.
- **A credential-step `begin` result for non-OAuth Platforms.** `AuthorizationRequest` is redirect-only; a Telegram connector needs `begin` to return a credential step (bot token) instead. Build it with the first non-Meta connector, not before.
- **Optional phone-number `/register`.** Activation does not call `/{phone_number_id}/register` (two-step PIN) because coexistence numbers are already registered. A new-number path would add it as an explicit option.

Host adoption (for example a Host replacing its own Embedded Signup service with `WhatsAppConnector`) is Host work and is tracked in that Host's backlog, not here.
