# ARCHITECTURE.md — Wappa Framework

## What Wappa Is

Wappa is a messaging runtime framework. It receives Platform webhooks, parses them into Universal Models, dispatches events to user-defined handlers, and provides outbound messaging. Messaging work is scoped by Inbox identity. External Webhook Source events are Inbox-independent unless a Host resolver associates one with an Inbox.

WhatsApp has the broad built-in adapter. Instagram has a Unified Login adapter for DMs (text, media, interactive messages, carousels), comments, mentions, message updates and echo/unsupported system events. Telegram, Teams, and Facebook Messenger have no implemented adapters. Platform callback routes remain separate; shared authentication, Directory, dispatch, and HTTP lifecycle infrastructure are reused.

Instagram intake uses `wappa/core/inbound/instagram_routing.py` after exact-body Meta authentication. It validates the whole envelope, proves each event addresses its professional account, resolves explicit-mode Inbox credentials, and splits every entry/messaging event before all-or-nothing runtime admission. `wappa/processors/instagram_processor.py` is pure translation. It never registers accounts or fetches content. The professional account is both the Instagram Platform Account and Inbox; this is not a fabricated WABA or business-portfolio membership.

Recipient-based Messenger methods take an immutable `DirectMessage` target, validated against the bound Inbox before outbound middleware and again by the adapter. An action available on more than one Platform has exactly one Messenger method, which each adapter maps onto its native API ([ADR-0016](docs/adr/0016-one-messenger-method-per-action.md)); unmappable calls reject before I/O, and methods a Platform lacks raise `UnsupportedOperationError`, with `supported_operations` describing implemented adapter operations. Separate responsibilities (media storage through `IMediaLibrary`, WhatsApp Templates through `ITemplateMessaging`) and Platform-only actions (comment replies and controls, content reads) are Focused Capabilities reached with `messenger.capability(kind)`, not Messenger methods. `send_location_request` / `send_contact_request` stay core methods that only WhatsApp implements today. Known gap: `send_reaction` is a missing core method ([backlog draft](docs/backlog/drafts/261105-mid-send-reaction-core-method.md)). The public facade remains whole; no per-family interface split is introduced. Host takeover and durable business idempotency remain host responsibilities.

## Design Patterns

Instagram scope includes planned regular/Live comment intake, public mentions, public/private replies, comment controls and explicit conversation-content/media reads. Wappa provides the Platform operations; Hosts own response, moderation, AI, takeover and workflow policy. Publishing, content calendars, scheduled publication and content/account analytics belong to Hosts or Platform Extensions.

The agreed extension design formalizes Symphonai's existing reuse of current credentials for its own provider clients. A planned narrow supported access capability will replace consumer dependence on the internal resolver; it does not require Wappa to own extension clients. Registered extension fields enter the same authenticated Instagram callback; extension schemas and handlers stay outside the conversation domain. Message edits/deletions use a planned distinct message-update lane rather than delivery statuses. These are target contracts, not implemented additions. See the [PRD](docs/backlog/in_progress/261103-instagram-conversations/references/scope.md), [completed session](docs/sasha/grilling-sessions/261103-instagram-scope-and-extensions.md) and [ADR-0015](docs/adr/0015-conversation-primitives-and-trusted-platform-extensions.md). The [implementation series](docs/backlog/in_progress/261103-instagram-conversations/plan.md) tracks the remaining capability slices, DDD reconciliation, setup and developer skill deliverables; planned contracts are not available merely through that plan.

HTTP composition uses FastAPI 0.162.x. Inspect included routes through `fastapi.routing.iter_route_contexts(app.routes)` so prefixes and inherited metadata describe each inclusion. `app.routes` contains router relationships; its length does not count endpoints. Plugins populate registered router shells with `include_router()` during startup rather than copying route lists.

Public router registration combines the include prefix with the router's own prefix. Auth exclusions for those registrations match complete path segments. The same router can have a public mount and a protected mount.

