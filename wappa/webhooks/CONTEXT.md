# Webhooks Context — Glossary

Terms specific to this bounded context. Shared kernel terms (`inbox_id`, `user_id`, `phone_number`,
`platform_account_id`, Universal Model, Webhook, Processor) are defined in the root `CONTEXT.md`.

| Term | Definition |
|---|---|
| **Webhook Schema** | A Pydantic model that validates either a platform-specific webhook payload or a Universal Model form. |
| **Platform Schema** | A Pydantic model for one messaging Platform's webhook payload shape, such as WhatsApp's webhook envelope, changes, values, statuses, system events, contacts, and message types. |
| **Universal Webhook Schema** | A Pydantic schema for one Universal Model form, such as `InboundMessageWebhook`, `StatusWebhook`, `ErrorWebhook`, `SystemWebhook`, or `CustomWebhook`. |
| **Shared Primitive Schema** | A cross-cutting schema or enum that is not an inbound webhook model, such as `PlatformType`, `MessageType`, or recipient normalization primitives. |
| `WebhookValue` | Strict Pydantic model for a single WhatsApp `change.value` payload. Carries `messages`, `statuses`, `errors`, `user_preferences`, or `user_id_update`. |
| `CustomWebhookValue` | Permissive value container for app-registered Meta webhook fields not natively understood by Wappa (e.g. `message_template_status_update`). Parsed downstream by the app's registered parser. |
| `WebhookChange` | A single entry in the `changes` array. Routes its `value` to either `WebhookValue` (built-in fields) or `CustomWebhookValue` (registered fields). |
| `WebhookEntry` | Wraps the `platform_account_id` and its associated `changes` array. |
| `BaseWebhook` | Abstract contract all platform webhook containers must implement. Exposes platform-agnostic inspection methods (`is_incoming_message`, `is_status_update`, `has_errors`, etc.). |
| `BaseMessage` | Abstract contract all per-type message models must implement. |
| `InboundMessageWebhook` | Canonical name for the Universal Model representing a message sent by a User to an Inbox. |
| `StatusWebhook` | Universal Model for a delivery status event (sent / delivered / read / failed) on a business-sent message. |
| `ErrorWebhook` | Universal Model for a platform-level error not tied to a specific message delivery. |
| `SystemWebhook` | Universal Model for identity events: phone-number changes, BSUID changes, marketing-preference updates. |
| `CustomWebhook` | Universal Model carrying the output of an app-registered parser for a non-built-in Meta field. |
| `UniversalWebhook` | Type union of the five universal models above. This is what leaves the webhooks context and enters the event dispatcher. |
| `InboxBase` | Inbox identification component inside universal models. `inbox_id` equals WhatsApp `phone_number_id`; `platform_account_id` equals WhatsApp WABA ID (`entry[].id`). |
| `UserBase` | End-user identification component. `user_id` property returns BSUID when present, falls back to `phone_number`. |
| `BSUID` | Business Scoped User ID — the stable Meta v24.0+ user identifier. Used as `user_id` when available; `phone_number` is the fallback. |
| Built-in field | A Meta `change.field` value Wappa handles natively: `messages`, `user_preferences`, `user_id_update`. |
| Custom field | A Meta `change.field` value the host application registers via `WappaBuilder.register_webhook_field`. |
| `SchemaFactory` | Singleton that selects and instantiates the right `BaseWebhook` or `BaseMessage` subclass for a given platform. Delegates universal webhook creation to the processors layer. |
| `MessageSchemaRegistry` | Lookup table mapping `(PlatformType, MessageType)` → `BaseMessage` subclass. |
| `WebhookSchemaRegistry` | Lookup table mapping `PlatformType` → `BaseWebhook` subclass. |
