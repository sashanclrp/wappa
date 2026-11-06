---
status: in_progress
created: 2026-11-05
last_reviewed: 2026-11-06
scope: finish hardening Wappa architecture (multi-Inbox, multi-Platform)
sources: audit/01-inbound-webhooks.md … audit/10-ddd-docs.md (verified, adversarially checked)
---

# Architecture hardening plan

Multi-Inbox already holds: `InboxRef.cache_namespace` is Platform-qualified, one payload-routed callback (`/webhook/inboxes/{platform}`) serves many Inboxes, and credentials are a Platform-discriminated union. Multi-Platform does not hold yet. The live runtime restates the installed-Platform set or picks "Instagram, else WhatsApp" in 9 places across 6 shared files (audit 09-1), the neutral `IMessenger` contract imports WhatsApp wire types (02-1, 02-2), and media has three overlapping seams (03-2, 03-3). This plan turns the ten verified audits into one dependency-ordered backlog. Every item cites verified finding ids; the evidence (file:line) lives in the audit files.

Cross-area conflicts were resolved by opening the code. Five rulings shape the plan. (1) The adapter registry from 01-2 and the `PLATFORMS` table from 09-1 are one thing: a single composition-root table, `wappa/platforms.py`, whose entries hold the `PlatformWebhooks` adapter and the Messenger builder. (2) The Instagram deauthorize route is deleted (06-7), not moved into the runtime (05-1): `docs/public-contract.md:316` and `wappa/messaging/ARCHITECTURE.md:230` both show it can only fire for Instagram Login grants, which this adapter does not create. (3) `IAttachmentMediaReader` is folded into `IMediaLibrary.download(max_bytes=)` (03-3) rather than kept as a capability (06-8): it is the third media seam the target shape asks to remove. (4) `supported_operations` keeps its explicit lists with a parity test (06-10 over 02-3), because derivation cannot express `send_text:private_reply`. (5) `PlatformType.TELEGRAM`/`TEAMS` stay as reserved vocabulary (09-3 partly rejected): once the registry decides what is installed, the enum is only vocabulary, and the third-Platform proof test needs an uninstalled member to register against.

## Code reality (2026-11-06)

The audit below describes the pre-hardening baseline. Its file paths and defect descriptions are historical inputs, not a claim that those defects remain. ADR references in the audits and in this plan were repointed to the consolidated ADRs; their `NNNN:line` citations point at the deleted pre-consolidation files. Implementation has landed through commits fbc7648, ab14f1b, db3fda8, 013f6e1, bb906ca, 1ae841a and 6cc8cf1. The WhatsApp-first commits further widened the shared messaging shapes. The review checkpoint is no longer a blocker to those landed slices.

The remaining work is H-26, final documentation/ADR work under H-32, H-33 and final series verification. The ADR drafts are reconciled: on the user's decision (overriding the append-only note in Rejected and deferred) each decision cluster has one consolidated ADR stating its full current decision, ADR-0022 to ADR-0027, plus ADR-0028 WhatsApp First, and the absorbed ADRs and `adr-drafts/` were deleted. A targeted run on November 6 passed 139 tests covering documentation claims, the backlog index, registry, Instagram conversations/connectors, Messenger parity and WhatsApp media library. This was not a full-suite, wheel or live rerun.

| Item | Current status | Evidence or remaining work |
| --- | --- | --- |
| H-01 | implemented | Landed in the November 6 hardening commits; final series verification remains. |
| H-02 | implemented | Landed in the November 6 hardening commits; final series verification remains. |
| H-03 | implemented | Landed in the November 6 hardening commits; final series verification remains. |
| H-04 | implemented | Landed in the November 6 hardening commits; final series verification remains. |
| H-05 | implemented | Landed in the November 6 hardening commits; final series verification remains. |
| H-06 | implemented | Landed in the November 6 hardening commits; final series verification remains. |
| H-07 | implemented | Landed in the November 6 hardening commits; final series verification remains. |
| H-08 | implemented | Landed in the November 6 hardening commits; final series verification remains. |
| H-09 | implemented | Landed in the November 6 hardening commits; final series verification remains. |
| H-10 | implemented | Landed in the November 6 hardening commits; final series verification remains. |
| H-11 | implemented | Landed in the November 6 hardening commits; final series verification remains. |
| H-12 | implemented | Landed in the November 6 hardening commits; final series verification remains. |
| H-13 | implemented | Landed in the November 6 hardening commits; final series verification remains. |
| H-14 | implemented | Landed in the November 6 hardening commits; final series verification remains. |
| H-15 | implemented | Landed in the November 6 hardening commits; final series verification remains. |
| H-16 | implemented | Landed in the November 6 hardening commits; final series verification remains. |
| H-17 | implemented | Landed in the November 6 hardening commits; final series verification remains. |
| H-18 | implemented | Landed in the November 6 hardening commits; final series verification remains. |
| H-19 | implemented | Landed in the November 6 hardening commits; final series verification remains. |
| H-20 | implemented | Landed in the November 6 hardening commits; final series verification remains. |
| H-21 | implemented | Landed in the November 6 hardening commits; final series verification remains. |
| H-22 | implemented | Landed in the November 6 hardening commits; final series verification remains. |
| H-23 | implemented | Landed in the November 6 hardening commits; final series verification remains. |
| H-24 | implemented | Landed in the November 6 hardening commits; final series verification remains. |
| H-25 | implemented | Landed in the November 6 hardening commits; final series verification remains. |
| H-26 | replaced | Ruling (user, 2026-11-06): replaced by the shared `resolve_platform_user_profile` contract on `IMessenger` (see the next group); no `IUserProfileReader` capability. |
| H-27 | done | Inbox-profile proposal now names IInboxProfileReader and typed optional fields; implementation remains a separate draft. |
| H-28 | implemented | 6cc8cf1: unsupported deauthorize route removed, connector records typed, shared Graph/login functions, connector backlog refreshed. |
| H-29 | implemented | 6cc8cf1: unsupported deauthorize route removed, connector records typed, shared Graph/login functions, connector backlog refreshed. |
| H-30 | implemented | 6cc8cf1: unsupported deauthorize route removed, connector records typed, shared Graph/login functions, connector backlog refreshed. |
| H-31 | implemented | 6cc8cf1: unsupported deauthorize route removed, connector records typed, shared Graph/login functions, connector backlog refreshed. |
| H-32 | done | ADRs consolidated per cluster (ADR-0022 to ADR-0028), CONTEXT-MAP rows added, root sediment removed, root ARCHITECTURE.md new-Platform recipe rewritten. |
| H-33 | done | `tests/test_third_platform_contract.py` and `tests/test_two_platform_inboxes.py`; `MessengerFactory` and `/api/{platform}` validation now read the app's Platform Registry table. |

### Scope decisions (2026-11-06)

- The completed v0.27 series was deleted at the user's request after confirmation that the published-package gate is ready. It no longer blocks this plan.
- Template catalog management and lifecycle handling remain Host-owned. Symphonai has create/delete catalog operations in `backend/symphonai/services/wappa/template_catalog/application.py` and the extension handler in `backend/symphonai/engine/system/meta_template_status_webhook.py`. Its generic update coverage was not established by this review; that does not create a Wappa implementation obligation.
- Outbound reactions were deprioritized by the user and their standalone draft was removed. Inbound reactions remain implemented.
- Inbox business-profile configuration and Platform conversation entry points have no equivalent Symphonai implementation in the inspected tree. Their drafts remain. H-26 User profile reading and H-27 proposal naming do not absorb Inbox profile implementation.
- H-25 owns the completed inbound Flow slice. The Flows draft retains outbound and unresolved phase-2 scope. Merely naming future Calling/Commerce/Media Adaptation capabilities here does not absorb those drafts.
- Provider delivery identity remains separate. Echo filtering and Inbox/User/address routing do not implement webhook redelivery identity or deduplication.

## Target architecture

### The five core interfaces

Four of the five exist today with two real adapters each; the work is trimming them to what callers use and removing the side doors around them. ProfileReading is the exception: WhatsApp Cloud API has no User lookup, so a mandatory interface would have one real adapter and one pass-through. The plan shipped it as a Platform capability (04-3); the H-26 ruling replaced that with one core method on every Platform, `resolve_platform_user_profile`, which maps webhook evidence on WhatsApp and adds a Graph lookup on Instagram (ADR-0025 rule 10).

