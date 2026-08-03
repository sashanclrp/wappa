# Messaging Context — Architecture

## Responsibilities

- Implement `IMessenger` for the WhatsApp platform.
- Own the `WhatsAppClient` HTTP adapter: token auth, JSON and multipart POST, GET, DELETE, and streaming GET against the Meta Graph API.
- Own media lifecycle: upload (path / bytes / stream / URL re-upload), download (to disk, temp file, or bytes), stream, delete, and MIME/size validation.
- Own outbound message construction for all WhatsApp message types: text, media,
  interactive, templates, contacts, locations, and contact-information requests.
- Own recipient normalization (phone → E.164, BSUID detection) via `schemas.core.recipient`.
- Own read-only template metadata queries against the WABA-level Graph API.
- Own the public `OutboundRuntime` and Inbox-scoped `InboxTemplateTransport`.
  This deep module resolves credentials and active clients, constructs the
  platform Messenger and Messenger Pipeline, executes Template transport, and
  normalizes platform evidence without exposing its composition.
- Keep `Messenger` / `IMessenger` as the general outbound seam. Template-only
  Host Applications use the smaller public Template transport capability.
  Internal WhatsApp handlers may stay grouped by message family, but public
  `TextMessenger`, `MediaMessenger`, or similar seams are deferred until there is
  concrete pressure from multiple platform adapters or tests.

## Not Owned Here

- Webhook parsing and inbound event routing — owned by `core/events`.
- Cache scoping, SSE, or runtime state — owned by `persistence`.
- Credential provisioning and `inbox_id` resolution — owned by `core/config` and API route adapters.
- Business logic, workflow decisions, or event handler behaviour — owned by host applications.
- Template authorization, attribution, idempotency, Campaigns, Conversation
  lifecycle, Reply State, Agent context, and Message persistence — owned by Host
  Applications and forbidden from the Template transport request.
- `IMediaHandler` and `IMessenger` abstract contracts — defined in `domain/interfaces`.

## Module Structure

```
messaging/
  template_transport.py         # Public OutboundRuntime + Inbox Template capability
  whatsapp/
    client/
      whatsapp_client.py          # HTTP session wrapper; WhatsAppUrlBuilder, WhatsAppManagementUrlBuilder
    handlers/
      whatsapp_media_handler.py   # IMediaHandler impl: upload/download/stream/delete
      whatsapp_interactive_handler.py  # Menus, CTA URLs, contact-info requests
      whatsapp_template_handler.py     # Text, media-header, location-header templates
      whatsapp_specialized_handler.py  # Contact cards, locations, location requests
    messenger/
      whatsapp_messenger.py       # IMessenger impl; composes all four handlers
    models/
      basic_models.py             # MessageResult
      media_models.py             # MediaType enum + supported MIME types
      interactive_models.py       # ReplyButton, ListSection, InteractiveHeader
      template_models.py          # WhatsAppTemplateType, WhatsAppTemplateMediaType, TemplateParameter
      specialized_models.py       # ContactCard
      template_info_models.py     # Request/response models for template read operations
    services/
      whatsapp_template_info_service.py  # Read-only WABA template listing and lookup
    utils/
      error_helpers.py            # handle_whatsapp_error — uniform error → MessageResult
```

## Key Classes and Roles

| Class | Role |
|---|---|
| `IMessenger` (`domain/interfaces`) | Abstract outbound messaging contract all platforms must implement. |
| `WhatsAppMessenger` | Facade implementing `IMessenger`. Delegates each message family to the appropriate handler; owns media-source resolution logic. |
| `WhatsAppClient` | Single httpx session per inbox. Holds `phone_number_id` (= `inbox_id`). Used by all handlers and the template info service. |
| `WhatsAppMediaHandler` | Implements `IMediaHandler`. Handles all media upload paths and download paths; enforces WhatsApp MIME and size limits. |
| `WhatsAppInteractiveHandler` | Builds and validates interactive payloads; enforces WhatsApp character-count and structural limits inline before dispatch. |
| `WhatsAppTemplateHandler` | Builds template component trees; resolves marketing vs. standard send URL via `_resolve_template_send_url`. |
| `WhatsAppSpecializedHandler` | Sends contact cards, location pins, and location-request messages. |
| `WhatsAppTemplateInfoService` | Stateless read service for WABA-scoped template metadata. Uses `WhatsAppManagementUrlBuilder`. |
| `MessageResult` | Uniform result VO returned by every send method. |
| `OutboundRuntime` | Deep public factory over credentials, sessions, Messenger construction, and Messenger Pipeline composition. |
| `InboxTemplateTransport` | Small capability bound to one Inbox; accepts provider-facing typed requests and returns normalized transport evidence. |
| `TemplateTransportResult` | Accepted/rejected/unavailable/indeterminate evidence. Acceptance requires a platform Message ID and does not imply delivery or local commit. |

