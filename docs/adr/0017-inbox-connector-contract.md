# Inbox Connector: one contract for connecting accounts

Accepted, 2026-11-05. Follows [ADR-0016](0016-one-messenger-method-per-action.md).

Connecting an account so it becomes an Inbox is the same action on every Platform: authorize, discover what the authorization covers, turn that into Wappa identities, subscribe webhooks and keep an encrypted credential. Before this decision Wappa had Instagram-only primitives (`InstagramUnifiedLogin`), and WhatsApp Embedded Signup lived in Symphonai, so each Platform was connected differently and every Host had to rebuild the WhatsApp side.

## Decision

1. **One contract, separate from messaging (SRP).** `wappa.connections.IInboxConnector` runs before a Messenger exists, so it is not an `IMessenger` capability:
   - `begin(host_subject)` returns an `AuthorizationRequest` (redirect URL plus a one-use state bound to the Host's operator);
   - `complete(state, host_subject, code, …)` returns a `ConnectionGrant` with `DiscoveredInbox` items (`inbox_ref`, `account_ref`, `display_name`, `InboxReadiness`);
   - `activate(grant, inbox_ref, credentials, previous)` subscribes webhooks and returns an `ActivationResult` with the Wappa-encrypted record (rotated when `previous` exists);
   - `disconnect(inbox_ref, account_ref, token)` stops webhook delivery.
2. **Shared Meta core, per-Platform strategy.** Both Meta Platforms use Facebook Login for Business: the dialog with `config_id`, the code exchange (with or without `redirect_uri`, because the Embedded Signup JavaScript SDK popup exchanges without one) and `debug_token`. That core is `MetaBusinessLogin`. `InstagramConnector` discovers `/me/assigned_instagram_accounts` and subscribes account fields. `WhatsAppConnector` reads shared WABAs from `debug_token`, lists `/{waba}/phone_numbers` (one Inbox per number) and subscribes the app to the WABA.
3. **Ownership is unchanged from ADR-0015.** Wappa owns protocol translation, state binding, discovery, scope evidence, subscription and record encryption. The Host owns operator authentication, intent storage, routes and UI, Owner/Channel mapping, the commit, and calling `refresh_inbox` after it commits.
4. **Readiness is explicit.** `InboxReadiness.conversation_ready` plus `missing_required_scopes`, and optional Platform features in `features` (for example Instagram `comments`). Hosts connect only ready Inboxes.

## Consequences

- A Host writes one connect flow; adding Telegram later means a `TelegramConnector` whose `begin` returns a credential step (bot token) instead of a redirect. That variant is not built yet: `AuthorizationRequest` is redirect-only today, and the contract will gain a credential-step result when a non-OAuth Platform arrives.
- Symphonai can replace its own Embedded Signup service with `WhatsAppConnector`. Not migrated yet; the Symphonai side is a separate step.
- WhatsApp `disconnect` is per WABA, so it stops every number in that account. Hosts call it only when no other active Inbox shares the WABA.
- Phone-number registration (`/{phone}/register` with a PIN) is not part of activation, because Embedded Signup coexistence numbers are already registered. A new-number path would add it as an explicit option.
- The unreleased `InstagramUnifiedLogin`, `UnifiedLoginConfig` and `build_instagram_record` are replaced before release.