| # | Interface | Module | Members (signatures) | Adapters |
| --- | --- | --- | --- | --- |
| 1 | `PlatformWebhooks` (Protocol) | `wappa/core/inbound/platform_webhooks.py` (new; also holds `RoutedWebhookDelivery`, `PayloadRoutingError` moved from `webhook_routing.py`) | `platform: PlatformType`; `builtin_fields: frozenset[str]`; `async route(payload: dict, resolver: IInboxCredentialResolver) -> tuple[RoutedWebhookDelivery, ...]` (may do credential I/O, raises `PayloadRoutingError` / the 503 family); `async translate(payload: dict, *, inbox_id: str) -> UniversalWebhook` (pure, no I/O) | WhatsApp (`processors/whatsapp_processor.py` + `core/inbound/webhook_routing.py`), Instagram (`processors/instagram_processor.py` + `core/inbound/instagram_routing.py`) |
| 2 | `IMessenger` (SendingMessages, ADR-0025) | `wappa/domain/interfaces/messaging_interface.py` | `platform`, `inbox_id`, `supported_operations`, `capability(kind)`, `require_capability(kind)`, `send_text`, `send_image`/`send_video`/`send_audio`/`send_document`, `send_sticker`, `send_button_message(..., header: ButtonHeader | None)`, `send_list_message(..., header: ButtonHeader | None, sections: list[ListSection])`, `send_cta_message`, `send_carousel`, `send_location`, `send_contact`, `send_location_request`, `send_contact_request`, `mark_as_read(message_id: str, target: DirectMessage, *, typing: bool = False) -> MessageResult` | `WhatsAppMessenger`, `InstagramMessenger` |
| 3 | `IMediaLibrary` (HandlingMedia, one seam) | `wappa/domain/interfaces/media_library.py` | `async upload(source: Path, family: MediaFamily, *, mime_type: str | None = None) -> UploadResult`; `async download(media_id: str, *, max_bytes: int | None = None) -> ReadResult[MediaBytes]` | `WhatsAppMediaLibrary`, `InstagramMediaLibrary` (private `InstagramAttachmentReader` behind it) |
| 4 | `IUserProfileReader` (ProfileReading, Platform capability) | `wappa/domain/interfaces/user_profile_reader.py` (new) | `async get_user_profile(user_id: str) -> ReadResult[UserProfile]`; `UserProfile(user_id, display_name, username, picture_url, raw=exclude)` frozen, `extra="forbid"` | Instagram (`messaging/instagram/profile.py`, Graph `GET /{igsid}`); WhatsApp registers none, its supply is webhook `UserBase.profile_name`. Promote to Shared when a second Platform has a real lookup |
| 5 | `IInboxConnector` (InboxConnection, ADR-0026) | `wappa/connections/contract.py` | `platform`; `begin(host_subject, *, metadata) -> AuthorizationRequest`; `complete(*, state, host_subject, code, error, error_reason) -> ConnectionGrant`; `activate(grant, inbox_ref, *, credentials: InboxCredentialService, previous: CredentialRecord | None = None) -> ActivationResult` (raises `ValueError` on a Platform mismatch); `disconnect(inbox_ref, account_ref, token) -> bool`; `ActivationResult.record: ActiveInboxCredentialRecord` | `WhatsAppConnector`, `InstagramConnector` on `MetaBusinessLogin` |

`PlatformWebhooks` deliberately omits four things. An SSE identity hook is not needed, because identity is read from neutral evidence fields (01-3). A display name is cosmetic and lives on the registry entry. A per-Platform authenticator is a one-adapter seam while both Platforms are Meta callbacks sharing one App Secret (01-8, ADR-0023); add `authenticate` only with a non-Meta Platform. Message-type handler tables stay private to each adapter. `route` and `translate` stay separate because ADR-0023 runs admission and echo proof between them.

### Composition root

`wappa/platforms.py` holds `PLATFORMS: Mapping[PlatformType, PlatformEntry]`, built once by `build_platforms(field_registry)`. `PlatformEntry` is a frozen dataclass, not a class hierarchy: `webhooks: PlatformWebhooks`, `build_messenger: Callable[[ResolvedInboxCredentials, MessengerDeps], IMessenger]`, `display_name: str`. `PLATFORMS.keys()` is the single installed-Platform set; the webhook controller (GET and POST), `/webhook/platforms`, the status route, `WappaCorePlugin`, `RoutePlatform` and `MessengerFactory` read it, and a missing key fails loudly (400 on HTTP, `ValueError` in code) instead of falling through to WhatsApp. The table replaces `ProcessorFactory`. Platform branches inside this module are legitimate: it is the composition root.

The credential-record union stays a static Pydantic discriminated union in `wappa/domain/inbox/credentials.py` (stored records must validate without runtime registration), with a `RECORD_TYPES: Mapping[PlatformType, tuple[type, type]]` (active, inactive) next to it so `InboxCredentialService` stops branching (05-2). Connectors stay Host-composed and are not in the table (05-7 rejected).

### Neutral homes for shared values

| Value | Today | After |
| --- | --- | --- |
| `MessageResult` | `wappa/messaging/whatsapp/models/basic_models.py:101`, `platform` defaults to WHATSAPP, imported at runtime by `wappa/domain/results.py:22` | Defined in `wappa/domain/results.py`; `platform` required; `platform_response` the single native-evidence field; `from_api_response` moves to the WhatsApp adapter. BSUID/phone recipient fields stay only if ADR-0022 Delivery Address evidence needs them on the neutral type (check during H-01) |
| `InteractiveHeader` / `HeaderType` | `wappa/messaging/whatsapp/models/interactive_models.py` | Replaced by `ButtonHeader` (text, or image by `url` or `media_id`) in `wappa/domain/interactive.py`; used by both button and list messages; video/document headers stay WhatsApp adapter validation, not neutral type |
| `ListSection` / `ListRow` | `wappa/messaging/whatsapp/models/interactive_models.py` | `wappa/domain/interactive.py`; WhatsApp wire models become private to the adapter |
| `RoutedWebhookDelivery`, `PayloadRoutingError` | `wappa/core/inbound/webhook_routing.py` (WhatsApp module) | `wappa/core/inbound/platform_webhooks.py` |
| `RouteFamily`, route profile/capabilities | `wappa/api/routes/whatsapp/route_families.py` (`WhatsAppRouteProfile`, `WhatsAppRouteCapabilities`) | `wappa/api/routes/families.py` (`MessagingRouteProfile`, `MessagingRouteCapabilities`) |
| `OutboundRuntime` | `wappa/messaging/template_transport.py` | `wappa/messaging/outbound_runtime.py` |

### Platform capability map and the one extension mechanism

There is exactly one mechanism for a Platform-only capability: a focused, action-named interface in `wappa/domain/interfaces/`, returned by the adapter from `IMessenger.capability(kind)` (implemented once in the base over a `_capabilities` mapping, 02-4), reached by Hosts with `require_capability(kind)` and by HTTP routes with `requires_capability(kind)` (501 when absent). Inbound Platform-only event families are Universal Webhook classes emitted only by their adapter, with their own handler hook; shared code never branches on them. `whatsapp_only` survives in exactly one place: the router-level dependency of the WhatsApp extension router, for static WhatsApp operations that have no capability (limits, validators, Template info, Media API info/delete, `/health`).

| Capability | Interface | WhatsApp | Instagram | Inbound lane |
| --- | --- | --- | --- | --- |
| Templates | `ITemplateMessaging` (`send_text_template`, `send_media_template`, `send_location_template`) + `OutboundRuntime.templates(inbox_ref)` transport | yes | — | Template button reply on `InboundMessageWebhook` |
| Flows | `IFlowMessaging.send_flow(target, flow, body, cta, *, header=None, footer=None, screen=None, data=None) -> MessageResult` (when the Flows PRD lands) | yes | — | typed `nfm_reply` `FlowReply` on `InboundMessageWebhook` |
| Calls | `ICallControls` (`pre_accept`, `accept`, `reject`, `terminate`, `start_call`, `request_call_permission` → `OperationOutcome`) (when the Calling PRD lands) | yes | — | `CallWebhook` → `process_call` (exists) |
| Comments | `ICommentControls`, `IConversationContentReader` (exist); private replies are a `send_text` target (`PrivateReply`, ADR-0025, ADR-0024) | — | yes | comment/mention Universal Webhooks (exist) |
| User profile | `IUserProfileReader` (interface 4) | — | yes | — |
| History | `IConversationHistoryReader` (exists) | — | yes | `HistorySyncWebhook` |

When a second sending capability (Flows) lands, `SendInvocation` carries the owning capability kind and the pipeline's `_call_raw` calls `require_capability(invocation.capability)`; `TEMPLATE_METHODS` is deleted then and not before (07-6, 07-1 rejected).

### Seams to delete or merge

