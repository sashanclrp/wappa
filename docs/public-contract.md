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

Host applications import inbound webhook schemas and Universal Models from
`wappa.webhooks`.

Public inbound imports include:

- `from wappa.webhooks import InboundMessageWebhook`
- `from wappa.webhooks.core.webhook_interfaces import InboundMessageWebhook`
- `from wappa.webhooks import StatusWebhook`
- `from wappa.webhooks import ErrorWebhook`
- `from wappa.webhooks import SystemWebhook`
- `from wappa.webhooks import CustomWebhook`
- `from wappa.webhooks import UniversalWebhook`
- `from wappa.webhooks.whatsapp import WhatsAppWebhook`
- `from wappa.webhooks.whatsapp.*` platform payload schemas

`InboundMessageWebhook` is the only public inbound-message Universal Model name. Wappa does not provide a compatibility alias for previous inbound-message model names.

The old inbound schema paths under `wappa.schemas.whatsapp`,
`wappa.schemas.factory`, and `wappa.schemas.core.base_*` are intentionally
removed. No compatibility import path is provided.

`wappa.schemas` remains public only for shared primitives such as:

- `wappa.schemas.core.types.PlatformType`
- `wappa.schemas.core.types.MessageType`
- `wappa.schemas.core.recipient.RecipientRequest`
- `wappa.schemas.core.recipient.apply_recipient_to_payload`

Webhook processors are translation-only adapters. They return Universal Models and do not mutate ContextVars, construct messengers, construct cache factories, open DB sessions, clone handlers, or dispatch events. Those responsibilities belong to the Inbound Runtime and its Dispatch Context.

## Messenger

`IMessenger` is Wappa's public outbound message interface. Host applications use it to send text, media, interactive, template, and specialized messages through an Inbox.

**Stable surface:**

- `from wappa.domain.interfaces import IMessenger`
- All `send_*` methods and `mark_as_read` on the interface
- `MessageResult` as the uniform return type

**Design commitment:**

- The interface stays as a single seam until the split threshold documented in `wappa/messaging/ARCHITECTURE.md` is met.
- If a split is justified in the future, it will be a clean breaking change with no compatibility aliases.
- Internal handler composition (per message family) is not part of the public contract.
