# Messaging Context — Architecture

## Responsibilities

`IMessenger` has one method per conversation action on every Platform; each adapter maps it onto its native API ([ADR-0025](../../docs/adr/0025-messenger-contract.md)). Besides sending and acknowledging, it has one read: `resolve_platform_user_profile(user)` returns a `PlatformUserProfile` (`wappa/domain/user_profile.py`) with every fact the Platform provides about a User. WhatsApp maps the webhook evidence with no I/O; Instagram adds a Graph `GET /{igsid}?fields=name,username,profile_pic` with the Inbox token and, on failure, returns the evidence with the `ReadOutcome` instead of raising. Wappa never calls it during intake or dispatch, and the pipeline forwards it without middleware; the Host merges and persists the result (ADR-0025 rule 10). Separate responsibilities are Focused Capabilities, registered in each adapter's `_capabilities` and looked up internally with `messenger.capability(kind)`: `IMediaLibrary` (WhatsApp and Instagram upload/download), `ITemplateMessaging` (WhatsApp Templates), `IUserDataRequests` (WhatsApp location and phone-number requests), and the Instagram-only `ICommentControls`, `IConversationContentReader` and `IConversationHistoryReader`. Hosts never look one up (ADR-0025 rule 12): a shared capability is an `IMessenger` attribute (`messenger.media`), and a Platform-only one is ready on that Platform's Platform Messenger, `WhatsAppMessenger` (`wappa/messaging/whatsapp/platform_messenger.py`: `templates`, `send_location_request`, `send_contact_request`) or `InstagramMessenger` (`wappa/messaging/instagram/platform_messenger.py`: `comments`, `content`, `history`). Both extend `PlatformMessenger` (`wappa/core/messaging/platform_messenger.py`), which receives the dispatch's pipeline-wrapped Messenger and forwards every `IMessenger` member to it, so middleware runs and no second Messenger is built; each `PlatformEntry.build_platform_messenger` builds one and `WappaEventHandler.with_context` binds it as `self.whatsapp` / `self.instagram`. The concrete adapters are `WhatsAppMessengerAdapter` and `InstagramMessengerAdapter`. Their existence does not put consumer moderation policy, AI or publishing/analytics inside messaging. Extra provider clients remain extension-owned and use `InboxCredentialAccess`.

- Implement `IMessenger` for WhatsApp and Instagram, and `IMediaLibrary` for both (`wappa/messaging/whatsapp/media_library.py`, `wappa/messaging/instagram/media_library.py`).
- Own the Meta Graph transport, `MetaGraphClient` (`wappa/messaging/meta/graph.py`, [ADR-0029](../../docs/adr/0029-meta-graph-transport.md)): every WhatsApp and Instagram API call, with Bearer auth, outcome classification, Meta error logging and the rate-limit governor. The Platform clients on top of it, `WhatsAppClient` (URL shapes, multipart form) and `InstagramClient` (paths, error wording), never build an HTTP request themselves; media bytes stream through `MetaGraphClient.stream`.
- Own media lifecycle: upload (path / bytes / stream / URL re-upload), download (to disk, temp file, or bytes), stream, delete, and MIME/size validation.
- Own outbound message construction for all WhatsApp message types: text, media,
  interactive, templates, contacts, locations, and contact-information requests.
- Own recipient normalization (phone → E.164, BSUID detection) via `schemas.core.recipient`.
- Own outbound payload classification: one pure function that names the
  transport family of any validated outbound schema, so route and service
  branches do not each re-derive it. Classification reads transport shape only.
- Own read-only template metadata queries against the WABA-level Graph API.
- Own the public `OutboundRuntime` and Inbox-scoped `InboxTemplateTransport`.
  This deep module resolves credentials and active clients, constructs the
  platform Messenger and Messenger Pipeline, executes Template transport, and
  normalizes platform evidence without exposing its composition.