- Dead parallel inbound seam: `wappa/webhooks/factory.py` (whole module), `PlatformDetector`, `WebhookFactory`/`webhook_factory`, `get_processor_for_payload`, `get_processor_capabilities`, `ProcessorCapabilities` and the abstract `capabilities` property, `PLATFORM_CAPABILITIES` and helpers in `wappa/schemas/core/types.py`, the raising Telegram/Teams processor branches, `generate_whatsapp_*` URL wrappers (01-1, 06-3, 09-3). Zero callers.
- `BaseWebhookProcessor` shrinks to the `PlatformWebhooks` protocol; parse/build helpers become private to the WhatsApp processor; Instagram's `NotImplementedError` stubs and container-ABC overrides go (01-2, 06-2).
- Media triplication: `IMediaHandler` ABC deleted (17 members, one adapter; concrete `WhatsAppMediaHandler` stays WhatsApp-internal), `IAttachmentMediaReader` ABC/capability/export deleted (reader private to Instagram), `MediaUploader` Protocol and the WhatsApp branch in `get_media_uploader` deleted. `IMediaLibrary` is the one seam (03-1, 03-2, 03-3, 06-8, 08-06).
- One-adapter domain ABCs: `MessageFactory`, `MediaFactory` collapse into their WhatsApp concretes under `wappa/messaging/whatsapp/`; `MessageBuilder` and `get_message_builder` deleted (02-5, 08-05).
- `InboundMessageWebhook.whatsapp` / `WhatsAppIncomingWebhookData` deleted (01-4).
- `OutboundRuntime._messenger` deleted; templates use the public `messenger(inbox_ref)` (07-4).
- Instagram deauthorize route and `deauthorization_event` deleted (06-7).
- Second Meta Graph transport in `InstagramSubscriptions` merged into one `graph_request` function (05-4, 06-5).

Nothing new is added with one adapter except interface 4 (as a capability, by the target shape) and the Platform-only capabilities, which are one-adapter by definition and sit behind the one extension mechanism, not a new seam.

## New Platform proof

### Files a third Platform touched before hardening

Taken from `ARCHITECTURE.md:300-311` and verified in audits 01, 05, 08, 09. Everything in the right column of the TODAY table that is not an adapter folder is a backlog item.

| File | Why it is touched today | Removed by |
| --- | --- | --- |
| `wappa/webhooks/<platform>/`, `wappa/processors/<platform>_processor.py`, `wappa/core/inbound/<platform>_routing.py` | inbound adapter | stays (adapter) |
| `wappa/messaging/<platform>/` | outbound adapter + capabilities | stays (adapter) |
| `wappa/connections/<platform>.py` (optional) | connector | stays (adapter) |
| `wappa/schemas/core/types.py` | `PlatformType` member | stays (vocabulary, one line) |
| `wappa/domain/inbox/credentials.py` | active/inactive record pair in the union | stays (static union) + `RECORD_TYPES` entry |
| `wappa/api/controllers/webhook_controller.py:116,136-140` | allow-set + router ternary | H-08 |
| `wappa/processors/factory.py:231-263,307-319` | if/elif + hand-written supported set | H-08 (file deleted) |
| `wappa/webhooks/factory.py` | documented "schema registration" step (dead) | H-06 (file deleted) |
| `wappa/core/wappa_app.py:285-295` | isinstance + getattr field-registry wiring | H-08 |
| `wappa/core/plugins/wappa_core_plugin.py:243-250` | labels + legacy filter | H-08 |
| `wappa/core/events/field_registry.py:88-96` | `_builtin_fields` branch + `_REGISTRABLE_PLATFORMS` | H-09 |
| `wappa/core/inbound/runtime.py:393` | SSE identity gate on WHATSAPP | H-12 |
| `wappa/domain/factories/messenger_factory.py:111,131-141,197-198` | allow-set + build branch + literal list | H-10 |
| `wappa/domain/inbox/services.py:76-152,191-198` | record-class ternaries, isinstance, literal set, WhatsApp health probe | H-11 |
| `wappa/api/dependencies/inbox_context.py:59-63` | `RoutePlatform` member | H-08 (derived) |
| `wappa/api/dependencies/media_transfer.py:94` | WhatsApp media branch (a new Platform with a different upload rule would add another) | H-18 |
| `wappa/domain/interfaces/messaging_interface.py:21-26` | must import WhatsApp `MessageResult`/`InteractiveHeader`/`ListSection` to implement `IMessenger` | H-01, H-02 |

### Target files a third Platform touches after hardening

- Its adapter folders: `wappa/webhooks/<platform>/`, `wappa/processors/<platform>_processor.py` (+ `core/inbound/<platform>_routing.py` or folded in), `wappa/messaging/<platform>/`, optional `wappa/connections/<platform>.py`, optional capability adapters registered in its Messenger's `_capabilities`.
- The composition root: one `PlatformEntry` in `wappa/platforms.py`.
- Vocabulary: one `PlatformType` member (already present for Telegram/Teams) and one record pair + `RECORD_TYPES` entry in `wappa/domain/inbox/credentials.py`.
- A non-Meta Platform additionally adds `authenticate` to `PlatformWebhooks` and a second authenticator at that time (deferred, see Rejected and deferred).

### `tests/test_third_platform_contract.py`

A fake Platform keyed by the reserved `PlatformType.TELEGRAM` and built only from adapters defined inside the test module, with zero edits to `wappa/`: `FakeWebhooks` (implements `PlatformWebhooks`: `route` reads `payload["inbox"]` and returns one `RoutedWebhookDelivery`; `translate` returns an `InboundMessageWebhook` with a text message and `UserBase(platform_user_id=...)`), `FakeMessenger(IMessenger)` (records `send_text` calls, returns a `MessageResult(platform=TELEGRAM, success=True, platform_response={...})`, registers no capabilities), and `FakeConnector(IInboxConnector)` (begin/complete round trip with an in-memory state store). The test builds a Wappa app whose `PLATFORMS` table is `build_platforms(...)` plus the fake entry, uses an in-memory `IInboxCredentialResolver` (no Inbox Directory record needed), and asserts: (1) `POST /webhook/inboxes/telegram` with a valid Meta signature over a fixture body is accepted and dispatched; (2) the Host's `process_message` receives the neutral webhook with `inbox_ref == InboxRef(TELEGRAM, "fake-1")` and `self.messenger.platform is TELEGRAM`; (3) the handler's `send_text(DirectMessage(...), "pong")` reaches `FakeMessenger` through `MessengerPipeline` (middleware sees it); (4) `GET /webhook/platforms` lists telegram, and `GET`/`POST /webhook/inboxes/teams` answer 400 (registered vocabulary, not installed); (5) `messenger.capability(ITemplateMessaging) is None` and `/api/telegram/templates/...` answers 501; (6) `FakeConnector` satisfies `IInboxConnector` and `activate` with a WhatsApp grant raises `ValueError` (H-29 precondition, via the shared helper). A guard test greps `wappa/` (excluding `platforms.py`, `schemas/core/types.py`, `domain/inbox/credentials.py` and adapter folders) for `PlatformType.WHATSAPP`/`PlatformType.INSTAGRAM` comparisons and fails on any new shared-code Platform branch, with an explicit allow-list for the known legitimate sites.

### Two Inboxes on two Platforms test

`tests/test_two_platform_inboxes.py`: one app, one WhatsApp Inbox and one Instagram Inbox that deliberately share the same raw `inbox_id` string. Deliver a WhatsApp fixture to `/webhook/inboxes/whatsapp` and an Instagram fixture to `/webhook/inboxes/instagram` in the same event loop. Assert each Dispatch Context carries its own `InboxRef`, the two `cache_namespace` values differ (`whatsapp__X` vs `instagram__X`), state written by one handler is invisible to the other, `OutboundRuntime.messenger(inbox_ref)` returns two distinct Messenger instances bound to the right Platform, `evict_inbox` on one leaves the other cached, and the SSE events carry `bsuid`/`phone_number` for WhatsApp and `None` for Instagram (H-12).

## Hardening backlog

Ordered by dependency: neutral types first, then dead-code removal (shrinks the surface later items touch), then the registry, then each seam. "Deletion" marks items that only remove code. Sizes: S < half day, M 1-2 days, L 3+ days.

### Seam 0: neutral contract types (do first)

**H-01 Move `MessageResult` to `wappa/domain/results.py`** (02-1, 06-1, 08-03). Size M. Breaking: yes (`wappa.messaging.whatsapp.models.basic_models.MessageResult` path removed; `MessageResult.platform` required; `api_response`/`from_api_response` leave the neutral type).
Files: `wappa/messaging/whatsapp/models/basic_models.py`, `wappa/domain/results.py`, `wappa/domain/interfaces/messaging_interface.py`, `wappa/domain/interfaces/template_messaging.py`, `wappa/messaging/instagram/messenger.py`, `wappa/core/messaging/pipeline.py`, `wappa/api/utils/event_decorators.py`, `wappa/api/utils/error_helpers.py`, `wappa/api/routes/conversations.py`, `docs/public-contract.md:56`.
Problem: the neutral send result of every Platform is WhatsApp-owned, defaults to WHATSAPP, and makes `wappa.domain` import the WhatsApp adapter at runtime.
Solution: define it in `domain/results.py` with `platform` required and `platform_response` as the one native-evidence field; WhatsApp builds it through an adapter-side constructor; repoint every import; no re-export from the old module.
Benefits: the domain stops depending on an adapter; a third Platform implements `IMessenger` without importing WhatsApp; wrong-Platform default disappears.