| Pattern | Where Used | Why |
|---------|-----------|-----|
| **Template Method** | `WappaEventHandler.handle_*()` → `process_*()` | Framework guarantees pre/post-processing (logging, metrics) while host app owns business logic in `process_*()` |
| **Prototype (Clone)** | `WappaEventHandler.with_context()` | Thread-safe per-request handler instances. Base handler is a prototype; each request gets a shallow copy with injected context |
| **Factory** | `MessengerFactory`, `CacheFactory`, `WappaBuilder` | Decouple construction from use. Factories resolve credentials, build platform-specific clients, select cache backends |
| **Builder** | `WappaBuilder` | Assemble complex application configurations step-by-step with plugin composition |
| **Plugin** | `WappaPlugin`, `WappaBuilder.with_*()` | Open/Closed principle — extend framework behavior without modifying core |
| **Pipeline (Middleware)** | `MessengerPipeline` | Composable outbound message middleware (SSE lifecycle, PubSub notification) wrapping the messenger |
| **Strategy** | `IInboxCredentialResolver` (internal), `IIdentityResolver`, `IExternalWebhookContextResolver`, `ICacheFactory` backends | Swap credential authority, identity resolution, external webhook context resolution, and persistence implementations without changing runtime orchestration |
| **Adapter** | `wappa/messaging/whatsapp/`, `wappa/webhooks/whatsapp/` | Translate between platform-specific APIs and Wappa's universal interfaces |
| **Observer** | SSE/PubSub, Expiry keyspace notifications | Decouple event producers from consumers; fan-out without tight coupling |

## Message Flow — Inbound Webhook to Handler

```
Platform (WhatsApp, etc.)
    │
    │ POST /webhook/inboxes/whatsapp
    ▼
┌─────────────────────────────────┐
│  API Layer (routes + controller)│
│                                 │
│  1. Read exact body bytes once  │
│  2. Verify X-Hub-Signature-256  │
│     with META_APP_SECRET (401)  │
│  3. Decode JSON, require object │
│  4. Delegate: routing + runtime │
└────────────────┬────────────────┘
                 │
                 ▼
┌─────────────────────────────────┐
│  WhatsApp Payload Routing       │
│                                 │
│  1. Split every entry/change    │
│  2. InboxRef from phone_number_id│
│     or WABA fan-out via the     │
│     Platform Account Index      │
│  3. Resolve credentials through │
│     IInboxCredentialResolver    │
│  4. Prove Inbox ∈ entry[].id    │
└────────────────┬────────────────┘
                 │
                 ▼
┌─────────────────────────────────┐
│  Inbound Runtime                │
│                                 │
│  1. Call platform processor     │
│  2. Validate payload inbox      │
│  3. Build EVERY Dispatch Context│
│     (DispatchContextBuilder:    │
│     messenger, cache, db)       │
│  4. Only then schedule the batch│
│  5. Open SSE scope + dispatch   │
└────────────────┬────────────────┘
                 │
                 ▼
┌─────────────────────────────────┐
│  Platform Webhook Processor     │
│  (e.g., WhatsAppWebhookProcessor)
│                                 │
│  1. Parse raw payload into      │
│     Universal Webhook Models    │
│     (InboxBase, UserBase,       │
│      MessageBase, etc.)         │
│  2. Classify: message, status,  │
│     error, or system event      │
│  3. Return the Universal Model  │
└────────────────┬────────────────┘
                 │
                 ▼
┌─────────────────────────────────┐
│  WappaEventDispatcher           │
│                                 │
│  Routes to handler.handle_*()   │
│  which calls process_*()        │
│  (Template Method)              │
└────────────────┬────────────────┘
                 │
                 ▼
┌─────────────────────────────────┐
│  Host's WappaEventHandler impl  │
│                                 │
│  process_message(webhook)       │
│  process_status(webhook)        │
│  process_error(webhook)         │
│  process_system_webhook(webhook)│
│                                 │
│  Has access to:                 │
│    self.inbox_id                │
│    self.user_id                 │
│    self.messenger (outbound)    │
│    self.cache_factory (state)   │
│    self.db / self.db_read       │
└─────────────────────────────────┘
```

