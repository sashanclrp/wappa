# Messaging Context — Glossary

Terms specific to this bounded context. Shared kernel terms (`inbox_id`, `user_id`, `Messenger`, `Platform`) are defined in root `CONTEXT.md` and not repeated here.

| Term | Definition |
|---|---|
| **Media Source** | The three forms a media reference can take when passed to the Messenger: a file-system path (uploaded on the fly), a public URL (referenced inline), or an existing WhatsApp media ID (reused directly). |
| **Media ID** | An opaque identifier returned by the WhatsApp Media API after a successful upload. Scoped to the inbox that uploaded it. |
| **Recipient** | The outbound addressing token passed to every send method. Can be a phone number, a WhatsApp Business Suite user ID (BSUID), or an existing media ID when used as a routing target. Resolved by `resolve_recipient` before being written to API payloads. |
| **BSUID** | WhatsApp Business Suite user identifier — an alternative recipient form to E.164 phone numbers. Detected via `looks_like_bsuid`. |
| **Interactive Message** | A WhatsApp-native message type that renders actionable UI: reply-button menus, list menus, or CTA-URL buttons. Owned by `WhatsAppInteractiveHandler`. |
| **Template** | A pre-approved WhatsApp Business message structure. Three variants exist: text-only, media-header, and location-header. Template category (marketing vs. utility/service) controls which API endpoint is used. |
| **Marketing Override** | An optional flag (`override: bool`) that forces a marketing template through the `marketing_messages` endpoint instead of the default `messages` endpoint. |
| **MessageResult** | The uniform return type for every outbound send operation. Carries `success`, `message_id`, resolved recipient fields, `inbox_id` (stored as `tenant_id` in current code), platform, and optional error details. |
| **Specialized Message** | Contact cards, locations sent as a point-on-map, and location-request messages. Owned by `WhatsAppSpecializedHandler`. |
| **Template Info Service** | A read-only WABA-level helper that queries the Graph API for template metadata — listing, lookup by name, lookup by ID, and namespace resolution. Does not send messages. |
| **WhatsApp Management URL** | Graph API endpoints scoped to the WhatsApp Business Account (WABA ID), used exclusively for template management read operations. Separate from per-inbox messaging endpoints. |
| **URL Builder** | `WhatsAppUrlBuilder` — constructs per-inbox endpoint URLs (messages, media, marketing messages). `WhatsAppManagementUrlBuilder` — constructs WABA-level URLs. Both are value objects, not services. |
