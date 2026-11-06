# Inbox connection: one connector contract on a shared Meta login core

Accepted, 2026-11-06. Consolidates the Inbox Connector decision of 2026-11-05 and the 2026-11-06 architecture hardening (typed seam, one Meta Graph transport, no deauthorize side door). This ADR states the whole current decision; the earlier ADR it absorbed was deleted. Decisions 1-4 keep their earlier numbers so existing references stay valid.

## Context

Connecting an account so it becomes an Inbox is the same action on every Platform: authorize, discover what the authorization covers, turn it into Wappa identities, subscribe webhooks and keep an encrypted credential. Before this decision Wappa had Instagram-only primitives and WhatsApp Embedded Signup lived in Symphonai. The first connector erased the persisted record type with `Any`, never checked that a grant belonged to its Platform, carried a second Graph transport with hand-copied outcome classification, and kept an Instagram deauthorize route that bypassed the Inbox Directory for a callback Meta never sends for Unified Login grants.

## Decision

1. **One contract, separate from messaging.** `wappa.connections.IInboxConnector` runs before a Messenger exists, so it is not an `IMessenger` capability: `begin(host_subject, *, metadata) -> AuthorizationRequest` (redirect URL plus a one-use state bound to the Host's operator); `complete(*, state, host_subject, code, error, error_reason) -> ConnectionGrant` with `DiscoveredInbox` items (`inbox_ref`, `account_ref`, `display_name`, `InboxReadiness`); `activate(grant, inbox_ref, *, credentials, previous=None) -> ActivationResult` (subscribes webhooks, returns the Wappa-encrypted record, rotated when `previous` exists); `disconnect(inbox_ref, account_ref, token) -> bool`.
2. **Shared Meta core, per-Platform strategy.** Both Meta Platforms use Facebook Login for Business: the dialog with `config_id`, the code exchange (with or without `redirect_uri`, because the Embedded Signup popup exchanges without one) and `debug_token`. That core is `MetaBusinessLogin`, and `MetaBusinessLogin.authorize(...)` is the one consume, exchange, debug and scopes prelude both connectors call. `InstagramConnector` discovers `/me/assigned_instagram_accounts` and subscribes account fields; `WhatsAppConnector` reads shared WABAs from `debug_token`, lists `/{waba}/phone_numbers` (one Inbox per number) and subscribes the app to the WABA.
3. **Ownership.** Wappa owns protocol translation, state binding, discovery, scope evidence, subscription and record encryption. The Host owns operator authentication, intent storage, routes and UI, Owner/Channel mapping, the commit, and calling `refresh_inbox` after it commits.
4. **Readiness is explicit.** `InboxReadiness.conversation_ready`, `missing_required_scopes`, and optional Platform features in `features` (for example Instagram `comments`). Hosts connect only ready Inboxes.
5. **The seam is typed and Platform-checked.** `ActivationResult.record` is `ActiveInboxCredentialRecord` and `previous` is `CredentialRecord | None`. `activate` raises `ValueError` before any Platform call when the grant or `InboxRef` belongs to another Platform, through the one shared `require_platform` helper.
6. **One Meta Graph request function.** Graph calls share a module-level `graph_request` with one outcome classification, used by the Instagram Graph client and `InstagramSubscriptions`. The Graph version and base URL come only from `MetaApplicationConfig`. No template base class over the connectors. Extended to every Meta call, WhatsApp included, by [ADR-0029](0029-meta-graph-transport.md).
7. **No deauthorize side door.** The Instagram deauthorize route and `deauthorization_event` are removed. `InboxConnectionWebhook` is fed by WhatsApp `account_offboarded` / `account_reconnected`. If Instagram Login is supported later, its parser lives in `wappa/webhooks/instagram/` and dispatches through the Inbound Runtime; routes only adapt HTTP.
8. **Connectors stay Host-composed.** Wappa owns no connector registry until a non-Meta connector exists.

## Consequences

- A Host writes one connect flow. Telegram would add a `TelegramConnector` whose `begin` returns a credential step (bot token); `AuthorizationRequest` is redirect-only until a non-OAuth Platform arrives.
- WhatsApp `disconnect` is per WABA and stops every number in that account; Hosts call it only when no other active Inbox shares the WABA.
- Phone-number registration (`/{phone}/register` with a PIN) is not part of activation, because Embedded Signup coexistence numbers are already registered.
- Unified Login revocation is the Host's job: deactivate the record, then `disconnect`.
- Breaking (see `CHANGELOG.md`): `POST /webhook/inboxes/instagram/deauthorize`, `wappa.connections.deauthorization_event`, the `InstagramSubscriptions` constructor, and the pre-release `InstagramUnifiedLogin`, `UnifiedLoginConfig` and `build_instagram_record`.
- Symphonai can replace its own Embedded Signup service with `WhatsAppConnector` (a separate Symphonai step).

## Alternatives rejected

- Connection as an `IMessenger` capability (no Messenger exists yet).
- Keeping the deauthorize route or moving it under connections (a side door that skips the Inbox Directory and inverts layering).
- A connector template base class or a Wappa-owned connector registry before a non-Meta connector exists.