**Inbound Runtime boundary:** The Inbound Runtime owns the Dispatch Context: `inbox_id`, `user_id`, Messenger, Cache Factory, DB sessions, SSE identity, and cloned `WappaEventHandler`. Platform processors are pure translators and must not mutate ContextVars, build messengers, resolve cache factories, or clone handlers.

**Callback authentication:** The canonical Meta callback is `GET + POST /webhook/inboxes/whatsapp`. GET compares `hub.verify_token` with the Meta Application Configuration's verify token and reads nothing else. POST verifies the exact body bytes against `X-Hub-Signature-256` with `META_APP_SECRET` before JSON parsing, directory reads, payload logging, or scheduling; missing, malformed, and mismatched signatures all answer a generic 401. One Wappa application binds to one Meta App; there is no development bypass.

**Inbox authority:** Identity crossing Platforms is `InboxRef(platform, inbox_id)` and `PlatformAccountRef(platform, platform_account_id)`. `value.metadata.phone_number_id`, or a flat `value.phone_number_id`, maps to `InboxRef.whatsapp(...)`; `entry[].id` maps only to `PlatformAccountRef.whatsapp(...)` and is never an Inbox. A phone-scoped change must prove its active record belongs to that WABA (400 otherwise). A change without a phone number fans out to every validated member of the Platform Account Index; a stale index is repaired from the source once, and a failed repair is 503 with nothing dispatched. Wappa builds every Dispatch Context before scheduling any handler work.

