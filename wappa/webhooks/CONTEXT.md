# Webhooks Context — Glossary

Terms specific to this bounded context. Shared kernel terms (`inbox_id`, `user_id`, `phone_number`,
`platform_account_id`, Universal Model, Webhook) are defined in the root `CONTEXT.md`.

| Term | Definition |
|---|---|
| `WebhookValue` | Strict Pydantic model for a single WhatsApp `change.value` payload. Carries `messages`, `statuses`, `errors`, `user_preferences`, or `user_id_update`. |
| `CustomWebhookValue` | Permissive value container for app-registered Meta webhook fields not natively understood by Wappa (e.g. `message_template_status_update`). Parsed downstream by the app's registered parser. |
| `WebhookChange` | A single entry in the `changes` array. Routes its `value` to either `WebhookValue` (built-in fields) or `CustomWebhookValue` (registered fields). |
| `WebhookEntry` | Wraps the `platform_account_id` and its associated `changes` array. |
| `BaseWebhook` | Abstract contract all platform webhook containers must implement. Exposes platform-agnostic inspection methods (`is_incoming_message`, `is_status_update`, `has_errors`, etc.). |
| `BaseMessage` | Abstract contract all per-type message models must implement. |
| `IncomingMessageWebhook` | Universal Model for a message sent by a user to the business. Contains a `TenantBase` (inbox), a `UserBase`, and a `BaseMessage`. |
| `StatusWebhook` | Universal Model for a delivery status event (sent / delivered / read / failed) on a business-sent message. |
| `ErrorWebhook` | Universal Model for a platform-level error not tied to a specific message delivery. |
| `SystemWebhook` | Universal Model for identity events: phone-number changes, BSUID changes, marketing-preference updates. |
| `CustomWebhook` | Universal Model carrying the output of an app-registered parser for a non-built-in Meta field. |
| `UniversalWebhook` | Type union of the five universal models above. This is what leaves the webhooks context and enters the event dispatcher. |
| `TenantBase` | Inbox identification component inside universal models. `business_phone_number_id` equals `inbox_id` for WhatsApp; `platform_tenant_id` carries `platform_account_id`. The field is named `tenant` in code; the rename to `inbox` is pending. |
| `UserBase` | End-user identification component. `user_id` property returns BSUID when present, falls back to `phone_number`. |
| `BSUID` | Business Scoped User ID — the stable Meta v24.0+ user identifier. Used as `user_id` when available; `phone_number` is the fallback. |
| Built-in field | A Meta `change.field` value Wappa handles natively: `messages`, `user_preferences`, `user_id_update`. |
| Custom field | A Meta `change.field` value the host application registers via `WappaBuilder.register_webhook_field`. |
| `SchemaFactory` | Singleton that selects and instantiates the right `BaseWebhook` or `BaseMessage` subclass for a given platform. Delegates universal webhook creation to the processors layer. |
| `MessageSchemaRegistry` | Lookup table mapping `(PlatformType, MessageType)` → `BaseMessage` subclass. |
| `WebhookSchemaRegistry` | Lookup table mapping `PlatformType` → `BaseWebhook` subclass. |