**H-02 Neutral `ButtonHeader`, `ListSection`, `ListRow` in `wappa/domain/interactive.py`** (02-2, 06-1). Size M. Breaking: yes (`send_button_message`/`send_list_message` header type; `InteractiveHeader`/`HeaderType`/`ListSection` exports from `wappa.messaging`).
Files: `wappa/domain/interactive.py`, `wappa/domain/interfaces/messaging_interface.py`, `wappa/messaging/whatsapp/models/interactive_models.py`, `wappa/messaging/whatsapp/messenger/whatsapp_messenger.py`, `wappa/messaging/instagram/messenger.py`, `wappa/core/messaging/pipeline.py`, HTTP interactive request models, `docs/public-contract.md:45`.
Problem: the neutral signature uses WhatsApp wire models; Instagram unwraps enums with `getattr` and digs `header.image['link']`; button and list headers have different types.
Solution: one `ButtonHeader` (text, or image by `url` or `media_id`) for both methods; neutral list types; each adapter maps to its wire shape and validates Platform limits.
Benefits: Instagram's translation code shrinks to a mapping; Hosts stop building WhatsApp dicts for Instagram.

**H-03 `mark_as_read(message_id, target, *, typing=False)` with a required target** (02-7, 06-4). Size S. Breaking: yes (`IMessenger.mark_as_read` signature, mark-as-read HTTP request `recipient` required, CLI example apps).
Files: `wappa/domain/interfaces/messaging_interface.py:88-104`, both messengers, `wappa/core/messaging/pipeline.py:295-303`, `wappa/api/routes/whatsapp/whatsapp_messages.py:163-175`, `wappa/cli/examples/simple_echo_example/app/master_event.py:64`, `wappa/cli/examples/openai_transcript/app/master_event.py:24`, `docs/public-contract.md:44`.
Problem: the base declares `target` optional but Instagram raises when it is missing; the shipped examples omit it and would fail on Instagram (LSP).
Solution: required `target`, `typing` keyword-only; update examples and the skill reference.
Benefits: Platform-neutral Host code by construction; one runtime `ValueError` and its prose caveats disappear.

**H-04 Delete `InboundMessageWebhook.whatsapp` and `WhatsAppIncomingWebhookData`** (01-4). Size S. Deletion. Breaking: yes (`InboundMessageWebhook.whatsapp`, `wappa.webhooks.core.webhook_interfaces.WhatsAppIncomingWebhookData`).
Files: `wappa/webhooks/core/webhook_interfaces/universal_webhooks.py:61-111`, `.../__init__.py:62,77`, `wappa/processors/whatsapp_processor.py:774,1430-1451`, `tests/test_whatsapp_processor_user_base.py:101-103`, docstrings `base_components.py:3-6,22,51`.
Problem: a WhatsApp-only sender slot on the neutral inbound type duplicates `UserBase`; nothing in `wappa/` reads it.
Solution: remove the class, field, helper and export; point the test at `webhook.user`; reword the "based on WhatsApp" docstrings as Platform-optional identity evidence.
Benefits: the neutral inbound type is neutral.

**H-05 Remove the Instagram-named `PrivateReply` validator** (06-6). Size S. Deletion. Breaking: no (relaxes construction; adapters still reject at send).
Files: `wappa/domain/messaging_targets.py:150,160-164`.
Problem: a domain value names a Platform and duplicates the adapter-side `require_direct_message` rejection.
Solution: drop `_instagram_only` and the Platform wording; keep `PrivateReply` in `MessageTarget`.
Benefits: a future Platform with comment-addressed replies (Facebook Pages) needs no domain edit.

### Seam 1: dead scaffolding (pure deletions)

**H-06 Delete the dead parallel inbound seam and Platform scaffolding** (01-1, 06-3, 09-3). Size M. Deletion. Breaking: yes (`WebhookURLFactory.generate_whatsapp_webhook_url`/`generate_whatsapp_verify_url`, `wappa.schemas.core.types` capability helpers; the rest is internal).
Files: `wappa/webhooks/factory.py` (delete), `wappa/processors/factory.py:16-160,241-266,377-545`, `wappa/processors/base_processor.py` (`ProcessorCapabilities`, abstract `capabilities`), `wappa/schemas/core/types.py:152-260`, `wappa/core/events/webhook_factory.py:94-106`, `ARCHITECTURE.md:306-307`, `wappa/webhooks/ARCHITECTURE.md:36,94-95,116-117,173-174`, `wappa/webhooks/CONTEXT.md:33-35`.
Problem: `SchemaFactory`, both schema registries, `PlatformDetector`, `WebhookFactory`, `ProcessorCapabilities` and `PLATFORM_CAPABILITIES` have no production or test caller, yet root `ARCHITECTURE.md` lists them as required steps for a new Platform.
Solution: delete them and the raising Telegram/Teams branches; rewrite the docs' "Adding a message family" step 2 to the WhatsApp processor's handler table. Keep `PlatformType.TELEGRAM`/`TEAMS` as reserved vocabulary.
Benefits: several hundred lines and four branch families gone; the new-Platform recipe stops pointing at dead code.

**H-07 Collapse one-adapter domain factories; delete `MessageBuilder` and dead providers** (02-5, 08-05). Size S. Deletion. Breaking: yes (`wappa.domain.factories.MessageFactory`/`MediaFactory`, `get_message_builder`, `get_whatsapp_message_factory`/`get_whatsapp_media_factory` paths).
Files: `wappa/domain/factories/message_factory.py`, `wappa/domain/factories/media_factory.py`, `wappa/domain/builders/message_builder.py`, `wappa/api/dependencies/whatsapp_dependencies.py:64-134`, `wappa/api/dependencies/whatsapp_media_dependencies.py`.
Problem: each ABC has one WhatsApp subclass and only WhatsApp consumers; `MessageBuilder` has no caller; several handler providers exist only for `/health`.
Solution: move the concretes under `wappa/messaging/whatsapp/` as private payload builders; delete the ABCs, builder, dead providers; fold `whatsapp_media_dependencies.py` into `whatsapp_dependencies.py`.
Benefits: `wappa/domain` stops presenting WhatsApp wire construction as neutral domain.

### Seam 2: `PlatformWebhooks` and the composition root

**H-08 `PlatformWebhooks` protocol and the `PLATFORMS` registry** (01-2, 06-2, 08-07, 09-1, 09-4). Size L. Breaking: yes (`WappaBuilder.mount_whatsapp_callback` renamed `mount_webhook_callback`, undocumented; `GET /webhook/inboxes/{uninstalled}` now 400 instead of answering the challenge; `BaseWebhookProcessor`/`processor_factory` internal).
Files: new `wappa/core/inbound/platform_webhooks.py`, new `wappa/platforms.py`, `wappa/api/controllers/webhook_controller.py:53,71,110-141`, `wappa/processors/factory.py` (delete), `wappa/processors/base_processor.py`, both processors, `wappa/webhooks/instagram/models.py:300-393`, `wappa/core/inbound/webhook_routing.py`, `wappa/core/inbound/instagram_routing.py`, `wappa/core/inbound/runtime.py:309-312`, `wappa/core/wappa_app.py:19,285-304`, `wappa/core/factory/wappa_builder.py:72,368-371,484`, `wappa/core/plugins/wappa_core_plugin.py:243-250`, `wappa/api/routes/webhooks.py:171,183,196`, `wappa/api/dependencies/inbox_context.py:59-63`, `tests/test_meta_payload_fixtures.py:26`, `tests/test_instagram_conversations.py:606`.
Problem: the real two-adapter inbound seam is unnamed, so the Platform is re-decided in five places against three disagreeing supported lists; every else-branch treats an unlisted Platform as WhatsApp; the shared delivery types live in the WhatsApp module; `BaseWebhookProcessor` forces Instagram to stub members only WhatsApp calls (ISP).
Solution: the four-member protocol and the `PLATFORMS` table described in Target architecture; adapters receive the `FieldHandlerRegistry` in their constructor (no `set_field_registry` mutation); controller GET and POST look up `PLATFORMS[platform]` (400 if missing) then `route`; runtime calls `translate`; plugin, status and `/webhook/platforms` read `PLATFORMS.keys()`; `RoutePlatform` derived from the keys; helpers private to the WhatsApp processor; Instagram container overrides deleted.
Benefits: a third Platform is one adapter package plus one table entry on the inbound path; the GET-challenge leak for uninstalled Platforms closes.

**H-09 Field registry built from adapter `builtin_fields`** (01-5). Size S. Breaking: no (public `register_webhook_field(platform=WHATSAPP)` default kept, 09-7).
Files: `wappa/core/events/field_registry.py:85-173`, `wappa/core/events/event_dispatcher.py:373`, `wappa/processors/instagram_processor.py:179,500`.
Problem: `_builtin_fields` branches on Instagram and `_REGISTRABLE_PLATFORMS` is a third hand-kept Platform list in core.
Solution: construct the registry with `{platform: entry.webhooks.builtin_fields}`; delete the branch and the set; make `platform` required on internal `get`/`fields`; `__contains__` takes the Platform or goes.
Benefits: Platform field knowledge stays in `webhooks/<platform>/models.py`.