- Keep `Messenger` / `IMessenger` as the general outbound seam for conversation messages. WhatsApp Templates are the `ITemplateMessaging` capability (`WhatsAppMessengerAdapter` implements it; `MessengerPipeline.capability(ITemplateMessaging)` wraps it so message middleware still runs under the `send_*_template` method names). Hosts reach it as `self.whatsapp.templates`. Template-only Host Applications use the smaller public Template transport capability.
  Internal WhatsApp handlers may stay grouped by message family, but public
  `TextMessenger`, `MediaMessenger`, or similar seams are deferred until there is
  concrete pressure from multiple platform adapters or tests.

## Not Owned Here

- Webhook parsing — owned by `wappa/webhooks/` and `wappa/processors/`; inbound event routing — owned by `wappa/core/events/`.
- Cache scoping, SSE, or runtime state — owned by `persistence`.
- Credential provisioning and Inbox resolution — owned by `wappa.domain.inbox.services.InboxDirectory` behind the internal `IInboxCredentialResolver` port (legacy settings adapter in legacy mode, Inbox Directory in explicit mode). Messaging receives already-resolved credentials; it never reads `WP_*` settings or the directory itself.
- Business logic, workflow decisions, or event handler behaviour — owned by host applications.
- Template authorization, attribution, idempotency, Campaigns, Conversation
  lifecycle, Reply State, Agent context, and Message persistence — owned by Host
  Applications and forbidden from the Template transport request.
- Whether a classified send is *permitted*. `classify_outbound_payload` names
  transport shape; admission is a Host Application decision.
- `IMessenger` and `IMediaLibrary` abstract contracts — defined in `wappa/domain/interfaces/`. `IMediaLibrary` is the only media interface.

## Module Structure

```
messaging/
  classification.py             # Pure outbound payload -> transport family classifier
  outbound_runtime.py           # Public OutboundRuntime: the outbound Messenger factory for every Platform
  template_transport.py         # Inbox Template capability (InboxTemplateTransport) and its request/result values
  meta/
    graph.py                    # MetaGraphClient + graph_request: every Meta API call, outcomes, error parsing/logging, rate limits (ADR-0029)
  instagram/
    platform_messenger.py       # InstagramMessenger: the Host-facing Platform Messenger (self.instagram)
    messenger.py                # InstagramMessengerAdapter: IMessenger impl, _OPERATIONS, capability registration
    client.py                   # InstagramClient: Instagram paths + Messenger-family error wording over MetaGraphClient
    media.py                    # Instagram media rules + credential-free InstagramAttachmentReader (private)
    media_library.py            # IMediaLibrary: message_attachments upload (file or bytes), CDN download
    content.py                  # ICommentControls + IConversationContentReader
    history.py                  # IConversationHistoryReader (conversation message reads)
  whatsapp/
    platform_messenger.py       # WhatsAppMessenger: the Host-facing Platform Messenger (self.whatsapp)
    media_library.py            # IMediaLibrary over the Cloud API Media endpoints (upload, download, info, delete)
    client/
      whatsapp_client.py          # WhatsAppClient over MetaGraphClient (raises MetaGraphError/RateLimitedError); WhatsAppUrlBuilder, WhatsAppManagementUrlBuilder
    handlers/
      whatsapp_media_handler.py   # WhatsApp Media API: upload/download/stream/delete
      whatsapp_interactive_handler.py  # Menus, CTA URLs, contact-info requests
      whatsapp_template_handler.py     # Text, media-header, location-header templates
      whatsapp_specialized_handler.py  # Contact cards, locations, location requests
    messenger/
      whatsapp_messenger.py       # WhatsAppMessengerAdapter: IMessenger + ITemplateMessaging + IUserDataRequests impl; composes all four handlers
    models/
      basic_models.py             # WhatsAppAPIResponse wire models; message_result_from_* builders
      media_models.py             # MediaType enum, WhatsApp MIME types and size caps, MediaUploadRequest
      template_models.py          # WhatsAppTemplateType, WhatsAppTemplateMediaType, TemplateParameter, TemplateStateConfig
      specialized_models.py       # BusinessContact, PersonalContact, validation results (WhatsApp extension)
      template_info_models.py     # Request/response models for template read operations
    services/
      whatsapp_template_info_service.py  # Read-only WABA template listing and lookup
      template_state_service.py   # TemplateStateService: Template-triggered User state
    utils/
      error_helpers.py            # handle_whatsapp_error — uniform error → MessageResult
```