**Credential authority:** `wappa/core/factory/inbox_assembly.py` is the only code that reads `WP_ACCESS_TOKEN`, `WP_PHONE_ID`, `WP_BID`, and `SYSTEM_TOKEN_ENC_KEY`. It selects exactly one `InboxRoutingMode` — `legacy` (settings-backed single Inbox) or `explicit` (Inbox Directory over the Host's `IInboxDirectorySource`) — and rejects mixed configuration. Every runtime component then consumes the resulting `InboxRuntimeConfiguration` (`app.state.inbox_runtime`) through the internal `IInboxCredentialResolver`; none read those variables again.

**Inbox Directory dependency direction:**

```text
Host durable schema
  -> IInboxDirectorySource                 (Host adapter, read-only)
  -> InboxDirectory                        (wappa/domain/inbox/services.py: read-through,
                                            versions, index repair, refresh/deactivate)
  -> InboxDirectoryTable on ITableCache    (wappa/persistence/inbox_directory.py,
                                            context_id = SYSTEM_SCOPE)
  -> CredentialCodec                       (wappa/core/security: Fernet, context-bound)
  -> IInboxCredentialResolver              (internal read port)
  -> DispatchContextBuilder / InboxExecutionContext
  -> WhatsApp client and Messenger construction
```

## External Webhook Source flow

External callbacks do not use messaging Inbox identity as URL routing data. `WebhookPlugin` mounts an ID-less callback by default and may instead add an opaque `{webhook_id}`. The processor authenticates and parses the request before the optional Host `IExternalWebhookContextResolver` runs. That strategy may associate the event with an `InboxRef` and User using authenticated payload, headers, database state, or trusted FastAPI request state.

Wappa completes admission before returning HTTP success. An event without a resolved Inbox receives database factories only. An event with a resolved Inbox receives Messenger, and a resolved User also receives the Inbox-scoped Cache Factory. Only Host handler execution moves to tracked background work.

The API layer receives an Inbox Execution Context and knows nothing about Table Cache names, source queries, encryption keys, or token values. The persistence class never imports Host repositories or WhatsApp clients.

**Outbound HTTP scope:** Inbox-dependent routes depend on `get_inbox_execution_context`, which reads `X-Wappa-Inbox-ID`, falls back to the legacy default only in legacy mode, resolves the active record once, and shares the `InboxExecutionContext` with every dependency in the route. Local-only routes (limits, local validation, root health, docs) never resolve an Inbox and never depend on directory health. The header selects scope; Host authentication and authorization decide permission and run first. `InboxMiddleware` only isolates the ambient logging context per request.

**Failure classes:** `InboxNotFoundError`, `InboxMembershipError`, `InboxDirectoryUnavailableError`, `InboxCredentialIntegrityError`, and `InboxMutationConflictError` are the stable categories. The callback maps them to 400/400/503/503/503; Wappa HTTP operations map unknown to 404 and unavailable to 503; programmatic entry points raise them unchanged. A directory outage during Messenger construction is never an unclassified 500.

## Message Flow — Outbound (Host sends a reply)

```
Host's process_message():
    await self.messenger.send_text("Hello!", recipient=user_id)
        │
        ▼
┌─────────────────────────────────┐
│  MessengerPipeline              │
│  (middleware stack)             │
│                                 │
│  → SSELifecycleMiddleware       │
│  → PubSubNotificationMiddleware │
│  → ... (composable)            │
└────────────────┬────────────────┘
                 │
                 ▼
┌─────────────────────────────────┐
│  WhatsAppMessenger (IMessenger) │
│                                 │
│  Delegates to typed handlers:   │
│  - WhatsAppMediaHandler         │
│  - IInteractiveHandler          │
│  - ITemplateHandler             │
│  - ISpecializedHandler          │
└────────────────┬────────────────┘
                 │
                 ▼
┌─────────────────────────────────┐
│  WhatsAppClient (httpx)         │
│                                 │
│  Sends to Meta Graph API        │
│  phone_number_id = inbox_id     │
└─────────────────────────────────┘
```

## Message Flow — Inbox-scoped Template transport

Embedding hosts that only need Template delivery use a smaller public capability. The capability and the general Messenger share the same internal construction and pipeline; it is not a second delivery implementation.

```
Host Application
    │ OutboundRuntime.from_app(app).templates(inbox_id).send(request)
    ▼
InboxTemplateTransport
    │ validates Delivery Address, category, authentication method,
    │ and selects one endpoint before I/O
    ▼
MessengerFactory → MessengerPipeline.capability(ITemplateMessaging) → WhatsApp adapter → Meta
    │
    ▼
TemplateTransportResult
    accepted | rejected | transport_unavailable | indeterminate
```

The request contains platform-facing values only. The Host Application retains governance, attribution, state, persistence, and durable commit. A result is `accepted` only when Meta returns a platform Message ID. Wappa never performs an automatic cross-endpoint retry.

## HTTP Client Lifecycle

Wappa manages two separate HTTP client pools, both owned by `SessionLifecycle`:

```
┌───────────────────────────────────────────────────────┐
│  SessionLifecycle                                     │
│                                                       │
│  Authenticated Client (get_session)                   │
│  ├── 100 max connections, 20 keepalive                │
│  ├── Bearer token injected by WhatsAppClient          │
│  ├── Used for: Meta Graph API calls                   │
│  └── ⚠️  NEVER used for third-party URLs              │
│                                                       │
│  Media Download Client (get_media_download_client)    │
│  ├── 20 max connections, 5 keepalive                  │
│  ├── No auth headers — credential isolation enforced  │
│  ├── Lazily created on first access                   │
│  └── Used for: public/third-party media downloads     │
│                                                       │
│  Lifecycle: startup → active → drain → close          │
│  Both clients closed during three-phase shutdown      │
└───────────────────────────────────────────────────────┘
```

**Credential isolation rule:** The authenticated client carries Meta/WhatsApp Bearer tokens. The media download client never carries auth headers. These clients must not be consolidated. This prevents accidental credential leakage to third-party hosts when downloading public media URLs for re-upload.

**Three-phase shutdown:**

| Phase | Priority | Action |
|-------|----------|--------|
| Drain mark | 90 | `SessionLifecycle.begin_drain()` + `BackgroundWorkTracker.begin_drain()` — reject new work |
| Background drain | 70 | `BackgroundWorkTracker.drain(timeout=30s)` — await in-flight tasks |
| Resource close | 10 | Stop memory cleanup, close both HTTP clients, clear app state |

## Layer Dependencies

```
   CLI (no runtime coupling)
    
   API Layer
     └── depends on → Core Events, Core Logging, Schemas
   
   Core Events (dispatch)
     └── depends on → Domain Interfaces, Webhooks (universal models)
   
   Webhooks (parsing)
     └── depends on → Shared Schema Primitives, Domain Models
   
   Messaging (outbound)
     └── depends on → Domain Interfaces, Platform SDKs (httpx)
   
   Persistence (cache backends)
     └── depends on → Domain Interfaces
   
   SSE / PubSub
     └── depends on → Core Logging
   
   Expiry
     └── depends on → Messaging, Persistence, Core Logging
   
   Plugins
     └── depends on → Core (any), Domain Interfaces
   
   Resilience (retry + transient-failure classification)
     └── depends on → Core Logging, httpx
   
   Domain Interfaces (pure abstractions)
     └── depends on → nothing
```

**Dependency rule:** Domain Interfaces is the innermost layer. Outer layers depend inward. No layer depends on the API layer except the application entry point.

**Edge ownership:** API route modules only adapt HTTP to Wappa modules; Platform parsing, credential lookup, cache namespace rules, and dispatch policy live behind them. Platform adapters own SDK/client construction, request/response translation, Platform errors, and Platform-specific identity mapping. The WhatsApp `inbox_id == phone_number_id` mapping stays explicit inside the WhatsApp adapter; every other module speaks `inbox_id`.

## Multi-Platform Strategy

Wappa is multi-platform by design. Platform types remain stable while adapter capabilities are registered independently:

1. **Universal Webhook Models** (`wappa/webhooks/core/`): `InboxBase`, `UserBase`, `MessageBase`, `StatusBase`, `ErrorBase`, `SystemBase` — platform-agnostic.
2. **Platform Adapters**: per Platform, an inbound adapter (`wappa/webhooks/<platform>/`, `wappa/processors/<platform>_processor.py`, `wappa/core/inbound/<platform>_routing.py`) that implements `PlatformWebhooks` (`wappa/core/inbound/platform_webhooks.py`: `platform`, `builtin_fields`, `route`, `translate`) and an outbound adapter (`wappa/messaging/<platform>/`) that implements `IMessenger`. WhatsApp and Instagram are installed.
3. **Shared Schema Primitives** (`wappa/schemas/core/types.py`, `wappa/schemas/core/recipient.py`): Cross-cutting enums and outbound recipient normalization shared by inbound, outbound, API, and runtime modules. Inbound webhook schemas do not live here.
4. **`PlatformType` is vocabulary; `PLATFORMS` is installation.** `wappa/platforms.py` is the composition root: `PLATFORMS: Mapping[PlatformType, PlatformEntry]` (each entry holds the `PlatformWebhooks` adapter, the Messenger builder and a display name), `BUILTIN_FIELDS` (each Platform's reserved webhook fields, which seed `FieldHandlerRegistry`) and `build_platforms(field_registry)`, which `WappaBuilder.build()` calls once per app and stores on `app.state.platforms`. The webhook controller (GET and POST), `/webhook/platforms`, the status route, `WappaCorePlugin`, `RoutePlatform` and `MessengerFactory` read it; a `PlatformType` member without an entry (Telegram, Teams) answers 400 on HTTP and raises `ValueError` in code, never falls through to WhatsApp. Platform imports and branches are legitimate only there and in adapter folders.
5. **Inbox Directory** (`wappa/domain/inbox/`): Wappa's canonical, Platform-discriminated credential records and the read-through directory that resolves them. Hosts supply only an `IInboxDirectorySource`; Wappa owns encryption, caching, versions, indexes, and Messenger eviction. The `InboxCredentialRecord` union grows one active/inactive pair per Platform, and `RECORD_TYPES` beside it maps each Platform to that pair so `InboxCredentialService` never branches on Platform.
6. **Adding a new platform** touches:
   - Its adapter folders: `wappa/webhooks/<platform>/`, `wappa/processors/<platform>_processor.py` (plus `wappa/core/inbound/<platform>_routing.py` or routing folded in), `wappa/messaging/<platform>/`, optional capability adapters its Messenger registers, and optionally a connector implementing `IInboxConnector` (as `wappa/connections/instagram.py`).
   - The composition root: one `PlatformEntry` in `build_platforms` and its `builtin_fields` in `BUILTIN_FIELDS` (`wappa/platforms.py`).
   - Vocabulary: one `PlatformType` member (`wappa/schemas/core/types.py`) and one active/inactive record pair plus its `RECORD_TYPES` entry (`wappa/domain/inbox/credentials.py`). `InboxRef.cache_namespace` is already Platform-qualified (`<platform>__<inbox_id>`), so it needs no per-Platform encoding.
   - A non-Meta Platform additionally adds `authenticate` to `PlatformWebhooks` and its own callback authenticator; today both Platforms are Meta callbacks sharing one App Secret (ADR-0010).
   - Instagram is the worked example: `wappa/webhooks/instagram/models.py`, `wappa/processors/instagram_processor.py`, `wappa/core/inbound/instagram_routing.py`, `wappa/messaging/instagram/`, `wappa/connections/instagram.py`.

Event lanes beyond message/status/error/system (message updates, comments, mentions) have optional `WappaEventHandler` hooks; a Platform without those events simply never emits them. User choices are not a lane: WhatsApp button/list replies and Instagram quick replies and postbacks all arrive as `InboundMessageWebhook` with `get_interactive_selection()`.

### Instagram adapter (implemented)

| Module | Responsibility |
| --- | --- |
| `wappa/webhooks/instagram/models.py` | Pure envelope (`messaging[]` + `changes[]`) and typed message-family models. |
| `wappa/processors/instagram_processor.py` | Pure lane translation (see the table in its docstring); extension fields via the Platform-qualified `FieldHandlerRegistry`. No I/O. |
| `wappa/core/inbound/instagram_routing.py` | Signature-first, whole-batch admission: resolve every entry's Inbox before returning one delivery per event/change. Authors never select an Inbox. |
| `wappa/messaging/instagram/graph.py` | Inbox-bound Graph HTTP, outcome classification (accepted/rejected/indeterminate), credential-free error text. |
| `wappa/messaging/instagram/messenger.py` | `IMessenger` facade: maps the shared contract (`mark_as_read`, button/list/CTA messages, carousels, captions as follow-up text, location/contact as text, sticker as image) onto Instagram APIs, PrivateReply, local limit checks, capability lookup. |
| `wappa/messaging/instagram/media_library.py` | `IMediaLibrary`: reusable `message_attachments` upload (attachment_id) and CDN download through the attachment reader. |
| `wappa/messaging/instagram/content.py` | `ICommentControls` (including public `reply_comment`) and `IConversationContentReader` (Focused Capabilities). |
| `wappa/messaging/instagram/media.py` | Media rules and the credential-free, host-restricted `InstagramAttachmentReader`, private to `InstagramMediaLibrary.download`. |
| `wappa/connections/contract.py` | `IInboxConnector` (ADR-0017): begin / complete / activate / disconnect, grant, readiness and activation results. |
| `wappa/connections/meta_login.py` | Meta Business Login core shared by both Meta connectors: state binding, code exchange, `debug_token`, `signed_request`. |
| `wappa/connections/instagram.py` | `InstagramConnector` (Unified Login discovery, field subscriptions); the Host owns routes, intent storage and commit. |
| `wappa/connections/whatsapp.py` | `WhatsAppConnector` (Embedded Signup: WABA + phone-number discovery, WABA `subscribed_apps`). |
| `wappa/domain/inbox/access.py` | `InboxCredentialAccess`: the supported trusted-adapter credential seam (ADR-0015). |

Host policy (which comments to answer/hide, flows, AI, takeover) stays in the Host's handler and Scores; see `instagram_conversations_example` in the sibling `wappa_examples` repository.

## Deeper Architecture Docs

Each bounded context has its own `ARCHITECTURE.md` for internal details:

| Context | Doc | Covers |
|---------|-----|--------|
| Webhooks | [`wappa/webhooks/ARCHITECTURE.md`](./wappa/webhooks/ARCHITECTURE.md) | Payload parsing, universal model construction, platform processor interface |
| Messaging | [`wappa/messaging/ARCHITECTURE.md`](./wappa/messaging/ARCHITECTURE.md) | Handler composition, pipeline middleware, client construction |
| API | [`wappa/api/ARCHITECTURE.md`](./wappa/api/ARCHITECTURE.md) | Router tree, Inbox selection, capability gates, request models |
| Persistence | [`wappa/persistence/ARCHITECTURE.md`](./wappa/persistence/ARCHITECTURE.md) | Backend selection, key namespace rules, cache interface contracts |
| SSE/PubSub | [`wappa/core/sse/ARCHITECTURE.md`](./wappa/core/sse/ARCHITECTURE.md) | Subscription model, fan-out, envelope structure |
| Expiry | [`wappa/core/expiry/ARCHITECTURE.md`](./wappa/core/expiry/ARCHITECTURE.md) | Key format, keyspace notification flow, handler registration |
| Plugins | [`wappa/core/plugins/ARCHITECTURE.md`](./wappa/core/plugins/ARCHITECTURE.md) | Plugin lifecycle, hook points, built-in plugins |
| External Webhooks | [`wappa/core/external_webhooks/ARCHITECTURE.md`](./wappa/core/external_webhooks/ARCHITECTURE.md) | Admission, Host context strategy, signature verification, event registry |
| CLI | [`wappa/cli/ARCHITECTURE.md`](./wappa/cli/ARCHITECTURE.md) | Commands, templates, example generation |

## Key Architectural Decisions

See [`docs/adr/`](./docs/adr/) for recorded decisions. Notable:

- [ADR-0001: inbox_id as runtime scope](./docs/adr/0001-inbox-id-runtime-scope.md) — replaces tenant_id
- [ADR-0005: Runtime primitives for host platforms](./docs/adr/0005-runtime-primitives-for-host-platforms.md) — signature verification, external event routing, versioned caches, request IDs, retry classification
- [ADR-0007: Embedded outbound route control](./docs/adr/0007-embedded-outbound-route-control.md) — an embedding host omits Wappa's raw outbound mutation routes without losing media, read, or service routes
- [ADR-0008: Redis hash boolean encoding](./docs/adr/0008-redis-hash-boolean-encoding.md) — `"1"`/`"0"` is a compatibility contract, not an implementation detail
- [ADR-0009: Route capability groups](./docs/adr/0009-route-capability-groups.md) — "mutation" means every route that sends, deletes, or rewrites state, not only sends
- [ADR-0010: Authenticated, payload-routed WhatsApp webhook](./docs/adr/0010-payload-routed-whatsapp-webhook.md) — one callback, raw-body HMAC, qualified routing, WABA membership, all-or-nothing admission
- [ADR-0011: Encrypted Inbox Directory](./docs/adr/0011-encrypted-inbox-directory.md) — Wappa-owned directory on Table Cache under the System Scope, Host-owned schema through one source, encrypted records, TTL and version rules
- [ADR-0012: Inbox-independent external webhooks](./docs/adr/0012-inbox-independent-external-webhooks.md) — optional Webhook ID, Host context strategy, and admission before acknowledgment
- [ADR-0016: One Messenger method per action](./docs/adr/0016-one-messenger-method-per-action.md) — adapters map shared actions onto native APIs; Platform-only actions are capabilities

Shared event logging reads Universal Model identity rather than assuming WA fields are present: system records include Platform/Inbox and an available User; status records include native message/recipient references. Consumer examples may add send-result correlation without calling acceptance delivery or dumping raw provider payloads. Missing optional identity is omitted from log text.