**H-10 `MessengerFactory` builds through the registry; Graph version has one home** (09-1, 06-5 part). Size S. Breaking: no.
Files: `wappa/domain/factories/messenger_factory.py:111,131-141,197-198`, `wappa/core/config/meta_application.py:38`, `wappa/core/config/settings.py:90`, `wappa/connections/meta_login.py:51`, `wappa/connections/instagram.py:118`.
Problem: an allow-set, an "Instagram, else WhatsApp" build branch and a literal list; `"v26.0"` and the base URL literal repeated in five places.
Solution: `PLATFORMS[inbox_ref.platform].build_messenger(resolved, deps)`; version and base URL read only from `MetaApplicationConfig`.
Benefits: messenger construction stops being a shared-code Platform branch.

**H-11 Credential record table; neutral credential constant and health probe** (05-2, 05-3, 09-1 part). Size S. Breaking: yes (`wappa.domain.inbox.services.WHATSAPP_ACCESS_TOKEN_FIELD` leaves `__all__`, value unchanged).
Files: `wappa/domain/inbox/credentials.py:134-221`, `wappa/domain/inbox/services.py:58-67,76-152,191-198,298-304,443-447`.
Problem: record classes chosen by ternaries and isinstance in four places plus a literal Platform set; the envelope binding constant and the health probe name WhatsApp in Platform-neutral code.
Solution: `RECORD_TYPES` next to the union; service and `_require_platform` read it; `rotate_encrypted_record` uses `record.is_active`; private `_ACCESS_TOKEN_FIELD = "access_token"` (AAD unchanged); health probe via a neutral sentinel or a `ping()` on the table.
Benefits: `services.py` no longer changes per Platform.

**H-12 SSE identity read from evidence, not Platform** (01-3; 09-5 rejected). Size S. Breaking: no (WhatsApp unchanged, Instagram still `None`).
Files: `wappa/core/inbound/runtime.py:390-413`, `wappa/core/sse/context.py:135-172`.
Problem: `_derive_sse_identity` gates on WHATSAPP and guesses phone vs BSUID from identifier shape although the adapters already fill explicit evidence fields.
Solution: `derive_identifiers(user)` for webhooks with a user, `(bsuid, phone_number)` for `CallWebhook`, `(recipient_bsuid, recipient_phone_id)` for `StatusWebhook`, `(None, None)` otherwise; drop the Platform check and `classify_meta_identifier` here; make the `sse_event_scope(platform=...)` default required.
Benefits: one Platform branch removed from the runtime; aligned with ADR-0022 explicit evidence.

### Seam 3: SendingMessages

**H-13 `capability()` implemented once in the base** (02-4). Size S. Breaking: no.
Files: `wappa/domain/interfaces/messaging_interface.py:51-65`, `wappa/messaging/whatsapp/messenger/whatsapp_messenger.py:82-88`, `wappa/messaging/instagram/messenger.py:222-258`.
Problem: two lookups with different semantics (asking for the concrete class works on Instagram, returns `None` on WhatsApp).
Solution: base `capability()` over a plain `_capabilities: Mapping[type, object]` filled in each constructor, with the isinstance fallback in that one place.
Benefits: Flows, Calls and profile reading register by adding one mapping entry.

**H-14 Pipeline signature and `supported_operations` parity tests** (02-6, 02-3 reduced). Size S. Breaking: no.
Files: `tests/test_one_method_per_action.py`, `wappa/core/messaging/pipeline.py`.
Problem: the pipeline copies every `IMessenger` signature by hand and the two `supported_operations` lists are hand-kept; nothing catches drift.
Solution: one `inspect.signature` parity test for `MessengerPipeline`/`_PipelineTemplates` against `IMessenger`/`ITemplateMessaging`, and one test that each adapter's list equals its overridden optional methods plus declared qualifier tokens. No derivation machinery.
Benefits: drift fails CI; static typing kept.

**H-15 One send-route helper and one failure mapper** (08-04). Size M. Breaking: yes (`POST /api/{platform}/messages/send-text` and `mark-as-read` return 4xx for a failed result instead of 200; specialized routes lose text-guessed statuses).
Files: `wappa/api/routes/whatsapp/whatsapp_messages.py`, `whatsapp_media.py`, `whatsapp_interactive.py`, `whatsapp_specialized.py`, `wappa/api/utils/error_helpers.py:49-84`.
Problem: 14 copies of target building, 20 copies of the unsupported catch, four different mappings of a failed result.
Solution: `direct_target(messenger, request)` plus one decorator/context manager owning 400/501/500 and `raise_for_failed_result`; delete `map_whatsapp_api_error_to_status`, `_raise_for_whatsapp_error` and per-route 413/415 blocks.
Benefits: each handler is one messenger call; consistent HTTP semantics across Platforms.

**H-16 Remove the event decorator `platform` argument** (08-09). Depends on H-01. Size S. Breaking: yes (`wappa.api.dispatch_message_event(platform=)`, `fire_api_event(platform=)`).
Files: `wappa/api/utils/event_decorators.py:68-77,181-185,217-226` and 14 route call sites.
Problem: the fallback can never run, and every route passes `"whatsapp"` even on Instagram.
Solution: use `result.platform` (required after H-01).
Benefits: no wrong-Platform literal at the HTTP edge.

**H-17 Neutral names for the shared messaging router** (06-9, 08-02). Size M. Breaking: yes (`wappa.api.routes.whatsapp.route_families`, `wappa.api.routes.whatsapp_combined` module paths, OpenAPI tag names).
Files: `wappa/api/routes/whatsapp/route_families.py`, `wappa/api/routes/whatsapp_combined.py`, `wappa/api/routes/conversations.py:34`, neutral send modules under `wappa/api/routes/whatsapp/`, `wappa/api/ARCHITECTURE.md:25`.
Problem: the router that serves `/api/{platform}` for both Platforms is named, tagged and filed as WhatsApp.
Solution: `routes/families.py` (`MessagingRouteProfile`, `MessagingRouteCapabilities`), `routes/messaging_router.py`, neutral send modules under `routes/`, only the WhatsApp extension router left in `routes/whatsapp/`. Do with H-24.
Benefits: a new-Platform contributor can see which routes are shared.

### Seam 4: HandlingMedia

**H-18 `IMediaLibrary` takes `mime_type` and `max_bytes`; HTTP media routes use it** (03-1, 03-5, 08-06, 09-2 part). Size M. Breaking: no (new optional keywords; `GET /api/instagram/media/download/{id}` goes from 501 to served).
Files: `wappa/domain/interfaces/media_library.py:38-45`, `wappa/messaging/whatsapp/media_library.py:31-60`, `wappa/messaging/instagram/media_library.py:68-69`, `wappa/api/dependencies/media_transfer.py`, `wappa/api/routes/whatsapp/whatsapp_media.py:426-451`.
Problem: the shared upload dependency branches on WHATSAPP only because `upload` cannot carry an explicit MIME; download has no size bound; the download route bypasses the seam and tells Instagram Hosts to fetch CDN URLs directly.
Solution: `upload(source, family, *, mime_type=None)`, `download(media_id, *, max_bytes=None)` enforced by both adapters; `get_media_uploader = requires_capability(IMediaLibrary)`; delete the branch, the `WhatsAppMediaHandler` import and the `MediaUploader` Protocol; the download route returns `MediaBytes.content_type`; add a WhatsApp library-path route test.
Benefits: one media seam at the HTTP edge with no Platform branch (ADR-0024 decision 4 honoured).

**H-19 Delete the `IMediaHandler` ABC** (03-2, 06-8). Size S. Deletion. Breaking: yes (`wappa.domain.interfaces.IMediaHandler`).
Files: `wappa/domain/interfaces/media_interface.py`, `wappa/domain/interfaces/__init__.py:14`, `wappa/api/routes/whatsapp/whatsapp_media.py:400,435,506`, `wappa/api/routes/whatsapp/whatsapp_health.py:38`, `docs/public-contract.md:1050`, `wappa/messaging/ARCHITECTURE.md:37,57,98`.
Problem: 17 abstract members, one adapter, published next to `IMessenger` as a domain interface.
Solution: delete it; WhatsApp-only routes type against `WhatsAppMediaHandler`; no replacement ABC.
Benefits: a third Platform sees one media interface, not two.

