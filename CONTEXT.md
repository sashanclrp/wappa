# CONTEXT.md — Wappa Shared Kernel

This is the ubiquitous language shared across all Wappa bounded contexts. Terms here are canonical; if code or docs contradict this file, this file wins until updated through a deliberate decision.

## Core Runtime Identity

| Term | Definition |
|------|-----------|
| **Inbox** | The platform-facing message ingress/egress identity. Wappa receives webhooks, sends messages, scopes caches, and streams events per Inbox. |
| `inbox_id` | The stable string identifier of an Inbox inside Wappa. For WhatsApp today, this is Meta's `phone_number_id`. For future platforms, it will be the equivalent platform-native channel/bot identity. |
| **Platform** | An external messaging platform such as WhatsApp, Telegram, Instagram, or Teams. |
| `PlatformType` | The enum of supported platforms. Values: `whatsapp`, `telegram`, `instagram`, `teams`. |
| **Platform Account** | Platform-side account metadata that groups one or more Inboxes. For WhatsApp this is the WABA (WhatsApp Business Account). |
| `platform_account_id` | The identifier of the Platform Account. For WhatsApp, this is the WABA ID (`entry[].id` in Meta's webhook payload). |

## User Identity

| Term | Definition |
|------|-----------|
| **User** | The end-user/contact inside a platform conversation. A User talks to an Inbox. |
| `user_id` | The canonical stable user identifier inside Wappa. Prefers BSUID when available; falls back to phone number. Used for cache scoping and state lookups. |
| **BSUID** | Business Scoped User ID. Meta's stable user identifier (v24.0+) that persists across phone number changes. Format: `^[A-Z]{2}\.[A-Za-z0-9]{1,128}$`. |
| `phone_number` | The raw E.164 phone number of the user. May change; not stable for identity. Retained for marketing and PII use cases. |

## Host Integration

| Term | Definition |
|------|-----------|
| **Host Application** | The application embedding Wappa (e.g., Symphonai). Owns business concepts like Owner, Channel, customer, and workflow. Wappa does not define these. |
| **WappaEventHandler** | The interface a Host Application implements to receive dispatched events and execute business logic. |
| `owner_id` | Not a Wappa runtime concept. If a host application needs owner attribution for log correlation, it manages that in its own middleware outside Wappa. Wappa does not store, route, or scope by owner_id. |

## Event Processing

| Term | Definition |
|------|-----------|
| **WappaEventHandler** | Abstract base class the Host Application implements. Receives dispatched events with per-request context (`inbox_id`, `user_id`, `messenger`, `cache_factory`, `db`) already injected. |
| `process_message(webhook)` | Fires when a User sends a message to an Inbox. Input: `IncomingMessageWebhook`. The only abstract (required) processor. |
| `process_status(webhook)` | Fires on message delivery status changes (sent, delivered, read, failed). Input: `StatusWebhook`. |
| `process_error(webhook)` | Fires when the platform reports an error. Input: `ErrorWebhook`. |
| `process_system_webhook(webhook)` | Fires on system events: phone number change, BSUID update, marketing preference change. Input: `SystemWebhook`. |
| `process_external_event(event)` | Fires when a third-party webhook (MercadoPago, Stripe, CRM) is routed through Wappa. Input: `ExternalEvent`. |
| `process_api_message(event)` | Fires after a message is sent via Wappa's REST API. Used for tracking, DB writes, analytics. Input: `APIMessageEvent`. |
| `process_cron_event(event)` | Fires when a scheduled cron triggers. Input: `CronEvent`. |

## Message Flow

| Term | Definition |
|------|-----------|
| **Webhook** | An inbound HTTP request from a platform carrying message, status, or system events. |
| **Universal Model** | The platform-agnostic representation of a parsed webhook payload. All platform-specific parsing collapses into these models before dispatch. |
| **Event Dispatch** | The act of routing a parsed universal model to the appropriate WappaEventHandler processor method. |
| **Messenger** | The outbound message interface. Sends text, media, interactive, template, and specialized messages to a User on a Platform via an Inbox. |
| **Messenger Pipeline** | Composable middleware stack wrapping outbound message calls (SSE lifecycle, PubSub notification, etc.). |

## Persistence

| Term | Definition |
|------|-----------|
| **Cache Factory** | Creates scoped cache instances. Scoped by `(inbox_id, user_id)`. |
| **State Cache** | Per-user conversational state within an Inbox. |
| **User Cache** | Per-user profile/metadata cache within an Inbox. |
| **Table Cache** | Structured record storage scoped by Inbox. |

## Real-Time

| Term | Definition |
|------|-----------|
| **SSE Event** | A server-sent event pushed to subscribers. Scoped by `inbox_id` and optionally by `user_id` and `event_type`. |
| **Event Envelope** | The JSON structure wrapping an SSE event: `{ event_id, event_type, timestamp, inbox_id, user_id, bsuid, phone_number, platform, source, payload, metadata }`. |
| **Subscription** | A client connection filtering events by `inbox_id`, `user_id`, and/or `event_type`. |

## Expiry

| Term | Definition |
|------|-----------|
| **Expiry Action** | A time-triggered handler that fires when a Redis key expires. Registered via decorator. |
| **Expiry Key** | Redis key with TTL. Format: `{inbox_id}:EXPTRIGGER:{action}:{identifier}`. Parsed on expiration to route to the correct handler. |

## Anti-Language (Do NOT Use)

| Forbidden Term | Use Instead |
|----------------|-------------|
| `tenant`, `tenant_id` | `inbox_id` (if it means the platform-facing identity) or `owner_id` (if it means a business grouping supplied by the host) |
| `multi-tenant` | "multi-inbox" if describing Wappa's ability to handle multiple inboxes; avoid entirely if describing business tenancy (not Wappa's concern) |
| `provider` (as a code identifier) | `platform` — the canonical term in Wappa for external messaging services |
| `TenantBase`, `TenantCredentialsService` | `InboxBase`, `SettingsInboxCredentialStore` (or any `IInboxCredentialStore` implementation) |
