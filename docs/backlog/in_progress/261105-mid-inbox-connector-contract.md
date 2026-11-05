---
status: in_progress (Wappa contract built 2026-11-05 per ADR-0017; remaining work below)
origin: ADR-0016 contract map (2026-11-05)
---

# Inbox Connector: one contract for connecting accounts on every Platform

Connecting an account so it becomes an Inbox is one action on every Platform, so it needs one contract. It is separate from `IMessenger` (SRP): it runs before a Messenger exists and produces the encrypted credential record a Messenger later uses.

## Today

- Instagram: `wappa.connections.instagram` (`InstagramUnifiedLogin`, `InstagramSubscriptions`) is Instagram-specific.
- WhatsApp: Embedded Signup lives in Symphonai (its `connect-whatsapp` route), not in Wappa.

## Proposed shape

```
begin(intent)       → RedirectStep(url) | CredentialStep(fields)
complete(input)     → ConnectionGrant(discovered Inboxes, granted scopes, readiness)
activate(inbox)     → Wappa-encrypted CredentialRecord + webhook subscription
disconnect(inbox)   → deactivate + unsubscribe
```

| Step | WhatsApp (Embedded Signup) | Instagram (Unified Login) | Telegram |
| --- | --- | --- | --- |
| begin | Facebook Login for Business dialog (`config_id`) | same dialog, Instagram config | credential form (BotFather token) |
| complete | code exchange → WABA and phone numbers | code exchange → `assigned_instagram_accounts` | `getMe` |
| activate | register the number, subscribe the app to the WABA | `/{ig}/subscribed_apps` | `setWebhook` with a secret token |

Both Meta Platforms share one Meta Business Login core (dialog, code exchange, `debug_token` scope readiness), plus a per-Platform discovery and activation strategy.

## Done in Wappa

`IInboxConnector`, `MetaBusinessLogin`, `InstagramConnector` and `WhatsAppConnector` with offline tests ([ADR-0017](../../adr/0017-inbox-connector-contract.md)).

## Remaining

- Live check of both connectors (Gate B for Instagram; an Embedded Signup run for WhatsApp).
- Symphonai: replace `services/meta/embedded_signup` with `WhatsAppConnector`, keeping Owner, Channel and billing as Host policy.
- A credential-step result type for non-OAuth Platforms (Telegram bot token).
- Optional phone-number `/register` (PIN) for new, non-coexistence numbers.