**H-20 Fold `IAttachmentMediaReader` into `IMediaLibrary.download`** (03-3; 06-8 extras rejected). Depends on H-18. Size M. Deletion. Breaking: yes (`wappa.messaging.IAttachmentMediaReader`, `messenger.capability(IAttachmentMediaReader)`, Host-facing `stream()`).
Files: `wappa/domain/interfaces/conversation_capabilities.py:160-176`, `wappa/messaging/instagram/media.py:108`, `wappa/messaging/instagram/messenger.py:226`, `wappa/messaging/__init__.py:33`, `wappa/cli/skills/wappa-instagram-apps/references/text-and-media.md:83`, skill `SKILL.md:41`, `docs/public-contract.md:60,62`, migration doc `:147`, `wappa/messaging/ARCHITECTURE.md:48`, `tests/test_instagram_conversations.py:1093`.
Problem: a third media seam exists only because the neutral download had no size bound.
Solution: delete the ABC, export and capability registration; `InstagramAttachmentReader` stays private behind `InstagramMediaLibrary`; `stream()` deferred until a Host needs it and both adapters can implement it.
Benefits: HandlingMedia is one seam on both Platforms.

**H-21 Scaffolded transcription example uses `IMediaLibrary`** (03-10). Size S. Breaking: no.
Files: `wappa/cli/examples/openai_transcript/app/master_event.py:10,22,34`, `README.md:7`.
Problem: the scaffold casts to `WhatsAppMessenger` and uses `media_handler.download_media_tempfile` for a neutral download.
Solution: `self.messenger.require_capability(IMediaLibrary).download(media_id)`.
Benefits: scaffolds teach the neutral path.

### Seam 5: Platform capability extensions (WhatsApp)

**H-22 Move `OutboundRuntime` to `wappa/messaging/outbound_runtime.py`** (07-2). Size S. Breaking: no (`wappa.messaging.OutboundRuntime` re-export unchanged; the uncontracted deep path moves, listed in CHANGELOG).
Files: `wappa/messaging/template_transport.py:452-566`, `wappa/api/dependencies/inbox_context.py:151-161`, `wappa/messaging/__init__.py`.
Problem: the outbound Messenger factory for every Platform lives in the Template module.
Solution: move constructor, `from_app`, `messenger`, `evict_inbox`; keep `templates()` as a one-line factory.
Benefits: the generic send path is no longer filed under one Platform's capability.

**H-23 Template transport keyed by `InboxRef` and gated by capability** (07-4, 09-2 part, 10-13 code side). Depends on H-22. Size S. Breaking: yes (`OutboundRuntime.templates(inbox_id)` becomes `templates(inbox_ref)`; `InboxTemplateTransport` constructor; `InboxExecutionContext.template_transport`).
Files: `wappa/messaging/template_transport.py:404-440,557-573`, `wappa/api/dependencies/inbox_context.py:138-149`, `wappa/api/routes/whatsapp/whatsapp_templates.py:35-60`.
Problem: `_messenger` hardcodes `InboxRef.whatsapp`, so routes gate Templates on the Platform name; a missing capability would be reported INDETERMINATE although nothing was sent.
Solution: transport gets a messenger provider over the public `messenger(inbox_ref)`; `send()` checks `capability(ITemplateMessaging)` before any I/O and returns REJECTED `capability_unsupported`; delete `_messenger`; Template mutation routes take `requires_capability(ITemplateMessaging)`.
Benefits: Templates use the one extension mechanism; a latent outcome bug closes.

**H-24 One WhatsApp extension router with a single gate** (08-01, 09-2 part, 08-05 health). Size M. Breaking: yes (`GET /api/instagram/{messages,interactive,media}/limits`, `POST /api/instagram/specialized/validate-{contact,coordinates}` go from 200 to 501; `/health` response shape).
Files: `wappa/api/routes/whatsapp/whatsapp_messages.py:204-228`, `whatsapp_interactive.py:290-295`, `whatsapp_media.py:533-545`, `whatsapp_specialized.py:248-292`, `whatsapp_health.py`, `wappa/api/dependencies/inbox_context.py:39,94-108,163-176`, `wappa/api/dependencies/whatsapp_dependencies.py:46-50`, `wappa/api/routes/whatsapp_combined.py:7-9,140-145`.
Problem: WhatsApp-only gating happens only when a route happens to build a `WhatsAppClient`, so static WhatsApp routes answer 200 with WhatsApp data under `/api/instagram`; the shared execution context imports and builds `WhatsAppClient`.
Solution: mount limits, validators, Template info, Media API info/delete and `/health` from one WhatsApp extension router whose router dependency calls `whatsapp_only` once; move `whatsapp_client()` into `whatsapp_dependencies.py` over a neutral credentials accessor; `/health` reports platform, inbox_id, api_version; tests assert 501 under `/api/instagram`; fix the 404 docstring.
Benefits: one gate instead of N remembered client constructions; the shared context loses its WhatsApp import.

**H-25 Typed inbound Flow reply** (07-6). Size M. Breaking: no (Flow replies stop arriving as `UNSUPPORTED`). Feature-adjacent; can follow the hardening.
Files: `wappa/webhooks/whatsapp/message_types/interactive.py:21-23`, `wappa/processors/whatsapp_processor.py:191-206`.
Problem: `nfm_reply` is rewritten to Unsupported; Flows have no contract in either direction.
Solution: `FlowReply` (name, body, decoded `response`, `flow_token`) wired like `call_permission_reply`; `get_interactive_selection()` returns `flow_token`; outbound `IFlowMessaging` and the `SendInvocation.capability` generalisation are done with the Flows PRD.
Benefits: Flow completions reach Hosts typed.

### Seam 6: ProfileReading

**H-26 `IUserProfileReader` capability with the Instagram adapter** (04-1, 04-3). Depends on H-13. Size M. Breaking: no (additive).
Ruling (user, 2026-11-06): replaced by the shared `resolve_platform_user_profile` contract (see the next group). The text below is the original proposal.
Files: new `wappa/domain/interfaces/user_profile_reader.py`, new `wappa/messaging/instagram/profile.py`, `wappa/messaging/instagram/messenger.py:222-228`, `wappa/messaging/__init__.py`, `docs/public-contract.md`, ADR-0025 contract map.
Problem: Instagram DM Users arrive as `UserBase(platform_user_id)` only and `get_display_name()` returns the raw IGSID; Hosts cannot call Graph themselves without the Inbox token (credential-authority rule).
Solution: the interface in Target architecture; Graph `GET /{igsid}?fields=name,username,profile_pic` with `history.py`'s failure classification; never called from intake or dispatch; caching is Host policy; optional `GET /conversations/{user_id}/profile` with `requires_capability`.
Benefits: Instagram Hosts can greet Users by name through the one extension mechanism.

**H-27 Rename the Inbox-profile backlog draft** (04-2). Size S. Breaking: no (backlog only).
Files: `docs/backlog/drafts/261105-low-profile-reader-capability.md`, `docs/backlog/BACKLOG-EXECUTION-PLAN.md:25`.
Problem: `IProfileReader` for the Inbox's own business profile collides with User profile reading and carries an untyped `extras` escape hatch.
Solution: rename to `IInboxProfileReader`, typed optional fields instead of `extras`, keep it a separate low-priority two-adapter Shared capability.

### Seam 7: InboxConnection

**H-28 Delete the Instagram deauthorize route** (06-7; supersedes the move proposed in 05-1). Size S. Deletion. Breaking: yes (`POST /webhook/inboxes/instagram/deauthorize`, `wappa.connections.deauthorization_event`).
Files: `wappa/api/routes/webhooks.py:103-143`, `wappa/connections/instagram.py:368-410`, `wappa/connections/__init__.py:24-33`, `docs/public-contract.md:314-316`, `wappa/messaging/ARCHITECTURE.md` lane table, `wappa-instagram-apps` skill, ADR-0025 contract map row.
Problem: the route builds its own Dispatch Context, bypasses the Inbox Directory and makes `wappa.connections` import the webhooks layer, for a callback Meta never sends for the Unified Login grants Wappa's connector creates.
Solution: clean cut; the `InboxConnectionWebhook` lane stays real through WhatsApp `account_offboarded`/`account_reconnected`. If Instagram Login is ever supported, reintroduce the parser under `wappa/webhooks/instagram/` and dispatch through the inbound runtime.
Benefits: one side door and one layering inversion gone.

**H-29 Typed connector seam and a shared Platform precondition** (05-5, 05-8). Size S. Breaking: no (typing tightening; a mismatched grant now raises `ValueError` instead of calling Graph).
Files: `wappa/connections/contract.py:129-243`, `wappa/connections/whatsapp.py:168-190`, `wappa/connections/instagram.py:331-358`.
Problem: `ActivationResult.record` and `previous` are `Any`; neither adapter checks that the grant and `InboxRef` belong to its Platform.
Solution: `ActiveInboxCredentialRecord` / `CredentialRecord | None` types, drop `arbitrary_types_allowed`; one shared helper called first by both `activate` methods.
Benefits: wrong-Platform grants fail clearly; the persisted record is typed at the seam.