Outside this folder but on every send path: the Messenger Pipeline (`MessengerPipeline`, middleware chain, `_PipelineTemplates`) lives in `wappa/core/messaging/pipeline.py`; the `PlatformMessenger` base every Platform Messenger extends (forwarding the whole `IMessenger` contract to the dispatch's Messenger) lives in `wappa/core/messaging/platform_messenger.py`, and each Platform's `PlatformEntry.build_platform_messenger` builds it; `MessengerFactory` (per-Inbox Messenger cache) lives in `wappa/domain/factories/messenger_factory.py` and builds through each Platform's `PlatformEntry.build_messenger` in `wappa/platforms.py`; shared media rendition selection lives in `wappa/domain/media_renditions.py`; the Platform-neutral interactive values (`ReplyButton`, `InteractiveHeader`, `MediaRef`, `ListSection`, `ListRow`, `MessageCard`), their shared limits (the minimum across Platforms, enforced at construction and by `check_button_message` / `check_list_message` / `check_cta_message` / `check_carousel`, which each adapter calls before I/O), the free-form limits `TEXT_MAX` / `CAPTION_MAX` (WhatsApp's, checked by `check_text` / `check_caption` in every adapter before I/O) and `ContactCard` live in `wappa/domain/interactive.py` and `wappa/domain/contacts.py`, and the neutral `MessageResult` in `wappa/domain/results.py`; the neutral HTTP send request models live in `wappa/schemas/requests/`. No `IMessenger` signature imports a WhatsApp type.

## Changing a Messenger method

One action touches this chain, in order. Each hop is a real edit or a deliberate "no change"; skipping one is how a method drifts between Platforms.