## Design Patterns

- **Composition over inheritance**: `WhatsAppMessenger` holds handler instances injected at construction; it does not extend them.
- **Dependency injection**: `WhatsAppClient` and `httpx.AsyncClient` are injected, enabling per-inbox isolation and testability.
- **Value objects for URLs**: `WhatsAppUrlBuilder` and `WhatsAppManagementUrlBuilder` are stateless URL factories, not services.
- **Strategy pattern for media source**: `_resolve_media_object` in `WhatsAppMessenger` selects URL-link, media-ID, or upload path based on the shape of the input.
- **Result object**: All send methods return `MessageResult` rather than raising; error details are captured in the result.

## Data Flow — Outbound Message

```
Host application
  → WhatsAppMessenger.send_*(recipient, ...)
      → recipient normalized via schemas.core.recipient.apply_recipient_to_payload
      → factory builds API payload dict
      → handler validates constraints (character limits, required fields)
      → WhatsAppClient.post_request(payload)
          → httpx POST to Graph API
      → MessageResult.from_response_payload(response)
  ← MessageResult returned to host application
```

## Data Flow — Template Transport

```
Host Application use case
  → OutboundRuntime.from_app(app).templates(inbox_id)
  → InboxTemplateTransport.send(typed provider-facing request)
      → Inbox credential resolution + active SessionLifecycle client
      → WhatsApp Messenger construction + registered Messenger Pipeline
      → WhatsAppTemplateHandler endpoint/payload/media work
      → normalized TemplateTransportResult
  ← Host Application applies its own durability and lifecycle policy
```

Transport execution and Host Application commit are intentionally separate.
An `indeterminate` result must not be treated as safe to retry automatically.

## Data Flow — Media Upload (file path)

```
WhatsAppMessenger._resolve_media_object(path, ...)
  → WhatsAppMediaHandler.upload_media(path)
      → MIME detection + size validation
      → WhatsAppClient.post_request(multipart form, media endpoint)
  ← MediaUploadResult with media_id
→ payload assembled with {"id": media_id}
→ WhatsAppClient.post_request(message payload)
```

## Media Download — Credential Isolation

`WhatsAppMediaHandler` handles two categories of HTTP traffic with strictly separate clients:

| Operation | Client | Auth | Pool |
|-----------|--------|------|------|
| `get_media_info()`, `download_media()`, `stream_media()` | Authenticated `WhatsAppClient` | Bearer token | SessionLifecycle main pool (100 conn) |
| `upload_media_from_url()` — download from public URL | Unauthenticated pooled client | None | SessionLifecycle media pool (20 conn) |

The media download client is injected via `media_download_client` and remains
separate from the authenticated platform client. The pooled client is wired
through both construction paths:

1. **API routes**: `get_whatsapp_media_handler()` acquires the media client from
   `app.state.session_lifecycle`
2. **Inbound dispatch**: `MessengerFactory` receives `media_download_client_provider` via `InboundRuntimeDependencies`

**Invariant:** The media download client must never carry `Authorization` headers. Tests enforce this.

## inbox_id Mapping

`WhatsAppClient.phone_number_id` is the `inbox_id` for the WhatsApp platform. It flows into every `MessageResult` and `MediaUploadResult` as `inbox_id`. The mapping is explicit: `inbox_id == phone_number_id` for all WhatsApp operations.

## Outbound Seam Decision

`IMessenger` remains Wappa's general outbound interface. The Template transport
is the first deliberately smaller capability because a real Host Application
needed to depend on provider sending without receiving the rest of Messenger or
constructing its internal pipeline.

**Why the seam stays whole:**

- No second real platform adapter (Telegram, Instagram) exists yet to create pressure.
- Tests do not repeatedly need smaller Messenger fakes.
- Other message families have not yet demonstrated the same smaller-capability
  requirement.
- Message families (text, media, interactive, template, specialized) share the same `inbox_id`, `MessageResult`, and error-handling semantics — the interface is wide but cohesive.

**Internal composition is allowed:**

WhatsApp (and future adapters) may organize handler classes by message family internally. This is implementation structure, not public contract. The four handlers (`WhatsAppMediaHandler`, `WhatsAppInteractiveHandler`, `WhatsAppTemplateHandler`, `WhatsAppSpecializedHandler`) stay as internal composition detail.

**Split threshold — revisit only when:**

1. A second real platform adapter cannot implement `IMessenger` coherently.
2. Tests repeatedly need smaller Messenger fakes because the wide interface creates concrete pain.
3. Host applications need to depend on a smaller outbound capability set for security or lifecycle reasons.
4. Message families diverge enough that keeping one interface hides real invariants.

**If the threshold is met:**

Split with a clean breaking change. No compatibility aliases, no deprecation shims, no adapter layers wrapping old → new.