**H-30 One Meta Graph request function and one authorization prelude** (05-4, 06-5). Size M. Breaking: yes (`wappa.connections.InstagramSubscriptions` constructor).
Files: `wappa/messaging/instagram/graph.py:91-169`, `wappa/connections/instagram.py:112-220,266-310`, `wappa/connections/meta_login.py:196-257`, `wappa/connections/whatsapp.py:100-155`.
Problem: `InstagramSubscriptions` carries a second Graph transport with hand-copied outcome classification (and a weaker `unsubscribe`); both `complete()` methods repeat the same consume/exchange/debug/scopes prelude.
Solution: module-level `graph_request(client, base, path, token, *, operation, ...) -> GraphResponse` used by `InstagramGraphClient`, `InstagramSubscriptions` and optionally `MetaBusinessLogin`; one `MetaBusinessLogin.authorize(...)` returning (intent, token, expires_at, scopes); no template base class.
Benefits: outcome semantics change in one place; a third Meta connector does not copy the prelude.

**H-31 Refresh the connector backlog draft** (05-6). Size S. Breaking: no.
Files: `docs/backlog/in_progress/261105-mid-inbox-connector-contract.md`.
Solution: keep only open Wappa items (live Gate B, an Embedded Signup run, credential-step result type, optional `/register`), point to ADR-0026 for the shape, move the Symphonai step to the Symphonai backlog.

### Seam 8: docs and proof

**H-32 Docs deltas** (10-06, 10-01, 10-13, 10-02, 10-10, 10-05, 10-07, 10-09). Size M. Breaking: no. Detailed in Docs deltas below. Land the ARCHITECTURE.md new-Platform rewrite with H-08..H-11, the rest any time.

**H-33 Third-Platform contract test and two-Platform Inboxes test** (New Platform proof). Depends on H-01, H-02, H-08..H-13. Size M. Breaking: no. Can be written first as `xfail` to drive H-08.
Files: new `tests/test_third_platform_contract.py`, new `tests/test_two_platform_inboxes.py`.
Benefits: multi-Inbox and multi-Platform become provable claims checked in CI, not doc assertions.

Breaking items: H-01, H-02, H-03, H-04, H-06, H-07, H-08, H-11, H-15, H-16, H-17, H-19, H-20, H-23, H-24, H-28, H-30 (17 of 33). Pure deletions: H-04, H-05, H-06, H-07, H-19, H-20, H-28.

## Proposed public interface changes

Clean cut: no aliases, re-exports or deprecation shims (memory rule). Every row goes in the CHANGELOG of the release that ships it. This table is the user's review checkpoint.

| Symbol / surface | Change | New form | Item |
| --- | --- | --- | --- |
| `MessageResult` (`wappa.messaging`, `wappa.models`, `wappa.domain.results`) | moved, `platform` required, `api_response`/`from_api_response` removed from neutral type | defined in `wappa.domain.results` | H-01 |
| `wappa.messaging.whatsapp.models.basic_models.MessageResult` | removed | `wappa.domain.results.MessageResult` | H-01 |
| `InteractiveHeader`, `HeaderType` (`wappa.messaging`) | removed from neutral surface | `wappa.domain.interactive.ButtonHeader` | H-02 |
| `ListSection` (`wappa.messaging`) | moved | `wappa.domain.interactive.ListSection`, `ListRow` | H-02 |
| `IMessenger.send_button_message` / `send_list_message` `header` | type changed | `ButtonHeader | None` on both | H-02 |
| `IMessenger.mark_as_read(message_id, typing=False, target=None)` | signature changed | `mark_as_read(message_id, target, *, typing=False)` | H-03 |
| mark-as-read HTTP request `recipient` | now required | — | H-03 |
| `InboundMessageWebhook.whatsapp` | removed | `webhook.user` | H-04 |
| `wappa.webhooks.core.webhook_interfaces.WhatsAppIncomingWebhookData` | removed | — | H-04 |
| `PrivateReply` Instagram-only construction check | removed (adapters still reject) | — | H-05 |
| `WebhookURLFactory.generate_whatsapp_webhook_url` / `generate_whatsapp_verify_url` | removed | `generate_webhook_url(PlatformType.WHATSAPP)` | H-06 |
| `wappa.schemas.core.types` `PLATFORM_CAPABILITIES` and helpers | removed | `PLATFORMS` registry | H-06 |
| `wappa.webhooks.factory` module, `PlatformDetector`, `WebhookFactory`, `webhook_factory`, `ProcessorCapabilities` | removed (internal) | — | H-06 |
| `wappa.domain.factories.MessageFactory`, `MediaFactory` | removed | private WhatsApp payload builders | H-07 |
| `wappa.domain.builders.MessageBuilder`, `get_message_builder` | removed | — | H-07 |
| `processor_factory`, `ProcessorFactory`, `BaseWebhookProcessor` | replaced (internal) | `wappa.platforms.PLATFORMS`, `PlatformWebhooks` | H-08 |
| `PlatformWebhooks`, `PLATFORMS`, `PlatformEntry`, `build_platforms` | new | `wappa.core.inbound.platform_webhooks`, `wappa.platforms` | H-08 |
| `RoutedWebhookDelivery`, `PayloadRoutingError` | moved | `wappa.core.inbound.platform_webhooks` | H-08 |
| `WappaBuilder.mount_whatsapp_callback` | renamed | `mount_webhook_callback` | H-08 |
| `GET /webhook/inboxes/{platform}` for an uninstalled Platform | 200 challenge becomes 400 | — | H-08 |
| `wappa.domain.inbox.services.WHATSAPP_ACCESS_TOKEN_FIELD` | removed from `__all__` (value kept privately) | — | H-11 |
| `wappa.domain.inbox.credentials.RECORD_TYPES` | new | — | H-11 |
| `POST /api/{platform}/messages/send-text`, `mark-as-read` failed result | 200 becomes 4xx | — | H-15 |
| `wappa.api.dispatch_message_event(platform=)`, `fire_api_event(platform=)` | parameter removed | `result.platform` | H-16 |
| `wappa.api.routes.whatsapp.route_families` (`RouteFamily`, `WhatsAppRouteProfile`, `WhatsAppRouteCapabilities`) | moved/renamed | `wappa.api.routes.families` (`MessagingRouteProfile`, `MessagingRouteCapabilities`) | H-17 |
| `wappa.api.routes.whatsapp_combined` | renamed | `wappa.api.routes.messaging_router` | H-17 |
| OpenAPI tags "WhatsApp - Messages" etc. on shared routes | renamed | neutral tags | H-17 |
| `IMediaLibrary.upload` | new keyword | `mime_type: str | None = None` | H-18 |
| `IMediaLibrary.download` | new keyword | `max_bytes: int | None = None` | H-18 |
| `GET /api/instagram/media/download/{media_id}` | 501 becomes served | — | H-18 |
| `wappa.domain.interfaces.IMediaHandler` | removed | concrete `WhatsAppMediaHandler` | H-19 |
| `wappa.messaging.IAttachmentMediaReader`, `capability(IAttachmentMediaReader)`, `stream()` | removed | `IMediaLibrary.download(max_bytes=)` | H-20 |
| `wappa.messaging.template_transport.OutboundRuntime` deep path | moved (`wappa.messaging.OutboundRuntime` unchanged) | `wappa.messaging.outbound_runtime` | H-22 |
| `OutboundRuntime.templates(inbox_id)` | signature changed | `templates(inbox_ref, credentials=None)` | H-23 |
| `InboxTemplateTransport` constructor; `InboxExecutionContext.template_transport` | changed | messenger provider over `InboxRef` | H-23 |
| Template send with no capability | INDETERMINATE becomes REJECTED `capability_unsupported` | — | H-23 |
| `/api/instagram/*/limits`, `/api/instagram/specialized/validate-*` | 200 becomes 501 | WhatsApp extension router | H-24 |
| `GET /api/{platform}/health` | response slimmed | platform, inbox_id, api_version | H-24 |
| `FlowReply`, `MessageType` for `nfm_reply` | new | — | H-25 |
| `IMessenger.resolve_platform_user_profile`, `PlatformUserProfile` | new (H-26 ruling replaced `IUserProfileReader`) | one core method on every Platform | H-26 |
| `POST /webhook/inboxes/instagram/deauthorize`, `wappa.connections.deauthorization_event` | removed | WhatsApp `account_offboarded` lane unchanged | H-28 |
| `ActivationResult.record`, `IInboxConnector.activate(previous=)`, `build_record` | typed | `ActiveInboxCredentialRecord`, `CredentialRecord | None` | H-29 |
| `InstagramSubscriptions` constructor | changed | takes the shared Graph transport | H-30 |

## Docs deltas

