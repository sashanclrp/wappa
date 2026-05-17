# Public Contract

This file tracks Wappa surfaces that host applications may import, call, configure, subscribe to, or depend on.

## Inbox Credentials

Host applications may configure the credential lookup strategy through:

- `WappaBuilder.with_inbox_credential_store(store)`
- `Wappa(inbox_credential_store=store)`
- `Wappa.set_inbox_credential_store(store)`

The store must implement `IInboxCredentialStore`:

- `get_credentials(inbox_id) -> InboxCredentials`
- `validate_inbox(inbox_id) -> bool`
- `invalidate_cache(inbox_id) -> None`

When no custom store is configured, Wappa uses `SettingsInboxCredentialStore`, which resolves the single configured Inbox from `WP_PHONE_ID`, `WP_ACCESS_TOKEN`, and `WP_BID`.

`DatabaseInboxCredentialStore` is provided for host-owned `wappa_inboxes` tables. Wappa reads the table but does not own inbox CRUD, migrations, token rotation, or encryption policy.

## Inbound Webhook Schemas

Host applications import inbound webhook schemas and Universal Models from
`wappa.webhooks`.

Public inbound imports include:

- `wappa.webhooks.IncomingMessageWebhook`
- `wappa.webhooks.StatusWebhook`
- `wappa.webhooks.ErrorWebhook`
- `wappa.webhooks.SystemWebhook`
- `wappa.webhooks.CustomWebhook`
- `wappa.webhooks.UniversalWebhook`
- `wappa.webhooks.whatsapp.WhatsAppWebhook`
- `wappa.webhooks.whatsapp.*` platform payload schemas

The old inbound schema paths under `wappa.schemas.whatsapp`,
`wappa.schemas.factory`, and `wappa.schemas.core.base_*` are intentionally
removed. No compatibility import path is provided.

`wappa.schemas` remains public only for shared primitives such as:

- `wappa.schemas.core.types.PlatformType`
- `wappa.schemas.core.types.MessageType`
- `wappa.schemas.core.recipient.RecipientRequest`
- `wappa.schemas.core.recipient.apply_recipient_to_payload`