1. `wappa/domain/interfaces/messaging_interface.py`: the `IMessenger` signature and docstring. Optional operations default to raising `UnsupportedOperationError`.
2. Platform adapters: `wappa/messaging/whatsapp/messenger/whatsapp_messenger.py` and `wappa/messaging/instagram/messenger.py`. Update each adapter's `supported_operations` (Instagram's `_OPERATIONS` set) when a Platform gains or loses the operation.
3. Media rules, for media actions: `wappa/domain/media_renditions.py` (`pick_rendition`, which rendition each Platform accepts), the WhatsApp suffix sets (`WHATSAPP_STICKER_SUFFIXES` and siblings) at the bottom of `wappa/messaging/whatsapp/messenger/whatsapp_messenger.py`, and `wappa/messaging/instagram/media.py` (Instagram formats and size limits).
4. WhatsApp payload builders: `wappa/messaging/whatsapp/payload_builders.py` (`WhatsAppMessagePayloadBuilder` for text, read status and text limits; `WhatsAppMediaPayloadBuilder` for media payloads and media limits), private to the adapter. Interactive, template and specialized payloads are built in the handlers under `wappa/messaging/whatsapp/handlers/`.
5. `wappa/core/messaging/pipeline.py` and `wappa/core/messaging/platform_messenger.py`: the matching `MessengerPipeline` method and the `PlatformMessenger` forwarder, so middleware sees the call (reads such as `mark_as_read` and `resolve_platform_user_profile` forward to the raw Messenger without middleware). Template methods live on `_PipelineTemplates` and the user-data requests on `_PipelineUserDataRequests` in the same file.
6. HTTP API: the request model (a `DeliveryRequest` subclass from `wappa/schemas/core/recipient.py`, kept in the neutral `wappa/schemas/requests/`), the shared route under `wappa/api/routes/` (or `wappa/api/routes/conversations.py`), and `classify_outbound_payload` in `wappa/messaging/classification.py` when the request model is new. See `wappa/api/ARCHITECTURE.md`.
7. Tests: `tests/test_one_method_per_action.py` (both adapters, unsupported paths), `tests/test_messenger_parity.py` (pipeline, Platform Messenger and adapter signatures, forwarded arguments, `supported_operations` against overridden methods; it fails until steps 1, 2 and 5 agree), `tests/test_messenger_parameter_reach.py` (one neutral value set through both adapters: every parameter reaches the wire or is listed as ignored and documented; every multi-message Instagram emulation returns one result with `wappa_parts`), `tests/test_capability_map.py` (each adapter's `_capabilities` equal the ADR-0025 contract map), `tests/test_messenger_pipeline.py` (pipeline delegation), `tests/test_platform_messaging_api.py` (route, 501/400/failed-result mapping).
8. `docs/public-contract.md` ("Messenger operations" and "Messenger") and `CHANGELOG.md`, listing every break.

## Key Classes and Roles

| Class | Role |
|---|---|
| `IMessenger` (`wappa/domain/interfaces/messaging_interface.py`) | Abstract outbound messaging contract all platforms must implement. |
| `PlatformMessenger` (`wappa/core/messaging/platform_messenger.py`) | Base of the Host-facing Platform Messengers: receives the dispatch's pipeline-wrapped Messenger and forwards every `IMessenger` member to it. |
| `WhatsAppMessenger` / `InstagramMessenger` | The Platform Messengers bound as `self.whatsapp` / `self.instagram`: the dispatch's Messenger plus `templates`, `send_location_request`, `send_contact_request` (WhatsApp) or `comments`, `content`, `history` (Instagram). |
| `WhatsAppMessengerAdapter` | Facade implementing `IMessenger`. Delegates each message family to the appropriate handler; owns media-source resolution logic. |
| `MetaGraphClient` | Every Meta API call for one Inbox (both Platforms): `request` returns a classified `GraphResponse`, `call` returns the body or raises `MetaGraphError` / `RateLimitedError`. |
| `WhatsAppClient` | One phone number's Cloud API calls over `MetaGraphClient` (`.graph`). Holds `phone_number_id` (= `inbox_id`). Used by all handlers and the template info service. |
| `InstagramClient` | One Instagram account's Graph calls over `MetaGraphClient` (`.graph`): `messages_path`, `attachments_path`, Instagram error wording. |
| `WhatsAppMediaHandler` | Concrete WhatsApp Media API client (no ABC) behind `WhatsAppMediaLibrary` (upload, download, info, delete), also reached as `WhatsAppMessengerAdapter.media_handler` for WhatsApp-only extras (URL upload, tempfile, stream, limits). Enforces WhatsApp MIME and size limits. |
| `WhatsAppInteractiveHandler` | Builds interactive payloads; `wa_header` and `wa_media_object` map the neutral `InteractiveHeader` and `MediaRef` 1:1 (`id` before `link`). The shared limits are checked earlier by the neutral values and `check_*` functions. |
| `WhatsAppTemplateHandler` | Builds template component trees; resolves marketing vs. standard send URL via `_resolve_template_send_url`. |
| `WhatsAppSpecializedHandler` | Sends contact cards, location pins, and location-request messages. |
| `WhatsAppTemplateInfoService` | Stateless read service for WABA-scoped template metadata. Uses `WhatsAppManagementUrlBuilder`. |
| `MessageResult` | Uniform result VO returned by every send method. |
| `OutboundClassification` | Transport family (+ variant) of one validated outbound payload. Its `message_type` is the label Wappa reports in outbound API events, which is why route modules no longer restate it. |
| `OutboundRuntime` | Deep public factory over credentials, sessions, Messenger construction, and Messenger Pipeline composition. |
| `InboxTemplateTransport` | Small capability bound to one Inbox; accepts platform-facing typed requests and returns normalized transport evidence. |
| `TemplateTransportResult` | Accepted/rejected/unavailable/indeterminate evidence. Acceptance requires a platform Message ID and does not imply delivery or local commit. |

`MessengerFactory` may retain at most 128 recently used Messenger graphs per
factory. The shared HTTP session owns connection reuse; the bounded cache is
only a construction optimization and is evicted on credential refresh or
deactivation. It never becomes a second credential-lifetime authority.

## Design Patterns

- **Composition over inheritance**: `WhatsAppMessengerAdapter` holds handler instances injected at construction; it does not extend them.
- **Dependency injection**: `WhatsAppClient` and `httpx.AsyncClient` are injected, enabling per-inbox isolation and testability.
- **Value objects for URLs**: `WhatsAppUrlBuilder` and `WhatsAppManagementUrlBuilder` are stateless URL factories, not services.
- **Strategy pattern for media source**: `_resolve_media_object` in `WhatsAppMessengerAdapter` selects URL-link, media-ID, or upload path based on the shape of the input.
- **Result object**: All send methods return `MessageResult` rather than raising; error details are captured in the result.

## Data Flow — Outbound Message

```
Host application
  → WhatsAppMessengerAdapter.send_*(recipient, ...)
      → recipient normalized via schemas.core.recipient.apply_recipient_to_payload
      → factory builds API payload dict
      → handler validates constraints (character limits, required fields)
      → WhatsAppClient.post_request(payload)
          → MetaGraphClient.call (ADR-0029): RateLimitGovernor (pace, honour blocks,
            retry short limits) → graph_request (httpx POST, outcome classification)
          ← body, or MetaGraphError / RateLimitedError → handle_whatsapp_error → result
      → message_result_from_payload(response)  # neutral wappa.domain.results.MessageResult
  ← MessageResult returned to host application
```

## Data Flow — Template Transport

```
Host Application use case
  → OutboundRuntime.from_app(app).templates(inbox_ref)
  → InboxTemplateTransport.send(typed platform-facing request)
      → OutboundRuntime.messenger(inbox_ref): credential resolution, active
        SessionLifecycle client, Platform Messenger + registered Messenger Pipeline
      → capability(ITemplateMessaging), else REJECTED capability_unsupported before I/O
      → WhatsAppTemplateHandler endpoint/payload/media work
      → normalized TemplateTransportResult
  ← Host Application applies its own durability and lifecycle policy
```

Transport execution and Host Application commit are intentionally separate.
An `indeterminate` result must not be treated as safe to retry automatically.

`MessageResult` normalizes outbound phone evidence at model validation, for
both factories and direct construction. `recipient_phone` becomes `None` when
its value matches the complete numeric suffix of a valid regular BSUID, Parent
BSUID, or BSUID-valued resolved `recipient` on that result. Comparison tolerates
outer whitespace and a leading `+` on the phone; alphanumeric suffixes are never
stripped into digits. Distinct phones retain their original value, and a phone
without corroborating BSUID evidence keeps its existing behavior.

`ResponseContact.wa_id` and the Cloud API body in `MessageResult.platform_response`
retain raw provider evidence. Canonical identity, Message ID, and acceptance/error semantics
are preserved. Template transport projects this same sanitized phone into its
nullable `returned_phone_number`, with no second interpretation or retry.

## Data Flow — Media Upload (file path)

```
WhatsAppMessengerAdapter._resolve_media_object(path, ...)
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
separate from the authenticated platform client. Every Messenger, from inbound dispatch or from `OutboundRuntime` (Host sends and the HTTP API), is built by `MessengerFactory`, which receives `media_download_client_provider` (`SessionLifecycle.get_media_download_client`) and hands it to the WhatsApp media handler.

**Invariant:** The media download client must never carry `Authorization` headers. Tests enforce this.

## inbox_id Mapping

`WhatsAppClient.phone_number_id` is the `inbox_id` for the WhatsApp platform. It flows into every `MessageResult` and `MediaUploadResult` as `inbox_id`. The mapping is explicit: `inbox_id == phone_number_id` for all WhatsApp operations.

## Outbound Seam Decision

`IMessenger` remains Wappa's general outbound interface for conversation messages. Responsibilities other than sending conversation messages are capabilities (ADR-0025 rule 5): media storage (`IMediaLibrary`) and WhatsApp Templates (`ITemplateMessaging`) left the interface for that reason. The Template transport is a further, deliberately smaller capability because a real Host Application needed to depend on platform sending without receiving the rest of Messenger or constructing its internal pipeline.

**Why the seam stays whole:**

- The existing platform adapter set has not yet demonstrated a need to split
  the cohesive Messenger interface further.
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

## Instagram adapter and targets

`wappa/messaging/instagram/messenger.py` owns the Unified Login native request/response translation. Factory construction binds a professional account Inbox and Business Integration System User Access Token, plus a lifecycle-aware session provider and the application Graph configuration. It uses `graph.facebook.com` by default; this adapter does not support the legacy Instagram Login token/host contract. It maps the shared contract onto Instagram: media by http(s) URL, uploaded attachment_id or local `Path` (uploaded under `filename`, with an ASCII name); a document URL in a format Instagram cannot attach as a text with the file name and link (an audio or video URL Instagram cannot play, and a video upload other than an H.264 MP4, raise `ValueError` before any call, as WhatsApp's rules do); captions as a follow-up text (`transcript` is middleware-only metadata on every Platform); list section titles and row descriptions folded into the text as a numbered menu; `send_location` and `send_contact` as text (one block per contact card); `send_sticker` as an image (a png/jpeg/gif rendition preferred, else a WebP URL; a WebP file is refused because the upload endpoint answers HTTP 500, and an animated WebP shows only its first frame); buttons, lists, CTA and carousels as templates or quick replies. It emulates WhatsApp-valid input instead of rejecting it: text over 1000 UTF-8 bytes (captions and folded list text included) goes out as several messages, a media button or CTA header goes first as its own attachment, a video carousel card shows its `poster_url` and opens the video on tap, and a folded button text over 640 characters sends the header (then the body) first as text. It registers no `IUserDataRequests` (location and phone-number requests): a text prompt cannot return the data, so `capability(IUserDataRequests)` is `None`. `disable_preview` is ignored (Instagram has no preview switch). A video carousel card without `poster_url` and `IMediaLibrary.info`/`delete` raise `UnsupportedOperationError` before any call: a card is one visual unit, and Instagram has no attachment info or delete endpoint. Known gap: `send_reaction` is a missing core method on every Platform (deprioritized by the user on 2026-11-06). Timeout/disconnect, server error, or success without a Message ID is indeterminate and never retried. Every Graph call goes through `InstagramClient.request`, which delegates to `MetaGraphClient.request` and so runs the shared `RateLimitGovernor` (`wappa.resilience.rate_limits`): code `613` is retried inside the call, code `4` blocks every Instagram Inbox of the app and `17`/`32`/`80002`/`80006` block this Inbox, each returning `rate_limited` with `retry_after` without calling Meta while the block lasts; audio and video are paced at 10/s and other calls at 100/s.

All recipient-based `IMessenger` sends accept `DirectMessage`, including WhatsApp media, interactive, specialized, and `ITemplateMessaging` Template methods. WhatsApp native handlers keep their internal address strings. Pipeline invocations serialize a `target`; the derived `recipient` property is native-address evidence for middleware. Existing WhatsApp REST request models still accept their native recipient and construct qualified targets inside the HTTP adapter. The independent typed Template transport request remains separate and explicitly maps its recipient into a DirectMessage.

`supported_operations` distinguishes implemented adapter operations from provider catalogs. IMessenger's optional-operation defaults raise `UnsupportedOperationError`; each adapter advertises its implemented methods, and the pipeline delegates discovery. A qualifier token `operation:qualifier` (Instagram's `send_text:private_reply`) refines a listed operation. `tests/test_messenger_parity.py` fails when an adapter's list differs from the optional methods it overrides plus its qualifier tokens, and when a `MessengerPipeline` / `_PipelineTemplates` wrapper's signature or forwarded arguments drift from `IMessenger` / `ITemplateMessaging`. Capabilities are discovered with `capability(kind)` instead: Instagram returns `None` for `ITemplateMessaging` and `IUserDataRequests`. `capability()` is implemented once, in `IMessenger`, over the `_capabilities: Mapping[type, object]` each adapter fills in its constructor; the lookup is by interface only, so asking for a concrete adapter class returns `None`. A new Platform-only capability is one mapping entry, never an override of `capability()`.

The shared `MessageResult` is defined in `wappa/domain/results.py` with a required `platform`. Every adapter keeps its native response in the excluded `platform_response` field (WhatsApp: the Cloud API body, built by `message_result_from_payload` in `wappa/messaging/whatsapp/models/basic_models.py`). Instagram leaves the BSUID and phone recipient evidence empty.
