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
| **Coexistence** | Meta capability (for verified Tech Providers) that connects a client's existing WhatsApp number to the Cloud API. It emits account-scoped webhooks — `account_offboarded` / `account_reconnected` — that target a Platform Account (WABA), carry no User context, and surface as `SystemWebhook`. |

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
| **WappaEventHandler** | Abstract base class the Host Application implements. Receives dispatched events with Dispatch Context dependencies (`inbox_id`, `user_id`, `messenger`, `cache_factory`, `db`) already injected. |
| `process_message(webhook)` | Fires when a User sends a message to an Inbox. Input: `InboundMessageWebhook`. |
| `process_status(webhook)` | Fires on message delivery status changes (sent, delivered, read, failed). Input: `StatusWebhook`. |
| `process_error(webhook)` | Fires when the platform reports an error. Input: `ErrorWebhook`. |
| `process_system_webhook(webhook)` | Fires on system events. User-scoped: phone number change, BSUID update, marketing preference change. Account-scoped (Platform Account / WABA, no User): coexistence `account_offboarded` / `account_reconnected`. Input: `SystemWebhook`. |
| `process_external_event(event)` | Fires when a third-party webhook (MercadoPago, Stripe, CRM) is routed through Wappa. Input: `ExternalEvent`. |
| `process_api_message(event)` | Fires after a message is sent via Wappa's REST API. Used for tracking, DB writes, analytics. Input: `APIMessageEvent`. |
| `process_cron_event(event)` | Fires when a scheduled cron triggers. Input: `CronEvent`. |

## Message Flow

| Term | Definition |
|------|-----------|
| **Webhook** | An inbound HTTP request from a platform carrying message, status, or system events. |
| **Inbound Runtime** | The Wappa module that turns an accepted platform webhook into a context-bound handler dispatch. It owns orchestration across Inbox/User context, Messenger, Cache Factory, DB sessions, SSE scope, and event dispatch. |
| **Dispatch Context** | The per-event runtime bundle containing `inbox_id`, `user_id`, `messenger`, `cache_factory`, DB access, SSE identity, and the cloned `WappaEventHandler`. Use this instead of "request context" for event processing because background work may outlive the HTTP request. |
| **Processor** | A pure platform payload translator. A Processor parses a platform webhook payload into a Universal Model. It must not mutate ContextVars, build messengers, resolve cache factories, or clone handlers. |
| **Universal Model** | The platform-agnostic Pydantic schema representation of a parsed webhook payload. All platform-specific parsing collapses into these models before dispatch. |
| **InboundMessageWebhook** | Canonical name for the Universal Model representing a User-sent message entering Wappa. |
| **Event Dispatch** | The act of routing a parsed universal model to the appropriate WappaEventHandler processor method. |
| **Messenger** | The outbound message interface. Sends text, media, interactive, template, and specialized messages to a User on a Platform via an Inbox. |
| **Messenger Pipeline** | Composable middleware stack wrapping outbound message calls (SSE lifecycle, PubSub notification, etc.). |
| **External Webhook Source** | A non-messaging system that sends webhooks into Wappa, such as MercadoPago, Stripe, Wompi, GitHub, or a CRM. |
| **External Webhook Runtime** | The Wappa module that turns an accepted External Webhook Source request into a context-bound `process_external_event()` dispatch. It owns Inbox mismatch checks, Dispatch Context creation, handler cloning, and event dispatch. |
| **Payment Provider** | A payment-specific External Webhook Source, such as MercadoPago, Stripe, or Wompi. This term is allowed for payment integrations, not for messaging platforms. |

## Persistence

| Term | Definition |
|------|-----------|
| **Inbox Credential Store** | The strategy Wappa uses to resolve outbound platform credentials for an Inbox. The default store reads one Inbox from settings; host applications may provide a store backed by their own database and cache. |
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

## HTTP Client Lifecycle

| Term | Definition |
|------|-----------|
| **SessionLifecycle** | Owns the authenticated HTTP session used for platform API calls and the unauthenticated media download client. Provides drain-aware access, serialized recreation, and clean shutdown for both clients. |
| `get_session()` | Returns the authenticated `httpx.AsyncClient` for platform API calls (Meta Graph API). Carries Bearer token. Raises `RuntimeDrainingError` during shutdown. |
| `get_media_download_client()` | Returns the pooled unauthenticated `httpx.AsyncClient` for downloading public/third-party media. Never carries auth headers. Lazily created on first access. |
| **BackgroundWorkTracker** | Tracks all fire-and-forget `asyncio.Task` instances created by framework code (event dispatch, SSE flush, expiry handlers). Rejects new work during drain; awaits in-flight tasks with bounded timeout during shutdown. |
| **Three-Phase Shutdown** | Priority 90: mark draining (reject new work). Priority 70: drain tracked background tasks. Priority 10: stop memory cleanup, close HTTP clients, clear app state. |

## Anti-Language (Do NOT Use)

| Forbidden Term | Use Instead |
|----------------|-------------|
| `tenant`, `tenant_id` | `inbox_id` (if it means the platform-facing identity) or `owner_id` (if it means a business grouping supplied by the host) |
| `multi-tenant` | "multi-inbox" if describing Wappa's ability to handle multiple inboxes; avoid entirely if describing business tenancy (not Wappa's concern) |
| `provider` (as a code identifier) | `platform` — the canonical term in Wappa for external messaging services |
| `Request Context` (for event dispatch) | `Dispatch Context` |
| `Compatibility Shim` | No replacement. Wappa should prefer clean breaking changes over old import-path preservation. |
| `TenantBase`, `TenantCredentialsService` | `InboxBase`, `SettingsInboxCredentialStore` (or any `IInboxCredentialStore` implementation) |
