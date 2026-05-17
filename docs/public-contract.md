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

## Universal Webhooks

Host applications should import the user-sent-message Universal Model as:

- `from wappa.webhooks import InboundMessageWebhook`
- `from wappa.webhooks.core.webhook_interfaces import InboundMessageWebhook`

`InboundMessageWebhook` is the only public inbound-message Universal Model name. Wappa does not provide a compatibility alias for previous inbound-message model names.

Webhook processors are translation-only adapters. They return Universal Models and do not mutate ContextVars, construct messengers, construct cache factories, open DB sessions, clone handlers, or dispatch events. Those responsibilities belong to the Inbound Runtime and its Dispatch Context.
