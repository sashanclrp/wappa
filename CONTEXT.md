# CONTEXT.md — Wappa Shared Kernel

This is the ubiquitous language shared across all Wappa bounded contexts. Terms here are canonical; if code or docs contradict this file, this file wins until updated through a deliberate decision.

## Core Runtime Identity

| Term | Definition |
|------|-----------|
| **Inbox** | The platform-facing message ingress/egress identity. Wappa receives webhooks, sends messages, scopes caches, and streams events per Inbox. An Inbox is identified by its Inbox Reference. |
| `inbox_id` | The stable Platform-native string identifier of an Inbox. It is unique within one Platform, not across every Platform. For WhatsApp this is Meta's `phone_number_id`; future Platforms retain their equivalent native identifier. |
| **Inbox Reference** | Wappa's globally unique runtime identity for one Inbox, composed of `(platform, inbox_id)`. Code represents it as `InboxRef`. Components that persist, cache, route, or compare Inboxes across Platforms use this value rather than an unqualified `inbox_id`. |
| **Platform** | An external messaging platform such as WhatsApp, Telegram, Instagram, or Teams. |
| `PlatformType` | The enum of supported platforms. Values: `whatsapp`, `telegram`, `instagram`, `teams`. |
| **Platform Account** | Platform-side account metadata that groups one or more Inboxes. For WhatsApp this is the WABA (WhatsApp Business Account). |
| `platform_account_id` | The identifier of the Platform Account. For WhatsApp, this is the WABA ID (`entry[].id` in Meta's webhook payload). |
| **Platform Account Reference** | Wappa's globally unique identity for one Platform Account, composed of `(platform, platform_account_id)`. Code represents it as `PlatformAccountRef`. Components that compare, cache, or resolve Platform Accounts across Platforms use this value rather than an unqualified `platform_account_id`. |
| **Coexistence** | Meta capability (for verified Tech Providers) that connects a client's existing WhatsApp number to the Cloud API. It emits account-scoped webhooks — `account_offboarded` / `account_reconnected` — that target a Platform Account (WABA), carry no User context, and surface as `SystemWebhook`. |

## User Identity

| Term | Definition |
|------|-----------|
| **User** | The end-user/contact inside a platform conversation. A User talks to an Inbox. |
| `user_id` | The canonical stable user identifier inside Wappa. Prefers BSUID when available; falls back to phone number. Used for cache scoping and state lookups. Identity resolution is always scoped by Inbox Reference because the same Delivery Address may identify different Users in different Inboxes. |
| **BSUID** | Business Scoped User ID. Meta's user identifier scoped to one business portfolio (v24.0+). It survives username changes but Meta regenerates it when the user changes phone number; `user_id_update` carries the previous/current mapping. Format: `CC.<alphanumeric>`. |
| **Parent BSUID** | Optional enterprise identity for businesses enrolled in a parent BSUID account. It uses `CC.ENT.<alphanumeric>` and can be addressed by Inboxes across the enrolled portfolios. Keep it distinct from the portfolio BSUID. |
| `phone_number` | The raw E.164 phone number of the user. May change; not stable for identity. Retained for marketing and PII use cases. |
| **Delivery Address** | The one normalized platform address selected for an outbound call. A phone number and a BSUID are alternative Delivery Addresses; neither is Wappa's canonical User identity. A username is identity evidence, not a Delivery Address. |

## Host Integration

| Term | Definition |
|------|-----------|
| **Host Application** | The application embedding Wappa (e.g., Symphonai). Owns business concepts like Owner, Channel, customer, and workflow. Wappa does not define these. |
| **Meta Application Configuration** | The application-wide trust and Graph API configuration for one Meta App connected to one Wappa application: `MetaApplicationConfig` (App Secret, GET verify token, Graph API version, base URL). It comes from exactly one source, explicit or environment, never both. It covers every WhatsApp Platform Account and Inbox handled by that application; Wappa does not combine several Meta Apps inside one application, and the App Secret never enters an Inbox Credential Record. |
| **Inbox Routing Mode** | The application-level choice of one Inbox credential authority, `InboxRoutingMode`. `legacy` (the default) uses the single WhatsApp Inbox supplied by the complete `WP_ACCESS_TOKEN` / `WP_PHONE_ID` / `WP_BID` bundle and rejects an Inbox Directory Source. `explicit` uses the Inbox Directory fed by the Host's source, requires `SYSTEM_TOKEN_ENC_KEY`, and rejects every legacy Inbox variable. There is no third mode and the two never fall back to one another. |
| **WappaEventHandler** | The interface a Host Application implements to receive dispatched events and execute business logic. |
| `owner_id` | Not a Wappa runtime concept. If a host application needs owner attribution for log correlation, it manages that in its own middleware outside Wappa. Wappa does not store, route, or scope by owner_id. |

## Event Processing

| Term | Definition |
|------|-----------|
| **WappaEventHandler** | Abstract base class the Host Application implements. Receives dispatched events with Dispatch Context dependencies (`platform`, `inbox_id`, `user_id`, `messenger`, `cache_factory`, `db`) already injected. |
| `process_message(webhook)` | Fires when a User sends a message to an Inbox. Input: `InboundMessageWebhook`. |
| `process_status(webhook)` | Fires on message delivery status changes (sent, delivered, read, failed). Input: `StatusWebhook`. |
| `process_call(webhook)` | Fires on WhatsApp Calling connect, terminate, and call-status events. Input: `CallWebhook`. |
| `process_error(webhook)` | Fires when the platform reports an error. Input: `ErrorWebhook`. |
| `process_system_webhook(webhook)` | Fires on system events. User-scoped: phone number change, BSUID update, marketing preference change. Account-scoped (Platform Account / WABA, no User): coexistence `account_offboarded` / `account_reconnected`. Input: `SystemWebhook`. |
| `process_external_event(event)` | Fires when a third-party webhook (MercadoPago, Stripe, CRM) is routed through Wappa. Input: `ExternalEvent`. |
| `process_api_message(event)` | Fires after a message is sent via Wappa's REST API. Used for tracking, DB writes, analytics. Input: `APIMessageEvent`. |
| `process_cron_event(event)` | Fires when a scheduled cron triggers. Input: `CronEvent`. |

## Message Flow

| Term | Definition |
|------|-----------|
| **Webhook** | An inbound HTTP request from a platform carrying message, status, or system events. |
| **Callback Authentication** | The step that proves a Meta POST came from the configured Meta App: HMAC-SHA256 of the exact request bytes with `META_APP_SECRET`, compared in constant time against `X-Hub-Signature-256`, before any JSON parsing, directory read, or work scheduling. The GET challenge uses only `WP_WEBHOOK_VERIFY_TOKEN`; it is never an HMAC secret. |
| **Payload Routing** | The WhatsApp ingress step, after Callback Authentication, that splits a Meta batch into one-change deliveries and binds each to an `InboxRef` from `value.metadata.phone_number_id` or flat `value.phone_number_id`. A phone-scoped change must prove Platform Account Membership with `entry[].id`. A WABA-only change fans out to every validated active member of the Platform Account Index; the WABA ID never becomes an Inbox ID. |
| **Platform Account Membership** | The relation "this active Inbox belongs to this Platform Account", proven from the canonical Inbox Credential Record rather than from payload fields. A contradiction is `InboxMembershipError`. |
| **Batch Admission** | The all-or-nothing rule for one authenticated callback: every item is authenticated, split, resolved, membership-proven, and turned into a Dispatch Context before any delivery is scheduled. Delivery stays at least once; Wappa defines no delivery fingerprint. |
| **Inbound Runtime** | The Wappa module that turns an accepted platform webhook into a context-bound handler dispatch. It owns orchestration across Inbox/User context, Messenger, Cache Factory, DB sessions, SSE scope, and event dispatch. |
| **Dispatch Context** | The per-event runtime bundle containing the Inbox Reference, `user_id`, `messenger`, `cache_factory`, DB access, SSE identity, and the cloned `WappaEventHandler`. Use this instead of "request context" for event processing because background work may outlive the HTTP request. |
| **Inbox Execution Context** | The per-request bundle Wappa resolves once for an Inbox-dependent HTTP operation, `InboxExecutionContext`. It contains the qualified Inbox identity, its Platform Account, and the internal capabilities required by the route; it never exposes the decrypted token. `X-Wappa-Inbox-ID` selects this context and proves only that Wappa knows an active Inbox; it is not a credential and grants no permission. Local-only routes never resolve one. It is distinct from the per-event Dispatch Context. |
| **Processor** | A pure platform payload translator. A Processor parses a platform webhook payload into a Universal Model. It must not mutate ContextVars, build messengers, resolve cache factories, or clone handlers. |
| **Universal Model** | The platform-agnostic Pydantic schema representation of a parsed webhook payload. All platform-specific parsing collapses into these models before dispatch. |
| **InboundMessageWebhook** | Canonical name for the Universal Model representing a User-sent message entering Wappa. |
| **Event Dispatch** | The act of routing a parsed universal model to the appropriate WappaEventHandler processor method. |
| **Messenger** | The outbound message interface. Sends text, media, interactive, template, and specialized messages to a User on a Platform via an Inbox. |
| **Messenger Pipeline** | Composable middleware stack wrapping outbound message calls (SSE lifecycle, PubSub notification, etc.). |
| **Outbound Runtime** | The public Wappa factory that resolves Inbox credentials and active HTTP clients, constructs the platform Messenger and Messenger Pipeline, and returns small Inbox-scoped outbound capabilities. Host Applications do not construct those internals. |
| **Template Transport** | An Inbox-scoped outbound capability that accepts only platform-facing Template values and returns evidence about the platform call. It performs no Host Application governance, attribution, state, lifecycle, or persistence work. |
| **Template Transport Outcome** | Wappa's bounded statement about one Template call: `accepted`, `rejected`, `transport_unavailable`, or `indeterminate`. Acceptance proves platform acceptance and a platform Message ID; it never claims delivery, read, reply, or Host Application commit. |
| **Transport Family** | The kind of send a validated outbound payload represents — text, media, interactive, location, contact, Template, or read receipt — decided from the payload schema alone. It is a statement about shape, never about whether the send is permitted. |
| **Transport Subkind** | The concrete variant inside a Transport Family that has several: the media type, the interactive type, or which header a Template envelope carries. |
| **Outbound Transport API** | Wappa's own HTTP routes that mutate — that send something to a User. Distinct from the service routes (media upload/download/lookup, limits, validation, Template info, state handlers, health) that share their URL prefixes. An embedding Host Application omits the former and keeps the latter. |
| **External Webhook Source** | A non-messaging system that sends webhooks into Wappa, such as MercadoPago, Stripe, Wompi, GitHub, or a CRM. |
| **External Webhook Runtime** | The Wappa module that turns an accepted External Webhook Source request into a context-bound `process_external_event()` dispatch. It owns Inbox mismatch checks, Dispatch Context creation, handler cloning, and event dispatch. |
| **Payment Provider** | A payment-specific External Webhook Source, such as MercadoPago, Stripe, or Wompi. This term is allowed for payment integrations, not for messaging platforms. |
| **Signature Verifier** | A value object that checks an External Webhook Source signature against a shared secret. `HMACSignatureVerifier` covers the common shape (HMAC of the raw body, carried in a header). Used inside a processor's `parse_event()`; it returns a verdict rather than raising. |
| **External Event Registry** | A Host Application-owned routing table mapping `(source, event_type)` to async handlers, used inside `process_external_event()`. Matches exact, prefix (`payment.*`), and any (`*`) subscriptions. Dispatch is best-effort per handler. |


## Persistence

| Term | Definition |
|------|-----------|
| **Inbox Directory** | The Wappa-owned, application-scoped, read-through catalog of every Inbox available to one Wappa runtime across all supported Platforms (`InboxDirectory` over `InboxDirectoryTable`, on Table Cache under the System Scope). It resolves an Inbox's credentials and its Platform Account relationship, keeps active rows on a 60-minute sliding TTL and negative rows on a fixed 60-minute TTL, and is mutated only by Wappa commands (`refresh_inbox`, `deactivate_inbox`). Host Applications map durable records into it through the Inbox Directory Source but cannot replace its rules or implementation. It contains no Host Application Owner or business-tenancy semantics. |
| **Platform Account Index** | The Inbox Directory's cached projection of the active Inboxes under one Platform Account Reference. It is validated against primary records on every use and repaired from the source when stale; it is never membership authority. |
| **Credential Version** | `credential_version`: a positive integer that must increase across the whole lifetime of one Inbox Reference, including deactivation and recreation. A higher version wins, a lower one is stale, and an equal version is accepted only for an identical record. `updated_at` is evidence, never ordering. |
| **Inbox Credential Record** | Wappa's canonical, Platform- and status-discriminated stored value describing one Inbox's protected credentials, active state, Credential Version, and Platform Account relationship. The active member carries an Encrypted Secret Envelope; the inactive member cannot carry credential material. A Host Application may persist it in any database shape, but never invents another shape. |
| **Encrypted Secret Envelope** | Wappa's authenticated, context-bound representation of an Inbox credential secret. Host Applications may persist and return the envelope but never construct, alter, or decrypt it. |
| **Resolved Inbox Credentials** | The short-lived internal value Wappa obtains after validating and decrypting an Inbox Credential Record. Platform adapters consume it; Host Applications never receive it. |
| **Inbox Credential Resolver** | Wappa's internal read capability for resolving Inbox credentials and listing active Inboxes under a Platform Account. Wappa owns both production policies: legacy settings-backed resolution and explicit resolution through the Inbox Directory. It is not a Host Application extension point. |
| **Inbox Directory Source** | The Host Application adaptation point that maps its durable Inbox data into Wappa's canonical Inbox Credential Records. It supplies reads only. It does not define directory behavior, cache rows, routing rules, or mutation policy. |
| **Primary Session Factory** | The optional database capability exposed as `db`. It opens a primary PostgreSQL session for writes and for reads that require primary consistency. It does not apply Inbox or Host Application authorization filters. |
| **Read-Intent Session Factory** | The optional database capability exposed as `db_read`. It selects a read replica when available and provides eventual-consistency reads under its configured fallback policy. It does not apply Inbox or Host Application authorization filters. |
| **Cache Factory** | Creates scoped cache instances. Inbox-owned repositories use `(InboxRef, user_id)`; Table Cache may use another explicit `context_id` (`create_table_cache(context_id=...)`). |
| **State Cache** | Per-user conversational state within an Inbox. |
| **User Cache** | Per-user profile/metadata cache within an Inbox. |
| **Table Cache Scope** | The data-ownership namespace binding one Table Cache. Its code-level identifier is `context_id`. Wappa defines System and Inbox scopes. A Host Application may define its own business scope without making that term part of Wappa's runtime language. Scopes do not inherit from or fall back to one another. |
| `context_id` | The opaque identifier selecting a Table Cache Scope. It replaces `inbox_id` only in the Table Cache construction API. Normal Inbox-scoped Table Caches use the namespace derived from their Inbox Reference; every other cache family remains explicitly Inbox-scoped. |
| **System Scope** | The singleton Table Cache Scope for runtime data shared across every Inbox in one Wappa application. It is not an Inbox, User, Owner, or business tenant. |
| **Table Cache** | Structured record storage bound to one Table Cache Scope. The same table operations apply regardless of which scope owns the records. |
| **Cache Space** | An optional Host Application-owned namespace segment folded into a table name (`{cache_space}:{table_name}`). Separates unrelated read models that share a table name inside one Table Cache Scope. Wappa never assigns one; the host passes it explicitly. |
| **Table Generation** | The version suffix (`{table}@v{n}`) identifying the live generation of a versioned Table Cache. |
| **Version Bump** | Incrementing a versioned Table Cache's generation counter to invalidate every row at once, without enumerating keys. Orphaned generations expire by TTL. |
| **Row Transition** | An atomic table-cache write whose condition and mutation are one backend operation: create-if-absent, or replace-only-while-the-row-still-matches. Its result names exactly one of `created`, `replaced`, `already_exists`, `condition_not_met`, or `missing`. |
| **Row Condition** | The map of expected scalar field values a Row Transition compares against the stored row. Wappa does not interpret the fields; it only guarantees the comparison and the write cannot be separated. |

## Real-Time

| Term | Definition |
|------|-----------|
| **SSE Event** | A server-sent event pushed to subscribers. Scoped by Inbox Reference and optionally by `user_id` and `event_type`. |
| **Event Envelope** | The JSON structure wrapping an SSE event: `{ event_id, event_type, timestamp, inbox_id, user_id, bsuid, phone_number, platform, source, payload, metadata }`. |
| **Subscription** | A client connection filtering events by `platform`, `inbox_id`, `user_id`, and/or `event_type`. An Inbox-specific subscription identifies both Platform and `inbox_id`. |

## Request Correlation

| Term | Definition |
|------|-----------|
| **Request ID** | The correlation identifier assigned to one inbound HTTP request. Read from the inbound header when present, otherwise generated. Echoed on the response, attached to JSON log records, and cleared once the response is produced. It is request-scoped, so background work that outlives the request carries none. |

## Resilience

| Term | Definition |
|------|-----------|
| **Transient Failure** | An integration failure a retry can plausibly fix: timeouts, connection resets, DNS/TLS failures, and the retryable HTTP statuses. Distinct from contract failures (4xx, constraint violations, bad payloads) and from pool exhaustion, which retries make worse. |
| **Retry Policy** | Attempt count plus bounded exponential backoff with jitter, applied by the `wappa.resilience` decorators. |

## Expiry

| Term | Definition |
|------|-----------|
| **Expiry Action** | A time-triggered handler that fires when a Redis key expires. Registered via decorator. |
| **Expiry Key** | Redis key with TTL. Format: `{inbox_id}:EXPTRIGGER:{action}:{identifier}`. Parsed on expiration to route to the correct handler. It carries no User dimension — a trigger belongs to an action and an identifier, which may or may not be a `user_id`. |

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
| `TenantBase`, `TenantCredentialsService`, `IInboxCredentialStore` | `InboxBase`, `SettingsInboxCredentialResolver` or Wappa's `InboxDirectory`; Hosts adapt through `IInboxDirectorySource` only |
| `auto` (as an Inbox routing mode) | `legacy` or `explicit`; no precedence rule selects a credential authority |
| `Owner` (as Wappa runtime language) | A Host-defined Table Cache Scope value; Wappa does not define Owner |