- `CONTEXT.md:204`: map tenant/tenant_id to `inbox_id` only when it means the Platform-facing identity; business tenancy is a Host concern with no Wappa term; drop the `owner_id` clause (10-01). Add terms: Platform Registry (`PLATFORMS`, the installed-Platform set), Platform Capability (an interface reached through `IMessenger.capability`, one mechanism), User Profile (`IUserProfileReader`, Platform capability) (H-08, H-26).
- `CONTEXT-MAP.md`: add rows for API (`wappa/api/ARCHITECTURE.md`), External Webhooks (`wappa/core/external_webhooks/ARCHITECTURE.md`) and Connections (ADR-0026, terms in root `CONTEXT.md:106`); no new per-context glossaries (10-05).
- Root `ARCHITECTURE.md:290-311`: item 2 lists Instagram adapter paths too; item 4 says `PlatformType` is vocabulary and `PLATFORMS` is installation; item 6 "Adding a new platform" becomes the AFTER list in New Platform proof (adapter folders, one `PlatformEntry`, one enum member, one record pair). Until H-08..H-11 land, item 4 must state the current branches as known debt rather than claim a registry (10-06). Add a Connections row to the deeper-docs table (`:339-349`). Cut Key Architectural Decisions (`:351-363`) to a one-line pointer to `docs/adr/` and move the logging paragraph under a fitting heading (10-07).
- `wappa/webhooks/ARCHITECTURE.md` and `wappa/webhooks/CONTEXT.md`: remove `SchemaFactory`/registry rows; document the `PlatformWebhooks` protocol and the WhatsApp handler table for "Adding a message family" (H-06, H-08).
- `wappa/messaging/ARCHITECTURE.md`: neutral types now in `wappa/domain` (`:64-66`); media section names only `IMediaLibrary` (`:37,48,57,98`); capability map table per Target architecture; drop the Instagram deauthorize lane cell (H-01, H-02, H-19, H-20, H-28).
- `wappa/api/ARCHITECTURE.md`: list `ITemplateMessaging` among capability-gated routes (`:34`); describe the shared messaging router vs the WhatsApp extension router and its single gate (`:25,35`) (10-13, H-17, H-24).
- `docs/public-contract.md`: every row of Proposed public interface changes, including `:44,45,56,60,62,71,280,314-316,1050`.
- ADRs (user decision, 2026-11-06, replacing the banner plan): one consolidated ADR per cluster states the cluster's full current decision: ADR-0022 identity and Inbox Directory, ADR-0023 inbound webhooks, ADR-0024 outbound HTTP routes and transports, ADR-0025 Messenger contract, ADR-0026 Inbox connection, ADR-0027 runtime lifecycle; ADR-0028 WhatsApp First is new. ADR-0005, ADR-0008 and ADR-0013 stay standalone. The absorbed ADRs and `adr-drafts/` are deleted and every reference repointed (10-02, 10-13).
- Root sediment: `git rm TEMPLATE_API_GUIDE.md` (wrong, unlinked; 10-10); `git rm META_PRODUCTION.md` (stray personal Postman link; 10-09); `META-CHANGELOGS.md` stays (10-11 rejected).

Single home for each business rule after the hardening:

| Rule | Single home |
| --- | --- |
| Which Platforms are installed | `wappa/platforms.py` `PLATFORMS` |
| Platform vocabulary | `wappa/schemas/core/types.py` `PlatformType` |
| Callback authentication before parse | ADR-0023 + `webhook_controller.py` (`MetaCallbackAuthenticator`) |
| Payload → Inbox routing, per Platform | each `PlatformWebhooks.route` adapter |
| Credential record shape and Platform → record class | `wappa/domain/inbox/credentials.py` (`RECORD_TYPES`) |
| Credential authority (Hosts never hold Inbox tokens) | root `ARCHITECTURE.md` + `CONTEXT.md` |
| One method per cross-Platform action | ADR-0025 |
| Platform-only capability mechanism and capability map | ADR-0025 + `wappa/messaging/ARCHITECTURE.md` table |
| Media upload/download semantics | `IMediaLibrary` docstrings + ADR-0025 |
| HTTP gating (capability → 501; WhatsApp extension router) | ADR-0024 + ADR-0025 |
| Graph API version and base URL | `MetaApplicationConfig` |

## Rejected and deferred

Rejected findings (from the verified audits, plus the cross-area rulings above):

- 01-2-auditor: merged into 01-1 (dead parts) and 01-2 (live branches).
- 01-7: wrong; the `user_id` fallback belongs to `CallWebhook`, which has `bsuid`/`phone_number`.
- 01-8: correct ADR-0023 design; a per-Platform authenticator is a one-adapter seam while both Platforms are Meta.
- 01-9: out of area; handled as H-28.
- 02-8: no ISP split of `IMessenger`; confirms the design.
- 02-3 (derivation of `supported_operations`): replaced by a parity test (H-14); derivation cannot express qualifier tokens (06-10).
- 02-3 sub-claim (callers hit errors after checking): wrong; a missing entry correctly means unsupported.
- 02-4 sub-claim (callable cast): typing-only, cosmetic.
- 03-4: cosmetic; stateless per-call `WhatsAppMediaLibrary` is free.
- 03-6: merged into H-18; bytes source, neutral `limits()` and "never raise" rejected (hypothetical or contradict ADR-0024 decision 4).
- 03-7: observation, not a defect.
- 03-8: evidence wrong; the variants have a scaffold caller and a released Host feature.
- 03-9: docs accurate today; updates are in H-19/H-20.
- 04-4: design guidance, folded into H-26.
- 04-5: no violation; kept as a constraint.
- 04-6: optional route noted in H-26.
- 05-1 (move deauthorize into the inbound runtime): superseded by 06-7 delete (H-28); the callback cannot fire for Unified Login grants.
- 05-2 sub-claim (silent else-branch): refuted, `_require_platform` runs first.
- 05-4 sub-claim (MetaInboxConnector template base): over-engineering.
- 05-7 (Wappa-owned connector registry): connectors are Host-composed; a registry would be a hypothetical seam.
- 06-2-auditor (move PrivateReply to `ICommentControls`): conflicts with ADR-0025, ADR-0024, loses middleware and echo coverage.
- 06-9 split half (split `conversation_capabilities.py`): cosmetic.
- 06-10 (derived `supported_operations`): over-engineering; parity test instead.
- 06-8 extras (`IAttachmentMediaReader` as a legitimate capability): overruled by 03-3 / H-20 to remove the third media seam.
- 07-1 (pipeline registry for sending capabilities): one capability today; trigger recorded in H-25 / Target architecture.
- 07-3 (collapse three Template methods): contract churn ADR-0025 does not ask for.
- 07-5, 07-7: duplicates merged into 07-4 and 07-6.
- 07-8 (Calls SSE branch): not Calls-specific; covered by H-12.
- 07-9 (capability if-chain, ITemplateMessaging MRO): leave the MRO; lookup unified by H-13.
- 08-08 (`include_outbound_transport` as a shim): ADR-0024 fail-closed default.
- 08-10: merged into 08-01 (H-24).
- 08-10b (`RoutePlatform` duplicates `PlatformType`): it is a deliberate narrowing; now derived from `PLATFORMS` (H-08).
- 08-05b (duplicate `get_whatsapp_media_factory`): factually wrong.
- 09-3 enum part (remove `PlatformType.TELEGRAM`/`TEAMS`): rejected; with the registry the enum is vocabulary only, the GET leak is closed by H-08, and the proof test needs an uninstalled member.
- 09-5: evidence wrong (Instagram SSE events carry `user_id`); the Platform gate itself is removed by H-12 on evidence grounds.
- 09-6: duplicate of 09-1.
- 09-7: deauthorize handled by H-28; `MediaResult` defaults cosmetic; `register_webhook_field` default kept; `generate_whatsapp_*` moved to H-06.
- 09-8: cosmetic; labels come from `PlatformEntry.display_name` after H-08.
- 09-9: dead code, deleted in H-06.
- 10-03, 10-04, 10-12: the verifier rejected consolidation as rewriting an append-only log. The user overrode that on 2026-11-06: the clusters were consolidated (see Docs deltas), and ADR-0005 stays standalone as the verifier argued.
- 10-08: unsupported; layering across docs is deliberate.
- 10-11: cosmetic; `META-CHANGELOGS.md` is linked and accurate.

Deferred (not in this hardening):

- Gate C live verification and every Symphonai migration step (separate repo, out of scope).
- `IFlowMessaging` outbound and `SendInvocation.capability` (Flows PRD); `ICallControls` (Calling PRD).
- `IMediaLibrary.stream()` until a Host needs it and both adapters implement it.
- `IInboxProfileReader` build (H-27 only renames the draft).
- `send_reaction` core method, deprioritized by the user on 2026-11-06; no standalone implementation draft.
- Credential-step `begin` result type and any Wappa-owned connector registry (ADR-0026 consequences; wait for a non-Meta connector).
- `authenticate` on `PlatformWebhooks` and a non-Meta callback authenticator (wait for a non-Meta Platform).
- A pluggable credential-record union (static union kept; revisit only if a Platform must ship outside the package).
- Removing the public `register_webhook_field(platform=WHATSAPP)` default (optional clean cut, not planned).

Unaudited areas: none; all ten areas returned verified results. Not covered by any area and therefore unaudited at seam level: cache backends and SSE hub internals beyond identity (ADR-0013, ADR-0022), external webhooks (ADR-0023), CLI scaffolding beyond the two examples cited, and the HTTP client lifecycle (ADR-0027).
