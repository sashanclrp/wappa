# Changelog

All notable changes to Wappa will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

Instagram conversations join WhatsApp on one Messenger contract, and Wappa's contracts are split by responsibility so it can host more messaging Platforms. Every action that exists on more than one Platform has exactly one `IMessenger` method. Each adapter maps that method onto its native API, so Host code never branches on Platform name ([ADR-0025](docs/adr/0025-messenger-contract.md)). Platform-only families are capabilities a Host asks for: Templates for WhatsApp; comment controls and content reads for Instagram; the Media Library for both. Connecting an account so it becomes an Inbox is a separate contract, `IInboxConnector`, implemented for both Instagram and WhatsApp ([ADR-0026](docs/adr/0026-inbox-connection.md)).

### Breaking changes

This release is a clean cut: no aliases or compatibility shims are kept. Step-by-step upgrade from 0.33: [docs/migration/v0.34.0-from-0.33.md](docs/migration/v0.34.0-from-0.33.md).


- **Templates moved to a capability.** Call `messenger.require_capability(ITemplateMessaging).send_*_template(...)`. Middleware names are unchanged; `OutboundRuntime.templates()` takes an `InboxRef` (details below).
- **Recipient sends take `target=DirectMessage(...)`, and `DirectMessage` takes `addresses=DeliveryAddresses` instead of `recipient_id` ([ADR-0022](docs/adr/0022-inbox-identity-and-directory.md)).** The `recipient="..."` keyword is gone and no alias remains. Replace `DirectMessage(inbox_ref=..., recipient_id=x)` with `DirectMessage(inbox_ref=..., addresses=DeliveryAddresses.of(x))`. Inside a webhook, reply with `addresses=webhook.user.delivery_addresses()` so WhatsApp gets both the phone and the BSUID. Outside webhooks (operator sends, campaigns, reminders), pass every address you have stored: `DeliveryAddresses.of(bsuid, phone)`. `DirectMessage.recipient_id` still reads the first address.
- **WhatsApp chooses the address and falls back.** With both known, Wappa now sends to the phone first and to the BSUID only when there is no phone or Meta rejects the phone (`131030`, `131062`), following Meta's guidance. Authentication Templates go to phones only. `MessageResult.attempted_recipients` lists the addresses tried when it fell back.
- **WhatsApp cache keys are Platform-qualified: `whatsapp__<phone_number_id>` (deploy step, [ADR-0022](docs/adr/0022-inbox-identity-and-directory.md)).** Every Platform now uses one namespace rule, `<platform>__<inbox_id>`. Before 0.34, WhatsApp state, user, table, AI-state and expiry keys started with the raw `phone_number_id`, so after upgrading they are invisible until renamed. Deploy order: stop every 0.33 worker, run `wappa migrate cache-namespaces -i <phone_number_id> [-i ...]` (dry run) and then again with `--apply` (Redis keeps TTLs; existing keys are never overwritten; `--json-root` for the JSON backend), then start 0.34. Pub/Sub channels become `wappa:notify:whatsapp__<pnid>:...`, so subscribers must use the new pattern. `InboxRef.from_cache_namespace` rejects the raw form.
- **The Inbox Directory cache is cleared at startup (explicit routing).** A record changed in the Host source while Wappa was down (a rotated token, a deactivation) now takes effect on restart; before, the cached row could keep serving the old token for as long as messages kept arriving. Inboxes reload from the source on first use. Changes made while Wappa runs still need `refresh_inbox(inbox_ref)`.
- **The messaging HTTP API serves every Platform at `/api/{platform}`** ([ADR-0024](docs/adr/0024-outbound-http-routes-and-transports.md)). `/api/whatsapp/...` URLs are unchanged; `/api/instagram/...` sends through the Instagram Inbox selected by `X-Wappa-Inbox-ID`. Breaking for Hosts:
  - `create_whatsapp_router` is removed; mount `create_messaging_router` (`wappa.api.routes`).
  - Route tables and OpenAPI list paths as `/api/{platform}/...`.
  - A Host route that depends on `get_inbox_execution_context` must sit under a `{platform}` path parameter; without one it answers 500 (no implicit WhatsApp).
  - Send routes build the Messenger through `OutboundRuntime`, so **app Messenger middleware (window guards, Pub/Sub `bot_reply`) now runs on API sends**; before it was skipped.
  - A route the Inbox's Platform cannot serve answers **501** (`"<platform> does not provide <capability>"`): Template sends, Template info, media info/delete, text and media limits, the contact/coordinate validators and `/health` on Instagram; comments and post reads on WhatsApp. A local rule violation answers 400.
  - The legacy default Inbox only answers for its own Platform.
- **`send_sticker` formats per Platform.** WhatsApp stickers are `.webp` only (512x512; 100 KB static, 500 KB animated). Instagram has no stickers and sends an image: `.png`, `.jpg`, `.jpeg` or `.gif` (8 MB). `sticker_source` now also takes a list of renditions, and each adapter sends the first one its Platform accepts: `await messenger.send_sticker(["sticker.webp", "sticker.png"], target)`. When no rendition fits, `ValueError` is raised before any call (`POST .../send-sticker` answers 400). Before, WhatsApp accepted a PNG link with 200 and the message failed later as status `131053`. Wappa never converts media.
- **`send_audio` formats per Platform, and voice notes on both Platforms from one call.** `audio_source` now also takes a list of renditions; each adapter sends the first one its Platform accepts. WhatsApp voice note (`is_voice=True`): `.ogg` (Opus, mono) only. WhatsApp audio: `.aac`, `.amr`, `.mp3`, `.m4a` or `.ogg` (16 MB). Instagram: `.aac`, `.m4a`, `.wav` or `.mp4` (25 MB). Instagram shows every audio attachment as a voice message, so `is_voice` changes nothing there. `await messenger.send_audio(["note.ogg", "note.m4a"], target, is_voice=True)` sends a voice note on both. When no rendition fits, `ValueError` is raised before any Platform call (`POST .../send-audio` answers 400). This covers a WhatsApp `is_voice=True` with a non-OGG file, which before was sent and arrived as a plain audio file, and an OGG to Instagram, which before reached Meta and failed with `100/2534080`. A single source without an extension (a media ID, an Instagram CDN URL) is passed through unchanged.
- **`send_contact(contacts, target)` takes one typed `ContactCard` or a sequence of them** (now Platform-neutral in `wappa.domain.contacts`, exported from `wappa.messaging` and `wappa.models`; `wappa.messaging.whatsapp.models` no longer exports it). The keyword is renamed `contact=` → `contacts=`, and passing a dict no longer works: wrap it with `ContactCard.model_validate(d)`. WhatsApp sends every card in one native contacts message; Instagram sends one text block per card, split over several messages beyond 1000 UTF-8 bytes. As in the Cloud API, only `name.formatted_name` is required: `ContactCard.phones` is optional (`list[ContactPhone] | None`), so code that iterates `card.phones` must handle `None`. HTTP `POST /api/{platform}/specialized/send-contact` takes `contacts` (a list of one or more cards) instead of `contact`.
- **`supported_operations` no longer lists Template methods.** Check `messenger.capability(ITemplateMessaging)` instead.
- **`bot_reply` Pub/Sub notifications are keyed by the destination.** A send from a webhook to a different User was announced under the webhook User; it is now keyed by the destination address.
- **`UniversalWebhook` has six new members** (`MessageUpdateWebhook`, `IncomingCommentWebhook`, `MentionWebhook`, `OutboundEchoWebhook`, `HistorySyncWebhook`, `InboxConnectionWebhook`). Exhaustive `match` / `isinstance` code must add cases.
- **WhatsApp events moved to the shared lanes (ADR-0025).** Hosts handling these in `process_message` or `process_system_webhook` must move them:
  - consumer `edit` / `revoke` → `MessageUpdateWebhook` in `process_message_update` (was `InboundMessageWebhook` with `MessageType.EDIT` / `REVOKE`);
  - Coexistence `smb_message_echoes` → `OutboundEchoWebhook` in `process_outbound_echo` (was `SystemWebhook(SMB_MESSAGE_ECHO)`);
  - Coexistence `history` → `HistorySyncWebhook` in `process_history_sync` (was `SystemWebhook(HISTORY_SYNC)`);
  - Coexistence `account_offboarded` / `account_reconnected` → `InboxConnectionWebhook` in `process_inbox_connection` (was `SystemWebhook(ACCOUNT_*)`).
  `SystemEventType.SMB_MESSAGE_ECHO`, `HISTORY_SYNC`, `ACCOUNT_OFFBOARDED` and `ACCOUNT_RECONNECTED` are removed.
- **`SystemEventDetail` payloads are typed.** `coexistence_payload` is removed (`smb_app_state_sync` is now `contact_sync: ContactSync`); `group_update` is a `GroupUpdate` and `user_action` a `UserAction` instead of dicts.
- **`ad_referral` and `AdReferralBase` are removed.** Read `InboundMessageWebhook.entry_referral` (`EntryReferral`, same fields: headline, body, media URLs, `click_id`, welcome message) on every Platform. `has_ad_referral()` is renamed `is_from_ad()` (true when `entry_referral.kind` is `ad`).
- **Inbox-scoped helpers take an `InboxRef`; bare-ID shorthands that meant WhatsApp are removed.**
  - `WappaContextFactory.create_context(inbox_ref, user_id, *, include_messenger)`: the `inbox_id` and `platform` parameters are gone.
  - `CronPlugin.add_cron(..., inbox_ref=...)`: `inbox_id=` is gone.
  - `create_expiry_messenger(inbox_ref)` and `create_expiry_cache_factory(inbox_ref, user_id)`; `parse_inbox_from_expired_key` is removed, use `parse_inbox_ref_from_expired_key`.
  - `OutboundRuntime.evict_inbox(inbox_ref)`.
  - `build_channel(inbox_ref, user_id, event_type)` and `build_pattern(inbox_ref, ...)`: the `platform=` keyword is gone; the `InboxRef` qualifies the channel.
- **Detailed health moved the Inbox runtime to a top-level `inbox_runtime` key** (`inbox_routing_mode`, `inbox_directory`); `platform_configs.whatsapp` keeps only `legacy_default_inbox` and `meta_callback`.
- **`send_audio` takes `is_voice`** on `IMessenger`, the pipeline and every adapter (before, only `WhatsAppMessenger` had it, so app code behind the pipeline could not ask for a voice note). WhatsApp sends `audio.voice: true` and renders a voice note (waveform) for OGG/Opus mono files; Instagram ignores it. Custom `IMessenger` implementations and test doubles must accept the keyword. `POST /api/{platform}/media/send-audio` takes `is_voice`.
- **`mark_as_read(message_id, target, *, typing=False)` takes a required `target`.** `typing` is keyword-only. Positional `mark_as_read(id, True)` and calls without a target fail with `TypeError`; Instagram's runtime `ValueError` for a missing target is gone. Custom `IMessenger` implementations and test doubles must take the new signature. The HTTP `POST /api/{platform}/messages/mark-as-read` body now requires `recipient` on every Platform (422 without it). The shipped CLI examples and the scaffold template pass the target.
- **`MessageResult` is defined in `wappa.domain.results`.** `wappa.messaging.whatsapp.models.basic_models.MessageResult` and the `wappa.messaging.whatsapp.models` export are removed; import it from `wappa.messaging`, `wappa.models` or `wappa.domain.results`. `platform` is now required (it defaulted to WhatsApp). `api_response`, `MessageResult.from_api_response` and `MessageResult.from_response_payload` are removed: the native response is in `platform_response` on every Platform (the WhatsApp Cloud API body, excluded from serialization), and the WhatsApp builders are the adapter-internal `message_result_from_api_response` / `message_result_from_payload`.
- **One neutral `InteractiveHeader` for button messages, shaped like the WhatsApp Cloud API header.** The WhatsApp `InteractiveHeader(type=HeaderType..., image={"link": ...})` and `HeaderType` are removed (from `wappa.messaging` and `wappa.messaging.whatsapp.models.interactive_models`). The neutral `InteractiveHeader` and `MediaRef` live in `wappa.domain.interactive` (exported from `wappa.messaging`), and `ListSection` and `ListRow` moved there too. `send_button_message(header=)` and `send_cta_message(header=)` take `InteractiveHeader | None` (`send_cta_message` took a plain `str` before): `kind` is `text`, `image`, `video` or `document`; media is a `MediaRef` with a `url`, a `media_id` or both (WhatsApp sends the `media_id` when set, Instagram the `url`); `filename` is for a document only. Instagram sends a media CTA header first as its own attachment, as for buttons. Build one with `InteractiveHeader.of_text("Menu")`, `of_image(url=...)`, `of_video(media_id=...)` or `of_document(url=..., filename="menu.pdf")`. `send_list_message(header=)` stays a plain `str | None` (WhatsApp list headers are text only). HTTP `POST /api/{platform}/interactive/send-buttons` takes `header` as `{"kind": "text", "text": ...}` or `{"kind": "image" | "video" | "document", "media": {"url": ..., "media_id": ...}, "filename": ...}` instead of `{"type": ..., "image": {"link": ...}}`, and `send-cta` takes the same object instead of a header string; `send-list` keeps a text `header`. `wappa.api.utils.convert_header_to_dict` is removed.
- **Interactive limits are the most restrictive limit across WhatsApp and Instagram, enforced when the value is built**, so a message that builds is deliverable on every Platform. The constants live in `wappa.domain.interactive`: `ReplyButton` id 1–256 and title 1–20; 1–3 buttons with unique IDs; button `body` ≤ 640 (WhatsApp allows 1024, Instagram's button template 640); `ListRow` id ≤ 200, title ≤ 20 (WhatsApp allows 24, Instagram quick replies 20) and description ≤ 72; `ListSection.title` ≤ 24, now optional for a single section and required when there are several; 1–10 sections and ≤ 10 rows in total (before, 10 per section); row IDs unique across all sections; list `body` ≤ 1000 characters (WhatsApp allows 4096, Instagram text is 1000 UTF-8 bytes); list `button_text` ≤ 20; header text and footer ≤ 60; CTA `button_text` ≤ 20 and CTA `body` ≤ 640 (WhatsApp allows 1024); 2–10 carousel cards, carousel `body` ≤ 1000 characters (WhatsApp allows 1024), card title ≤ 80 and subtitle ≤ 80 (Instagram) with title + newline + subtitle ≤ 160 (WhatsApp), ≤ 2 buttons per card (Instagram allows 3). An over-limit value raises `ValidationError` when you build it; `body`, `footer`, `button_text`, `button_url`, the list `header`, the section set and the card count are checked by `check_button_message` / `check_list_message` / `check_cta_message` / `check_carousel`, which every adapter calls, so an over-limit call raises `ValueError` before any Platform call (HTTP 422 from request validation, 400 from a send). WhatsApp no longer returns failed results with `BODY_TOO_LONG`, `HEADER_TOO_LONG`, `ROW_TITLE_TOO_LONG` or the other local length codes for button and list messages, nor `MISSING_REQUIRED_PARAMS` / `INVALID_URL_FORMAT` for CTA messages (a bad CTA URL raises `ValueError` before any call, HTTP 400), and `validate_buttons_menu_limits` is removed. `GET /api/{platform}/interactive/limits` reports exactly these values: `max_rows_per_section` is replaced by `max_rows_total`, `button_messages` gains `max_header_text_length`, `supported_header_types` by `supported_header_kinds`, `cta_messages` reports the enforced CTA limits (instead of the 256 / 4096 lengths it advertised and never enforced), and a new `carousels` section reports the card limits.
- **`InboundMessageWebhook.whatsapp` and `WhatsAppIncomingWebhookData` are removed.** Read the sender from `webhook.user` (`phone_number`, `bsuid`, `parent_bsuid`, `username`, `country_code`) on every Platform.
- **Unknown WhatsApp webhook fields now reach `process_system_webhook` as `SystemWebhook(UNSUPPORTED_EVENT)` instead of getting HTTP 400.** `event_detail.platform_event` holds `{"field", "value"}`. Handlers that switch on `SystemEventType` should ignore or log the type they do not know.
- **Meta schema drift is logged, not rejected.** Unmodelled properties in Meta payloads are accepted and Wappa logs `META_SCHEMA_DRIFT platform=<p> field=<Model.field>` once per field per process (never the value). Alert on it. The `WHATSAPP_WEBHOOK_CONTRACT_DRIFT` critical log is removed. Host test suites can set `WAPPA_STRICT_META_SCHEMA=1` to raise `MetaSchemaDriftError` on drift.
- **Dead Platform scaffolding is removed.** `WebhookURLFactory.generate_whatsapp_webhook_url()` and `generate_whatsapp_verify_url()` are gone; call `generate_webhook_url(PlatformType.WHATSAPP)`. `wappa.schemas.core.types` no longer has `PLATFORM_CAPABILITIES`, `get_platform_capabilities`, `is_message_type_supported`, `is_interactive_type_supported`, `get_max_text_length` or `get_max_media_size` (the per-Platform limits routes still serve limits). Internal and never wired, also deleted: the `wappa.webhooks.factory` module (`SchemaFactory`, `schema_factory`, `MessageSchemaRegistry`, `WebhookSchemaRegistry`), `PlatformDetector`, `WebhookFactory` / `webhook_factory`, `ProcessorFactory.get_processor_for_payload` / `get_processor_capabilities`, `ProcessorCapabilities` with the processors' `capabilities` property, and the raising Telegram/Teams processor branches. `PlatformType.TELEGRAM` and `TEAMS` stay as reserved vocabulary.
- **WhatsApp payload factories are adapter-private.** `wappa.domain.factories.MessageFactory`, `WhatsAppMessageFactory`, `MediaFactory` and `WhatsAppMediaFactory` are removed; the WhatsApp adapter builds payloads with the private `WhatsAppMessagePayloadBuilder` / `WhatsAppMediaPayloadBuilder` (`wappa.messaging.whatsapp.payload_builders`). `WhatsAppMessenger(...)` no longer takes `message_factory=` / `media_factory=`. `wappa.domain.builders` (`MessageBuilder` and its helpers) and the FastAPI providers `get_message_builder`, `get_whatsapp_message_factory`, `get_whatsapp_media_factory`, `get_whatsapp_messenger`, `get_whatsapp_interactive_handler`, `get_whatsapp_template_handler` and `get_whatsapp_specialized_handler` are removed, and `wappa.api.dependencies.whatsapp_media_dependencies` is folded into `whatsapp_dependencies`. A Host route that needs a Messenger depends on `get_inbox_messenger`.
- **Custom `IMessenger` implementations** inherit `capability()` returning `None`. To expose Templates or a Media Library, return the capability object from `capability()`.
- **Installed Platforms come from one Platform Registry, `wappa.platforms.PLATFORMS`** (ADR-0023). `PlatformType` is vocabulary only. `GET /webhook/inboxes/{platform}` for a Platform with no entry (`telegram`, `teams`) now answers **400** instead of answering Meta's challenge; POST was already 400. `ProcessorFactory`, `processor_factory` and `BaseWebhookProcessor` (`wappa.processors.factory`, `wappa.processors.base_processor`) are removed; `PLATFORMS[platform].webhooks` is the Platform's `PlatformWebhooks` adapter (`route`, `translate`). `ProcessorError` and `UnsupportedMessageTypeError` moved to `wappa.processors.errors`. `WhatsAppWebhookProcessor` / `InstagramWebhookProcessor` take the `FieldHandlerRegistry` in their constructor (`set_field_registry` is removed) and `create_universal_webhook(payload, inbox_id=)` is renamed `translate(payload, *, inbox_id=)`; the WhatsApp parse/build helpers (`parse_webhook_container`, `create_message_from_data`, `create_status_from_data`, `get_supported_message_types`, `register_message_handler`) and Instagram's `NotImplementedError` stubs are gone. `InstagramWebhook` (`wappa.webhooks.instagram`) is a plain envelope model, no longer a `BaseWebhook`: its container methods (`is_incoming_message`, `get_raw_messages`, `get_metadata`, ...), `InstagramMetadata`, `is_user_message` and `is_text_message` are removed.
- **`RoutedWebhookDelivery` and `PayloadRoutingError` moved to `wappa.core.inbound.platform_webhooks`** (still exported from `wappa.core.inbound`); `wappa.core.inbound.webhook_routing` no longer exports them.
- **`WappaBuilder.mount_whatsapp_callback()` is renamed `mount_webhook_callback()`.**
- **`FieldHandlerRegistry(builtin_fields)` takes each installed Platform's reserved fields** (`wappa.platforms.BUILTIN_FIELDS`); its `get(field, platform)` and `fields(platform)` require the Platform, and `field in registry` (WhatsApp-only membership) is removed. `register_webhook_field(..., platform=PlatformType.WHATSAPP)` keeps its default. `BUILTIN_WEBHOOK_FIELDS`, `ACCOUNT_EVENT_FIELDS`, `BUSINESS_USERNAME_EVENT_FIELDS` and `COEXISTENCE_EVENT_FIELDS` moved from `wappa.core.events.field_registry` to `wappa.webhooks.whatsapp.webhook_container`.
- **`wappa.domain.inbox.services.WHATSAPP_ACCESS_TOKEN_FIELD` is removed.** The envelope binding name stays `access_token`, so stored records decrypt unchanged. `wappa.domain.inbox.credentials.RECORD_TYPES` maps each Platform to its `(active, inactive)` record classes.
- **`sse_event_scope(...)` requires `platform=`**; it no longer defaults to `"whatsapp"`.
- **`IMessenger.resolve_platform_user_profile(user)` is a new abstract method (H-26).** Custom Messengers and test doubles that subclass `IMessenger` must implement it; returning `PlatformUserProfile.from_evidence(self.platform, user)` is enough for a Platform with no User lookup.
- **`MessengerFactory.get_supported_platforms()` and `is_platform_supported()` are removed**; read `PLATFORMS` keys.
- **Send routes answer one status per failure (08-04).** `POST /api/{platform}/messages/send-text` and `/messages/mark-as-read` now answer a 4xx for a failed `MessageResult` instead of 200 with `success: false`. Every send route (messages, media, interactive, specialized, `send-private-reply`) and `POST /media/upload` map a failed result through `raise_for_failed_result`: the status its `error_code` maps to (413 size limits, 415 `MIME_TYPE_UNSUPPORTED`, 403 Template not found/approved), else 400. Specialized sends no longer guess 401/404/429/500 from the error text, and a `ValidationError` raised while sending answers 400 instead of 422. `UnsupportedOperationError` is still 501, a local `ValueError` 400, anything else 500. A failed send now emits its API event (`response_success=False`) on every send route. `wappa.api.utils.map_whatsapp_api_error_to_status` is removed; `wappa.api.utils.direct_target(messenger, request)` and `map_send_errors(operation)` are the one target builder and failure mapper. `send-private-reply` no longer answers a flat 400 for every failed result or lets an unexpected exception escape unmapped.
- **`dispatch_message_event()` and `fire_api_event()` no longer take `platform=`** (`wappa.api`, `wappa.api.utils`). The `APIMessageEvent.platform` is always `result.platform`, the Platform that sent; before, every route passed `"whatsapp"`, even on Instagram (the value was then ignored by the decorator but used by `fire_api_event`).
- **`IMediaLibrary` is the only media interface (03-2, 03-3).** `wappa.domain.interfaces.IMediaHandler` is removed; WhatsApp-only media code types against the concrete `WhatsAppMediaHandler` (`WhatsAppMessenger.media_handler`). `wappa.messaging.IAttachmentMediaReader` and `messenger.capability(IAttachmentMediaReader)` are removed, and with them the Instagram-only `stream(url)`; replace `get_bytes(url, max_bytes=n)` with `require_capability(IMediaLibrary).download(url, max_bytes=n)`. `InstagramAttachmentReader` is private to `InstagramMediaLibrary`. `wappa.api.dependencies.media_transfer.MediaUploader` is removed; `get_media_uploader` returns a `LibraryMediaUploader`. `IMediaLibrary` gains the abstract `info(media_id)` and `delete(media_id)` and `upload` takes `source: Path | bytes` and `filename=`, so a custom `IMediaLibrary` must implement them (raise `UnsupportedOperationError` where the Platform has no endpoint). `GET /api/{platform}/media/info/{media_id}` and `DELETE /api/{platform}/media/{media_id}` now go through `IMediaLibrary` (Instagram: 501) instead of the WhatsApp handler; the response bodies keep their shape. A delete of an unknown Media ID answers 404, a refused token 403, an unknown outcome 502, other refusals 400 (before: 404 only when the error text said "not found", else 400).
- **The shared messaging router has neutral names (H-17).** `wappa.api.routes.whatsapp.route_families` is now `wappa.api.routes.families`, with `WhatsAppRouteProfile` → `MessagingRouteProfile` and `WhatsAppRouteCapabilities` → `MessagingRouteCapabilities` (`RouteFamily` moves with them); `wappa.api.routes.whatsapp_combined` is now `wappa.api.routes.messaging_router`. The shared route modules moved from `wappa/api/routes/whatsapp/whatsapp_<name>.py` to `wappa/api/routes/<name>.py` (`messages`, `media`, `interactive`, `specialized`, `templates`, `state_handlers`), and their OpenAPI tags lost the `WhatsApp - ` prefix (`Messages`, `Media`, `Interactive`, `Specialized`, `Template Transport`, `State Handlers`). `wappa.api.routes.create_messaging_router` is unchanged; URLs are unchanged.
- **One WhatsApp extension router with a single gate (H-24).** `GET /api/{platform}/messages/limits`, `/media/limits`, `POST /specialized/validate-contact`, `/specialized/validate-coordinates`, Template info (`/templates/info*`, `/templates/limits`) and `/health` live in `wappa.api.routes.whatsapp.whatsapp_extension_router`, whose router dependency `whatsapp_only` (now in `wappa.api.dependencies.whatsapp_dependencies`, a dependency on the path Platform instead of a function over an `InboxRef`) answers **501** under any other Platform before any Inbox lookup. Under `/api/instagram` the limits and validators answered 200 with WhatsApp data; they now answer 501. `GET /api/{platform}/interactive/limits` stays shared and answers 200 on every Platform, because its limits are the shared minimum. Template send routes gate on `requires_capability(ITemplateMessaging)` instead of the Platform name.
- **`GET /api/whatsapp/health` is slimmed** to `status`, `platform`, `inbox_id` and `api_version` (the Inbox's Graph API version). The static `timestamp` and `services` block are gone.
- **`InboxExecutionContext.whatsapp_client()` is removed;** the shared context no longer imports `WhatsAppClient`. WhatsApp-only Host routes depend on `get_whatsapp_client` (`wappa.api.dependencies.whatsapp_dependencies`), which builds the client from the new neutral `InboxExecutionContext.credentials`. `InboxExecutionContext.template_transport(app)` no longer rejects non-WhatsApp Inboxes itself; the transport reports `capability_unsupported`.
- **`OutboundRuntime` lives in `wappa.messaging.outbound_runtime` (H-22).** `from wappa.messaging import OutboundRuntime` is unchanged; the uncontracted deep path `wappa.messaging.template_transport.OutboundRuntime` is gone. The private `OutboundRuntime._messenger(inbox_id)` that hardcoded WhatsApp is removed.
- **Carousel card rules hold when the value is built ([ADR-0028](docs/adr/0028-whatsapp-first.md) rule 2).** `MessageCard.header` is required and `buttons` needs at least one button; a card with a `UrlButton` and reply buttons, or with two `UrlButton`s, fails with `ValidationError`. `check_carousel` (run by every adapter and the `send-carousel` route) also requires the same button kind and count on every card (`ValueError`, HTTP 400). Before, these were checked only by the WhatsApp adapter at send, so a carousel built for Instagram (cards without a header or button) failed on WhatsApp; such cards no longer build on any Platform. The WhatsApp adapter's own copies of the checks and Instagram's "needs a subtitle, image, default URL or button" check are gone.
- **`send_text` and media captions are checked against WhatsApp's limits on every Platform** (`TEXT_MAX` = 4096, `CAPTION_MAX` = 1024 in `wappa.domain.interactive`, ADR-0028 rule 3). A longer text or caption raises `ValueError` before any I/O on both adapters (HTTP 400). Before, Instagram split any length and WhatsApp returned a failed result from the Cloud API.
- **The neutral HTTP send request models moved out of the WhatsApp adapter to `wappa.schemas.requests`.** `BasicTextMessage`, `ReadStatusMessage`, `ButtonMessage`, `ListMessage`, `CTAMessage`, `ImageMessage`, `VideoMessage`, `AudioMessage`, `DocumentMessage`, `StickerMessage`, `MediaMessage`, `ContactMessage`, `LocationMessage` and `LocationRequestMessage` import from `wappa.schemas.requests` (or `wappa.models`); `wappa.messaging.whatsapp.models` and its `basic_models`, `media_models` and `specialized_models` modules no longer define or export them, and `wappa.messaging.whatsapp.models.interactive_models` is deleted. `MediaMessage.media_type` is now a `MediaFamily` (same values) instead of the WhatsApp `MediaType`. The WhatsApp-only `MediaType`, `BusinessContact`, `PersonalContact`, `ContactValidationResult`, `LocationValidationResult`, `TemplateParameter` and `WhatsAppTemplateType` are no longer re-exported from `wappa.models`; import them from `wappa.messaging.whatsapp.models`.
- **`wappa.webhooks` exports only the universal models.** `WhatsAppWebhook`, `WhatsAppMetadata`, `WhatsAppContact`, `ContactProfile`, `MessageContext`, `MessageError`, `ErrorData`, `Pricing` and `Conversation` import from `wappa.webhooks.whatsapp`.
- **`TemplateStateService` moved to the WhatsApp extension.** Import it from `wappa.messaging.whatsapp.services`; `wappa.api`, `wappa.api.services` and the module `wappa.api.services.template_state_service` no longer provide it. `get_template_state_service` moved from `wappa.api.dependencies.cache_dependencies` to `wappa.api.dependencies.whatsapp_dependencies`.
- **`BSUID_ERROR_TAG` lives in `wappa.schemas.core.recipient`**; `wappa.messaging.whatsapp.utils.error_helpers` no longer defines it.
- **`register_webhook_field(..., platform=...)` requires `platform`** on `Wappa`, `WappaBuilder` and `FieldHandlerRegistry.register`; it no longer defaults to WhatsApp. Pass `platform=PlatformType.WHATSAPP` for a WhatsApp field.
- **`MediaUploadResult`, `MediaInfoResult`, `MediaDownloadResult` and `MediaDeleteResult` require `platform`**; they no longer default to WhatsApp.
- **The payload routing modules moved into the webhook adapter folders.** `wappa.core.inbound.webhook_routing` is now `wappa.webhooks.whatsapp.routing` and `wappa.core.inbound.instagram_routing` is `wappa.webhooks.instagram.routing`. `route_whatsapp_payload` is no longer exported from `wappa.core.inbound`; `PlatformAccountNotRegisteredError` is still exported there and is defined in `wappa.core.inbound.platform_webhooks`.
- **Location and phone-number requests are the WhatsApp `IUserDataRequests` capability ([ADR-0025](docs/adr/0025-messenger-contract.md) rule 4).** `IMessenger.send_location_request` and `send_contact_request` are removed, from `MessengerPipeline` too, and WhatsApp's `supported_operations` no longer lists them. Call `messenger.require_capability(IUserDataRequests).send_location_request(body, target)` (`from wappa.messaging import IUserDataRequests`); through the pipeline the calls still run the message middleware under the same method names. Instagram returns `None` for the capability instead of raising `UnsupportedOperationError` from the method. `POST /api/{platform}/specialized/send-location-request` now gates on `requires_capability(IUserDataRequests)`, so the 501 detail reads `"<platform> does not provide IUserDataRequests"`.
- **`capability(kind)` resolves by interface only.** Asking for a concrete adapter class (`capability(WhatsAppMediaLibrary)`, `capability(InstagramMediaLibrary)`) now returns `None`; ask for `IMediaLibrary`.
- **`PlatformWebhooks.translate(payload, *, inbox_id)` takes `inbox_id` as a required keyword on both adapters**, matching the protocol. `WhatsAppWebhookProcessor().translate(payload)` and `InstagramWebhookProcessor().translate(payload)` without `inbox_id` raise `TypeError`; a WhatsApp custom field without metadata takes the passed `inbox_id` (it was `""` when omitted).

### Breaking: WhatsApp Templates moved off `IMessenger` ([ADR-0025](docs/adr/0025-messenger-contract.md))

Templates are a WhatsApp-only message family, so they are now a focused capability instead of contract methods that every Platform had to reject.

- **Removed from `IMessenger` and `MessengerPipeline`:** `send_text_template`, `send_media_template` and `send_location_template`.
- **New:** `ITemplateMessaging` (exported from `wappa.messaging`), with the same three methods and the same signatures. `WhatsAppMessenger` implements it; Instagram does not provide it.
- **Middleware is unchanged.** `MessengerPipeline.capability(ITemplateMessaging)` returns a wrapper that still runs the message middleware chain, and `SendInvocation.method_name` is still `send_text_template` / `send_media_template` / `send_location_template`, so window guards and cache middleware keyed on those names keep working.
- **`OutboundRuntime.templates(inbox_ref, credentials=None)` takes an `InboxRef`** (it took a bare WhatsApp `inbox_id`), and `InboxTemplateTransport.send` checks `ITemplateMessaging` before any I/O: an Inbox whose Messenger lacks it gets `outcome=REJECTED`, `error_code="capability_unsupported"`, never `INDETERMINATE`. `InboxTemplateTransport(inbox_ref=..., messenger_provider=...)` replaces `InboxTemplateTransport(runtime=..., inbox_id=..., credentials=...)`; Hosts get it from `OutboundRuntime.templates`.
- `IMessenger.capability` / `require_capability` now take `kind: Callable[..., C]`, so abstract capability interfaces type-check under mypy (they raised `type-abstract` with `type[C]`).

**Migrate:**

```python
# before
await messenger.send_text_template("order_ready", target, params, "es", template_type="utility")
# after
templates = messenger.require_capability(ITemplateMessaging)
await templates.send_text_template("order_ready", target, params, "es", template_type="utility")
```

- Code that called `messenger.send_*_template(...)` directly (including through a `MessengerPipeline`) must switch to the capability.
- Test doubles and custom `IMessenger` implementations that provide Templates must implement `ITemplateMessaging` and return it from `capability()`.
- Hosts that send through `OutboundRuntime` pass an `InboxRef`: `OutboundRuntime.from_app(app).templates(InboxRef.whatsapp(phone_number_id))`. Hosts that only match template method names in middleware need no code change.

### Changed

- **`IMessenger.capability()` is implemented once, in the base** (02-4). Adapters fill `self._capabilities: Mapping[type, object]` in their constructor instead of overriding the lookup. Lookup is by capability interface only, and `capability(IMediaLibrary)` returns one cached `WhatsAppMediaLibrary` instead of a new one per call.
- `tests/test_messenger_parity.py` pins `MessengerPipeline` and `_PipelineTemplates` signatures and forwarded arguments to `IMessenger` / `ITemplateMessaging`, and each adapter's `supported_operations` to the optional methods it overrides plus qualifier tokens (`send_text:private_reply`).
- **Platform-neutral wiring.** The webhook controller, `/webhook/platforms`, the status route, `WappaCorePlugin`'s webhook URL log (labels from `PlatformEntry.display_name`), the `/api/{platform}` validation and `MessengerFactory` read the app's Platform Registry table instead of their own Platform lists; each built app holds its own table (`app.state.platforms`), so two apps in one process no longer share field registries through a processor singleton. `InboxCredentialService` picks record classes from `RECORD_TYPES` and `InboxDirectory.check_health()` probes the directory table with `InboxDirectoryTable.ping()` instead of reading a WhatsApp sentinel Inbox. Inbound SSE identity (`bsuid`, `phone_number`) is read from the adapters' evidence fields (`UserBase`, `CallWebhook`, `StatusWebhook.recipient_bsuid`/`recipient_phone_id`) instead of a WhatsApp check and identifier-shape guessing; WhatsApp events carry the same values and Instagram events still carry `None`.
- **A Platform in the app's table is served end to end** (H-33). `MessengerFactory` and `OutboundRuntime` take the app's Platform Registry table (`platforms=`, from `app.state.platforms`; `PLATFORMS` when omitted), and `/api/{platform}` validates against the same table, so a Platform entry added to an app builds its Messenger in dispatch and in API sends. The internal `RoutePlatform` enum of `wappa.api.dependencies.inbox_context` is removed: `route_platform` returns the `PlatformType`, OpenAPI still documents the installed set, and an unknown or uninstalled `{platform}` answers 404 before any Inbox lookup. `tests/test_third_platform_contract.py` proves a fake Platform built only from test adapters (callback, dispatch, Messenger Pipeline, 400 for an uninstalled Platform, 501 for a missing capability, connector Platform check) and guards shared code against new Platform branches; `tests/test_two_platform_inboxes.py` proves a WhatsApp and an Instagram Inbox with the same raw ID stay isolated.
- **The Graph API version and base URL have one default**, `DEFAULT_GRAPH_API_VERSION` / `DEFAULT_GRAPH_BASE_URL` in `wappa.core.config.meta_application`, used by `MetaApplicationConfig`, the `META_API_VERSION` / `META_BASE_URL` env defaults, `MetaLoginConfig` (whose `graph_base` `InstagramSubscriptions` takes, so it has no default of its own) and `InboxCredentialAccess`.
- **Breaking: recipient-based Messenger sends now require `target=DirectMessage(inbox_ref=..., addresses=DeliveryAddresses.of(...))` instead of `recipient="..."`.** This covers text, image/video/audio/document/sticker, buttons/lists/CTA, contacts/contact requests, locations/location requests, and WhatsApp Template send methods. Update custom implementations, wrappers, middleware, mocks, background callers and serialized send-event consumers. No recipient-keyword alias or string-target overload is retained. Cross-Inbox targets reject before provider I/O; the native Delivery Address remains distinct from a Host User ID. Independently typed WhatsApp HTTP and Template-transport inputs remain adapter contracts. See the [0.33 → 0.34 migration guide](docs/migration/v0.34.0-from-0.33.md).
- Optional Messenger operations expose `supported_operations` and raise `UnsupportedOperationError` when unimplemented; a shared method's existence does not promise Platform support.
- **Breaking for exhaustive consumers:** `UniversalWebhook` adds `MessageUpdateWebhook`, `IncomingCommentWebhook`, `MentionWebhook`, `OutboundEchoWebhook`, `HistorySyncWebhook` and `InboxConnectionWebhook`. Instagram deletions, reactions, quick replies, postbacks and attachments no longer arrive as `SystemWebhook(UNSUPPORTED_EVENT)`.
- **One Messenger method per action on every Platform ([ADR-0025](docs/adr/0025-messenger-contract.md)).** An action that exists on more than one Platform has exactly one `IMessenger` method, and each adapter maps it onto its native API, rejecting what it cannot honour before any provider call. Hosts check `messenger.supported_operations` once and never branch on Platform name. Instagram-only actions stay behind capabilities: `reply_comment` lives on `ICommentControls` (`messenger.require_capability(ICommentControls).reply_comment(comment_ref, text)`).
- An Instagram postback tap is an `InboundMessageWebhook` (`InstagramButtonReplyMessage`, `interactive_type` `BUTTON_REPLY`, `is_button_reply`) dispatched to `process_message`; read it with `webhook.get_interactive_selection()` exactly like WhatsApp button/list replies and Instagram quick replies. There is no separate interaction lane.
- `ReplyButton` moved to the neutral `wappa.domain.interactive` (exported from `wappa.messaging`; the WhatsApp models no longer re-export it) and is the one "choose this option" value on every Platform.
- `FieldHandlerRegistry` keys registrations by `(platform, field)`; `get`/`fields` take an optional `platform` (default WhatsApp).
- Instagram error codes are `code/subcode` strings. Instagram text over 1000 UTF-8 bytes is sent as several messages, cut on a word boundary when possible (the reply context goes on the first one); a `PrivateReply`, one message per comment, cannot be split and raises `ValueError` before I/O. `send_text(disable_preview=True)` is ignored on Instagram instead of raising `UnsupportedOperationError`, and an image, video or document caption over the limit is split the same way.
- `PrivateReply` no longer names a Platform: constructing one on any Inbox succeeds, and an adapter without comment-addressed replies (WhatsApp) rejects it at send with `UnsupportedOperationError`, as before.
- **`IMediaLibrary.upload(source, family, *, mime_type=None, filename=None)` and `download(media_id, *, max_bytes=None)`** (03-1, 03-3, 03-5). WhatsApp passes `mime_type` to the Media API and both adapters enforce `max_bytes` (an oversize read is `rejected` with `error_code="SIZE"`). `POST /api/{platform}/media/upload` goes through `IMediaLibrary` on every Platform, with no WhatsApp branch. `GET /api/{platform}/media/download/{media_id}` is gated on `IMediaLibrary` and answers with the `MediaBytes.content_type` (one Media API call fewer on WhatsApp); on Instagram it now serves the attachment (URL-encoded attachment URL as `media_id`) instead of 501, and an oversize read answers 413. A failed WhatsApp download says whether a retry can help: a Media ID Graph rejects as unknown, expired or deleted (Graph 400/404), a missing media URL or a CDN 404 is `not_found` (404), a Graph or CDN 401/403 is `access_denied` (403), another CDN 4xx is `rejected` (400), and only timeouts, 5xx and transport errors, on the info call or the CDN fetch, are `unavailable` (503). A failed media-info call now keeps Graph's status as `error_code="HTTP_<status>"` (on `WhatsAppMediaHandler.get_media_info` and `download_media`) instead of `INFO_RETRIEVAL_FAILED` / `MEDIA_INFO_FAILED`, which now mean only a timeout or transport error. Before, the route answered 404 only when the error text said "not found" and 400 otherwise.
- The `openai_transcript` scaffold downloads audio with `require_capability(IMediaLibrary).download(media_id)` instead of casting to `WhatsAppMessenger` and using `media_handler` (03-10).
- Wappa's daily log file (`wappa_YYYYMMDD.log`) now rolls over at midnight. Before, a long-running server kept writing to the previous day's file.

### Added

- **`POST /api/{platform}/specialized/send-contact-request`** asks the User to share a phone number through the `IUserDataRequests` capability (body `{"recipient", "body", "reply_to_message_id"}`, `ContactRequestMessage`; 501 off WhatsApp). The outbound classifier labels it `contact_request` (`OutboundTransportSubkind.CONTACT_REQUEST`).
- **`IUserDataRequests`** (`wappa.domain.interfaces.user_data_requests`, exported from `wappa.messaging`): the WhatsApp location and phone-number request capability.
- **Guard and parity tests.** `tests/test_third_platform_contract.py` fails when shared code imports an adapter package; `tests/test_messenger_parity.py` checks the `PlatformWebhooks`, `IMediaLibrary` and `IInboxConnector` adapters against their contract signatures.
- **An emulated Instagram send returns one result listing every part.** When the Instagram adapter delivers one Host call as several messages (split text, caption follow-up, media header before buttons or a CTA, carousel intro), the `MessageResult` is `success` only if every part was accepted, keeps the tapped message's ID (the media's for a captioned media send), and lists every delivered part under `platform_response["wappa_parts"]` (`message_ids`, `delivered`). A refused part stops the send, and its `error` says how many earlier parts were already delivered.
- **`IMessenger.resolve_platform_user_profile(user: UserBase) -> PlatformUserProfile` on every Platform (H-26, [ADR-0025](docs/adr/0025-messenger-contract.md) rule 10).** It returns every fact the Platform provides about a User, with field names matching `UserBase` (`platform_user_id`, `bsuid`, `parent_bsuid`, `phone_number`, `username`, `country_code`, `profile_name`) plus `picture_url`, an `outcome` (`ReadOutcome`) and a `raw` lookup body that never serialises. WhatsApp maps the webhook evidence with no I/O (`found`); Instagram adds `GET /{igsid}?fields=name,username,profile_pic` with the Inbox token, merged over the evidence, and on a failed lookup returns the evidence with `not_found`, `access_denied`, `rejected` or `unavailable` instead of raising. It is read-only and Wappa never calls it during intake or dispatch: merging, persistence and re-resolution are Host policy. The Messenger Pipeline forwards it without middleware. `PlatformUserProfile` is exported from `wappa.messaging`. Both adapters list it in `supported_operations`.
- **Typed WhatsApp Flow replies (H-25).** A completed Flow (`interactive.type == "nfm_reply"`) is a `WhatsAppInteractiveMessage` with `is_flow_reply`, `interactive_type == InteractiveType.FLOW_REPLY` and `interactive.nfm_reply: FlowReply` (`name`, `body`, raw `response_json`, decoded `response` dict, `flow_token`); `get_interactive_selection()` returns the `flow_token`. Undecodable answers leave `response` empty instead of failing the webhook. Sending Flows is not offered yet.
- Capability-gated HTTP routes under `/api/{platform}` (ADR-0024), 501 where the Platform lacks the capability:
  - `ICommentControls` (group `comment_controls`, `include_comment_controls_api`; on under `standalone`, off under `embedded`): `POST /comments/{id}/reply`, `/hide`, `/unhide`, `DELETE /comments/{id}`, `POST /posts/{media_id}/comments-enabled`.
  - `IConversationContentReader` (always mounted): `GET /posts/{media_id}`, `/posts/{media_id}/comments`, `/comments/{id}`, `/comments/{id}/replies`.
  - `IConversationHistoryReader`: `GET /conversations/{user_id}/messages`.
  - `POST /messages/send-private-reply` (`send_text` with a `PrivateReply`; outbound transport group).
  - `POST /media/upload` now works for Instagram Inboxes through `IMediaLibrary` (`message_attachments`).
  - `requires_capability(kind)` dependency for Host routes that gate on a capability.
- `POST /api/{platform}/interactive/send-carousel` (`send_carousel` over HTTP) and `addresses` on every send request body (`DeliveryRequest`); `mark-as-read` takes an optional `recipient` (required on Instagram).
- **One lane per event on every Platform ([ADR-0025](docs/adr/0025-messenger-contract.md)), all typed:**
  - `OutboundEchoWebhook` (`process_outbound_echo`): a message the business sent **outside Wappa** (the Instagram app, the WhatsApp Business app, another tool), with typed content (`message`, `message_type`, `get_text()`; `native_type` for shapes with no inbound model). Wappa applies a fixed filter so echoes of its own sends are never delivered ([ADR-0023](docs/adr/0023-inbound-webhooks.md)): WhatsApp Coexistence only echoes Business-app messages; Instagram echoes every send with no sender-app evidence (verified live: no `app_id` or `metadata` on either a Wappa send or a hand-typed message), so Wappa keeps `ISentMessageRegistry`, one short-lived key per sent message ID (`TableSentMessageRegistry`: 10-minute TTL, cut to a 2-minute grace once its echo is claimed, so only in-flight sends stay; shared across workers on Redis; re-checked after 1 s and 2 s because an echo can beat the send response). If the registry is down the echo is delivered with `origin=UNKNOWN` rather than lost.
  - Reactions: Instagram `message_reactions` now arrive as `InboundMessageWebhook` with `InstagramReactionMessage`, the same `BaseReactionMessage` shape (`target_message_id`, `emoji`, `is_removal`) WhatsApp reactions use.
  - `MessageUpdateWebhook` gains `message`, the typed replacement content of an edit, and now carries WhatsApp edits and deletions too.
  - `EntryReferral` (with `EntryPointKind`: ad, post, link, other) is the one entry-point model: Click-to-WhatsApp ads and posts, Instagram ads and ig.me links. No raw dict.
  - History backfill: `HistorySyncWebhook` (`process_history_sync`) carries Coexistence `history` as typed `HistoryThread`s of `HistoryMessage` (direction, status, typed content); the `IConversationHistoryReader` capability reads the same shape from Instagram's Conversations API (`read_history(user_id, limit≤20, after)`).
  - `InboxConnectionWebhook` (`process_inbox_connection`): WhatsApp `account_offboarded` / `account_reconnected`. Instagram has no emitter: Meta sends no deauthorize callback for the Unified Login grants `InstagramConnector` creates, so Wappa mounts no Instagram deauthorize route. Revoke an Instagram Inbox by deactivating its record and calling `connector.disconnect`.
  - `ContactSync`, `GroupUpdate`, `UserAction` typed `SystemEventDetail` payloads. `platform_event` remains only for `UNSUPPORTED_EVENT` evidence.
- Instagram message families: image, audio, video, file, shares (`ig_post`, `ig_reel`, `reel`, `story`), story mentions, story replies, reply context, attached referrals (`InboundMessageWebhook.entry_referral`), quick-reply selections. New `MessageType.SHARE` and `MessageType.STORY_MENTION`.
- Hooks `process_message_update`, `process_comment`, `process_mention` with optional defaults; `SystemEventType.REFERRAL`.
- Instagram sends through the shared contract: media by https URL or uploaded local `Path`, `PrivateReply` targets for `send_text`, `send_button_message` (button template; a media header, by URL or `attachment_id`, is sent first as its own attachment, then the buttons with the full body; when header, body and footer fold to over 640 characters the header, then the body, goes first as text), `send_list_message` (quick replies on the last text message; folded text over 1000 bytes is split), `send_cta_message` (one `web_url` button; a media header is sent first, as for buttons) and `send_carousel` (a video card shows its `poster_url` and opens the video on tap; a video card without `poster_url` is rejected before any call, because card media is never sent apart from its card). Header and footer text fold into the message text; presentation Instagram cannot show (section titles, row descriptions, list button text) is dropped and documented.
- `IMessenger.mark_as_read(message_id, target, *, typing=False)` is one acknowledge contract for both Platforms. Instagram marks `target`'s thread seen, then `typing_on`. WhatsApp marks the message read and checks `target` against its Inbox.
- `IMessenger.send_carousel(cards, target, body, reply_to_message_id=None)` on both Platforms (2–10 `MessageCard`s): a WhatsApp interactive media carousel (every card needs a `header`, a `CardMedia` image or video by public `url`, sent as the header `link` because Meta takes no Media ID for card headers, and at least one button; buttons are one `UrlButton` or 1–2 `ReplyButton`s, same on every card; the reply context is `context.message_id`), or on Instagram `body` as text (carrying the reply context) followed by a generic template. `MessageCard(header, title, subtitle, default_url, buttons)`; `CardMedia(kind, url, poster_url=None)`, URL-only on both Platforms, built with `CardMedia.image(url=...)` or `CardMedia.video(url=..., poster_url=...)`; Instagram shows an image card's `url` and a video card's `poster_url`, opening the video on tap.
- `IMediaLibrary` capability on both Platforms (exported from `wappa.messaging` with `MediaFamily`, `UploadResult`, `MediaInfo` and `DeleteResult`), shaped like the Cloud API Media endpoints: `messenger.require_capability(IMediaLibrary)` gives `upload(source, family, *, mime_type=None, filename=None) -> UploadResult` (a local `Path` or raw `bytes`; a reusable `media_id`), `download(media_id) -> ReadResult[MediaBytes]`, `info(media_id) -> ReadResult[MediaInfo]` (URL, MIME type, size, SHA-256) and `delete(media_id) -> DeleteResult`. `MediaFamily` covers `image`, `video`, `audio`, `document` and `sticker`. WhatsApp uses the Media API for all four; Instagram uploads to `message_attachments` with `is_reusable` (attachment_id; a sticker as an image, bytes as multipart), downloads the attachment URL from the Meta CDN without credentials, and raises `UnsupportedOperationError` for `info` and `delete` (no endpoint). Send an uploaded file by its id with `send_image(stored.media_id, target)` on either Platform; pass inbound `webhook.message.media_id` to `download` unchanged.
- Instagram adapts `send_location` (text with name, address and a maps link), `send_contact` (one text block per contact card, validated with WhatsApp's `ContactCard` shape) and `send_sticker` (sent as an image: png/jpeg/gif; pass a list of renditions to serve WhatsApp's `.webp` too) instead of raising. Captions on image/video/document are sent as a follow-up text; `filename` is ignored, and `transcript` is middleware-only metadata on every Platform (no adapter sends it). Location and phone-number requests are the WhatsApp-only `IUserDataRequests` capability; Instagram does not provide it.
- `wappa.messaging` exports `ReplyButton`, `UrlButton`, `CardButton`, `MessageCard`, `CardMedia`, `ListSection`, `ListRow`, `InteractiveHeader` and `MediaRef`.
- `IMessenger.capability()`/`require_capability()` with `IMediaLibrary`, `ITemplateMessaging` (WhatsApp) and Instagram `ICommentControls`, `IConversationContentReader` and credential-free `IAttachmentMediaReader` (prefer `IMediaLibrary.download`).
- Neutral `wappa.domain.interactive` and `wappa.domain.results` (`CommentResult`, `ControlResult`, `OperationOutcome`).
- `InboxCredentialAccess` (trusted current-credential access) and `OutboundRuntime.messenger(inbox_ref)`.
- Instagram `changes` admission (`comments`, `live_comments`, `mentions`) and Instagram extension field registration with whole-batch admission.
- Shipped developer skills `wappa-instagram-apps`, `wappa-conversational-scores` and `wappa-runtime-state` (package data under `wappa/cli/skills/`, emitted by `wappa init` into `.claude/skills` and `.agents/skills` without overwriting existing folders).
- Inbox Connector contract `wappa.connections.IInboxConnector` ([ADR-0026](docs/adr/0026-inbox-connection.md)): `begin` / `complete` / `activate` / `disconnect`, one shape for every Platform. `InstagramConnector` (Unified Login: `assigned_instagram_accounts` discovery, per-field webhook subscription with separate `message_edit` verification) and `WhatsAppConnector` (Embedded Signup: shared WABA discovery from `debug_token`, one Inbox per phone number, WABA `subscribed_apps`) share a Meta Business Login core (`MetaLoginConfig`: one-use operator-bound state, code exchange with or without `redirect_uri`, `debug_token` scope readiness, `signed_request` verification), whose one `authorize` prelude both `complete` methods call before their own discovery. `activate` first checks that the grant and `InboxRef` belong to the connector's Platform (`ValueError` before any Graph call otherwise), then returns the Wappa-encrypted record (rotating a previous one): `ActivationResult.record` is an `ActiveInboxCredentialRecord` and `previous` a `CredentialRecord | None`. `InstagramSubscriptions(client_provider=..., graph_base=MetaLoginConfig.graph_base, app_id=...)` sends every `subscribed_apps` call through the same `graph_request` function as the Instagram Messenger, so `subscribe`, `subscribed_fields` and `unsubscribe` classify outcomes (accepted, rejected, indeterminate) the same way; `unsubscribe` is `True` only on Meta's `{"success": true}`.
- **DEV log handles.** In DEV, `SYSTEM_LOG_DIR` holds `current.log`, a symlink to the active log file, and `dev.pid`, which records the serving PID, the reloader or launcher PID, the PID to stop, the port and the log file. `wappa dev` prints both paths.
- **Payload capture.** `SYSTEM_CAPTURE_PAYLOADS=true` (DEV only; ignored with a warning elsewhere) writes each authenticated webhook body, redacted, to `logs/payloads/<platform>/<kind>-<timestamp>.json`. Capture errors never affect webhook handling. `tests/fixtures/meta_payloads/` holds promoted captures, and `tests/test_meta_payload_fixtures.py` replays each one under strict schema validation, so Meta payload drift fails a test instead of live traffic.
- **Read-only tools for repo maintainers** in `scripts/`, not shipped in the wheel:
  - `devlog.sh`: reads the server log from the last restart, optionally filtered by time or pattern;
  - `meta_inspect.py`: app subscriptions, `debug_token`, and an Instagram account's `subscribed_apps`; tokens are masked;
  - `redis_inspect.py`: one Inbox's keys and TTLs;
  - `promote_payload.py`: copies a capture into the fixtures and refuses one that holds secrets;
  - `env_keys.sh`: `.env` key names without values.
- **Repository guardrails.** CI (`.github/workflows/ci.yml`) runs ruff, ruff format, mypy, pytest with Redis, and gitleaks on every push and pull request. `.pre-commit-config.yaml` runs the same checks locally. Tests set dummy credentials in `tests/conftest.py` and no longer depend on a developer's `.env`. `tests/` is now linted, `tests/test_doc_claims.py` checks the paths, imports and code blocks in the agent-read docs, and `tests/test_backlog_index.py` keeps the backlog plan complete.

### Fixed

- Access tokens no longer reach log files. httpx logs every request URL at INFO, and Meta's OAuth calls carry secrets in the query (`oauth/access_token?client_secret=…&code=…`, `debug_token?input_token=…`, `?access_token=…`), so the connect flow wrote full tokens to the DEV log file and the console. Every handler `setup_logging` installs now runs `SecretRedactingFilter`, which masks `access_token`, `input_token`, `client_secret`, `appsecret_proof`, `fb_exchange_token`, `code` query values and full `Bearer` tokens as `[REDACTED]`. Rotate any token that a log file from 0.34 development builds may contain.
- The WhatsApp media upload MIME allow-list named the 3GP video type `video/3gp`; Meta's type is `video/3gpp`, which the payload builders already used. `MediaType` now lists `video/3gpp`.
- `WhatsAppMessenger.send_document(caption=...)` dropped the caption: the document payload builder had no caption parameter. `document.caption` now reaches the Cloud API, from the Messenger and from `POST /api/whatsapp/media/send-document`.
- WhatsApp status webhooks with `status: played` (the User played a voice note) were rejected with 400, so Meta retried and dropped them. `played` is now a `StatusWebhook` with `MessageStatus.PLAYED`; any status value Wappa does not model yet arrives as `SystemWebhook(UNSUPPORTED_EVENT)` with `META_SCHEMA_DRIFT field=WhatsAppMessageStatus.status=<value>` instead of a 400.
- An inbound WhatsApp document whose filename contains `..`, `/` or `\\` (e.g. `informe..final.pdf`) was rejected with 400. `WhatsAppDocumentMessage.filename` is now the untrusted name as delivered (`str | None`); hosts sanitize it before using it as a path.
- A tap on a WhatsApp carousel card's quick reply (and a Template quick-reply button) arrives as `type: button` with `button.payload`; `get_interactive_selection()` ignored it, so handlers saw plain text. It now returns the payload, and the button message reports `interactive_type = quick_reply`.
- Expiry handlers broke on 0.34 namespaces: the parsed namespace (`whatsapp__…`, `instagram__…`) was wrapped as a WhatsApp ID and raised. The helpers now take the `InboxRef` from `parse_inbox_ref_from_expired_key` (see Breaking changes).
- API-sent message notifications were published on a `whatsapp__` channel whatever the Platform; they now use the event's Platform.
- `OutboundRuntime.evict_inbox` could only evict WhatsApp Inboxes; it takes an `InboxRef`.
- `build_channel` / `build_pattern` defaulted to WhatsApp, so an Instagram subscriber silently got a `whatsapp__` pattern; they take an `InboxRef`.
- Detailed health reported the Inbox Directory (which serves every Platform) as WhatsApp config; it is now top-level `inbox_runtime`. The SSE debug publish takes `platform` from the body.
- Instagram echoes of cards and carousels logged `META_SCHEMA_DRIFT field=InstagramAttachmentPayload.generic`. The echoed generic template is now typed (`payload.generic.elements[]` with `title`, `subtitle`, `image_url` and `buttons`).
- A WhatsApp list reply to a row sent without a description was rejected with 400 (`list_reply.description` was required), so the selection never reached the handler. Inbound WhatsApp models also stopped enforcing send-side limits (button title 20, row title 24, caption 1024, text 4096, filename 255, location name/address, order text): Meta is the authority on what it delivers.
- An interactive reply type Wappa did not model was rejected with 400. A completed WhatsApp Flow (`nfm_reply`) now arrives typed (see Added); any other unmodelled type arrives as `InboundMessageWebhook(UNSUPPORTED)` with the raw reply under `unsupported.interactive`, Meta gets 200, and `META_SCHEMA_DRIFT field=InteractiveContent.type=<type>` is logged (strict mode raises).
- WhatsApp status webhooks carrying a new `pricing.subtype` (`free_tier`) were rejected with 400 and the delivery status was dropped. Meta's `account_update` field was also answered 400 "Unknown webhook field". Both are now accepted with 200 (see Upgrade watch-outs).
- **Privacy:** the WhatsApp system-event drift warning (`user_preferences`, `user_id_update`, `group_participants_update`) logged the raw values of undocumented Meta fields. It now logs field names only, and those three payloads also report through `META_SCHEMA_DRIFT`.
- A token rotated in the Host source kept failing with 401 after a restart: the Inbox Directory row stayed cached in Redis (sliding 60-minute TTL renewed on every message). Wappa now resets that cache at startup ([ADR-0022](docs/adr/0022-inbox-identity-and-directory.md)).
- A WhatsApp reply to a BSUID no longer fails when the User's phone is known: from a Meta test number the BSUID send was rejected with `131030` (allow-lists hold phones), and a one-address target could not fall back ([ADR-0022](docs/adr/0022-inbox-identity-and-directory.md)).
- The WhatsApp carousel sent BSUIDs in `to`; it now uses `recipient` like every other send.
- WhatsApp carousels with quick-reply cards were rejected with 400 (code 100, `cards.N` missing `type`). Every card now carries `"type": "cta_url"`, as Meta's carousel examples do for quick-reply cards too.
- `WhatsAppMessenger.mark_as_read(typing=True)` now sends the `typing_indicator`. It used to drop it silently, on the wrong assumption that a recipient ID was needed.
- **`wappa init` projects failed on their first send.** The scaffolded `master_event.py` built `DirectMessage(..., recipient_id=...)`, which `DirectMessage` rejects. It now builds the target from `self.inbox_ref` and `webhook.user.delivery_addresses()` and passes it to `mark_as_read` too. `tests/test_cli_templates.py` runs the scaffolded handler.
- The README quick-start sample passed a bare user ID to `send_text`, which raises `UnsupportedOperationError`. It and the "Recipient Contract" section now use `DirectMessage`. The README also names the 9 shipped examples and the real plugin classes (`PostgresDatabasePlugin`, `CORSPlugin`).
- The `init` example's `.env.example` claimed `LOG_LEVEL`, `API_VERSION` and `ENVIRONMENT` still worked with a deprecation warning. Wappa reads only `SYSTEM_LOG_LEVEL`, `META_API_VERSION` and `SYSTEM_ENVIRONMENT`, so the claim is removed.
- **Privacy:** JSON-cache output under `cache/`, including one User's name and phone number, had been committed by accident. It is untracked and `cache/` is gitignored. It remains in git history.

### Documentation

- `transcript` on `send_video` / `send_audio` is documented as middleware-only metadata: no adapter sends it, and middleware reads it from the `SendInvocation` (`IMessenger` docstrings, public contract, ADR-0025 contract map).
- `UserBase` field descriptions and its identity validator message are Platform-neutral ("address evidence"); ADR-0025 rule 7 records that WhatsApp-shaped field names are allowed per ADR-0028. The validator message text changed.
- **ADRs are consolidated, one per decision cluster, each stating its full current decision:** [ADR-0022](docs/adr/0022-inbox-identity-and-directory.md) Inbox identity, the Inbox Directory and Delivery Addresses; [ADR-0023](docs/adr/0023-inbound-webhooks.md) inbound webhooks (authentication, routing, admission, the Platform Registry, the echo filter, External Webhook Sources); [ADR-0024](docs/adr/0024-outbound-http-routes-and-transports.md) the messaging HTTP API, route capability groups and Template transport; [ADR-0025](docs/adr/0025-messenger-contract.md) the Messenger contract (one method per action, neutral types, one media seam, capabilities, ProfileReading); [ADR-0026](docs/adr/0026-inbox-connection.md) Inbox connection; [ADR-0027](docs/adr/0027-runtime-lifecycle.md) HTTP client ownership and graceful drain. New: [ADR-0028](docs/adr/0028-whatsapp-first.md) WhatsApp First (neutral contracts mirror WhatsApp's seams and features; structured limits are the minimum across Platforms, enforced at construction; other Platforms emulate). ADR-0005, ADR-0008 and ADR-0013 stay as they were. The absorbed ADRs 0001-0004, 0006, 0007, 0009-0012 and 0014-0021 are deleted and every reference points at the consolidated ADR; rule and decision numbers of the former one-method-per-action, messaging-HTTP-API and Inbox Connector ADRs are kept in ADR-0025, ADR-0024 and ADR-0026. `CODING_STANDARDS.md` now says a changed cluster decision updates its ADR. `CONTEXT.md` gains WhatsApp First and drops the `owner_id` mapping for `tenant`; `CONTEXT-MAP.md` gains API, Connections and External Webhooks; root `ARCHITECTURE.md` states the WhatsApp First rule, adds a Connections row and replaces its ADR digest with a pointer; the stale `TEMPLATE_API_GUIDE.md` and `META_PRODUCTION.md` are removed.
- `docs/public-contract.md`, `CONTEXT.md` (Media Library, Template Messaging, Inbox Connector, Interactive Selection), `ARCHITECTURE.md`, `wappa/messaging/ARCHITECTURE.md`, `README.md` and the [migration guide](docs/migration/instagram-conversation-contracts.md) describe the contract map: core methods, shared and Platform capabilities, and connection.
- `wappa/cli/ARCHITECTURE.md` and `wappa/webhooks/ARCHITECTURE.md` had been overwritten by uncommitted work with a copy of the messaging doc. Both were restored from git and their sections re-added.
- Backlog drafts for future work, in `docs/backlog/drafts/`: a `send_reaction` core method, a commerce capability (WhatsApp catalog alongside Instagram cards), `IInboxProfileReader` (the Inbox's own business profile, with typed optional fields), `IConversationEntryPoints`, a WhatsApp Flows PRD, a WhatsApp Calling PRD, and Inbox Connector follow-ups.
- `AGENTS.md` is the single agent guide for every coding agent (Claude Code reads it when no `CLAUDE.md` exists): a short description plus pointers. `CLAUDE.md` is removed. Coding, test, docs and commit rules moved to `CODING_STANDARDS.md`, and `CONTRIBUTING.md` points there.
- New `wappa/api/ARCHITECTURE.md` (router tree, Inbox selection, capability gates, request models). `wappa/messaging/ARCHITECTURE.md` gains "Changing a Messenger method", `wappa/webhooks/ARCHITECTURE.md` gains "Adding a message family or event lane", and the root new-Platform checklist names its files. Stale statements were corrected (Instagram reactions are messages, echoes are `OutboundEchoWebhook`, the cache namespace is the same on every Platform).
- The Unified Login docs (public contract, `wappa-instagram-apps` skill, live test plan) say Meta sends no deauthorize callback for Unified Login grants. Unified Login issues `SYSTEM_USER` tokens, which are revoked through the business portfolio or the Host's connector.

### Known gaps

- **No reaction send.** `send_reaction` is missing from the core contract; ADR-0025 records it as a known gap.
- **Unverified live:** the Instagram Conversations API history read and Live-video comments.
- **Connector limits.** WhatsApp disconnect works per WABA, so it stops webhooks for every number in that WABA. Phone-number `/register` (two-step PIN) is not called. `begin` only returns a redirect, so a credential-entry step (Telegram bot token) is not built.
- **Live certification.** Gate A (WhatsApp and Instagram parity: text, media, voice, interactive, cards, carousels, `/read`, comments, private replies, mentions, post and comment reads, forwards, reactions, `played`) and Gate B (Unified Login connect, reconnect, cancel and multi-Inbox routing) passed live on 2026-11-05. Still open:
  - B-08, a Creator account;
  - Gate C, the Symphonai live run.

### Verification

`uv run pytest -q` → 1300 passed, 1 skipped (random order); `uv run mypy wappa` clean (388 files); `uv run ruff check .` clean; shipped skill lint 0 errors / 0 warnings.

## [0.33.0] - 2026-11-02

Recognizing a close signal is now part of the pluggable `SSEHub` contract.

### Changed

- **Breaking for custom SSE hubs:** `SSEHub` requires `close_reason(item) -> str | None`. It returns the reason (`backpressure_gap`, `shutdown`, or a custom hub's own reason) when a queued item is that hub's stream-close signal, and `None` otherwise. A hub without it no longer satisfies `SSEHub`, and `SSEEventsPlugin` rejects it with `TypeError`. Decorators should delegate to their local hub. The built-in `SSEEventHub` already had the method, so it satisfies the contract unchanged.
- The `/api/sse/events` stream asks the hub through `close_reason()` whether to end, instead of inferring closure from the queue item's shape. Any queued item that is not an event envelope still ends the stream.

## [0.32.0] - 2026-11-02

FastAPI 0.162 compatibility and corrected public router authentication.

### Changed

- Upgrade FastAPI from 0.137.0 to 0.162.0 and bound compatibility to `>=0.162.0,<0.163.0`. Host Applications must refresh their own lockfiles.
- Use `include_router()` for cron monitoring routes added at startup. Remove the callback contract test's recursive traversal of FastAPI's private router nodes in favor of `iter_route_contexts()`.

### Fixed

- Public router exemptions now combine include and router prefixes, matching FastAPI's mounted paths. Exemptions stop at path-segment boundaries, so `/public/hooks` does not exempt `/public/admin` or `/public/hooks-admin`. Other mounts of the same router stay protected.

## [0.31.0] - 2026-10-09

Outbound phone evidence excludes proven BSUID digit echoes while preserving canonical identity and provider acceptance.

### Fixed

- `MessageResult.recipient_phone` becomes `None` when it matches the complete numeric suffix of a valid regular BSUID, Parent BSUID, or BSUID-valued resolved recipient on the same result. Both factories and direct construction enforce the rule; comparison tolerates outer whitespace and a leading `+` on the phone. Distinct phones retain their original value, and alphanumeric or invalid identifiers do not manufacture an echo.
- `TemplateTransportResult.returned_phone_number` receives the sanitized phone through the existing result projection. The requested Delivery Address, endpoint, routing reason, Message ID, and accepted outcome remain intact. The typed provider response retains its original `wa_id`; no discovery, address rewrite, or retry is added.

## [0.30.1] - 2026-09-28

Production incident remedies for the WhatsApp webhook boundary and the Redis user-namespace scan.

### Fixed

- **`system.previous_user_id` events no longer reject the whole delivery.** Meta emits `system.previous_user_id` on `user_changed_user_id` system messages; `SystemContent`'s strict schema (`extra="forbid"`) had no field for it, so every such update failed parsing with `WHATSAPP_WEBHOOK_CONTRACT_DRIFT` and surfaced HTTP 400 to Meta. The field is now declared, optional, and BSUID-validated like `user_id`/`parent_user_id`, and `WhatsAppSystemMessage.previous_user_id` maps it into `SystemEventDetail.previous_user_id` alongside `current_user_id`. Genuinely unknown system fields still reject.
- **Blank contact profile names are accepted as absent.** A whitespace-only `contacts[].profile.name` no longer fails the delivery; it normalizes to `None` — the already-supported absent-name shape — while BSUID, phone number, and username are unchanged. Nonblank names are preserved verbatim. The `@username` display fallback in `UserBase.get_display_name()` stays display-only: hosts that adopt a real stored name see `profile_name=None`, i.e. no offer.
- **User-namespace scans skip host mutation locks.** Hosts serialize User-cache mutations with a short-lived Redis string at `{inbox}:user:{user_id}:symphonai:mutation`, inside the `{inbox}:user:*` namespace `InboxCache._find_by_field` SCANs. The reader HGETed it, logging a `WRONGTYPE` error per live lock per scan. `is_user_mutation_lock_key` names the shape and the scan skips it before `HGET`; per-key command errors keep degrading to a miss per the ops contract, and unexpected/connection errors still propagate.

## [0.30.0] - 2026-09-15

Wappa can now send WhatsApp Authentication Templates. `authentication_method` was required of every caller and then discarded, so the send was assembled without the OTP button component Meta requires and the provider rejected it — no Authentication Template with a button could be delivered by any path. The method now reaches the WhatsApp handler, which emits `body` and `button` together with `sub_type: "url"`, a string `index`, and the code repeated from the body, because the generated button URL ends in `&code=otp{{1}}` and Meta refuses a send that leaves that placeholder unsupplied. All three methods ship: Meta rewrites an `OTP` button to a `URL` button at template creation, so `copy_code`, `one_tap`, and `zero_tap` send the identical payload and differ only in how the recipient's device consumes the code.

### Added

- `authentication_method` and `authentication_button_index` on `IMessenger.send_text_template`, `MessengerPipeline`, `WhatsAppMessenger`, and `WhatsAppTemplateHandler`, so the OTP button is expressible rather than hard-coded in one handler.
- `TemplateInfo.authentication_method` and `TemplateButton.authentication_method`, resolving the OTP method from a template read back through Wappa. Meta commonly returns `otp_type: null` beside the rewritten `URL` button, so both read the flat field first and fall back to parsing `otp_type=` out of the generated button URL; an unmarked button resolves to `None` rather than a guess.
- `TemplateButton.otp_type`, and `_TemplateTransportRequest.authentication_code` for the code a request puts in both components.
- A golden Meta wire fixture for the copy-code send (`tests/fixtures/meta/v25.0/authentication_copy_code_request.json`) and `tests/test_authentication_template_otp.py`, which assert the emitted `components` array rather than that the call succeeded.

### Fixed

- Authentication Templates emit the `button` component Meta requires beside `body`, with both parameters filled from one value at a single call site so the code the person reads and the code "Copy code" writes to the clipboard cannot drift.
- `authentication_method` now provably changes the outgoing request instead of being validated and dropped.

### Changed

- An Authentication Template transport request is refused locally, instead of at Meta, when it carries anything other than exactly one body parameter, binds that parameter by name, or attaches a media or location header. A BSUID address was already refused and still is.
- `WhatsAppTemplateHandler.send_text_template` refuses an `authentication` send with no method, an unknown method, or a method on a non-authentication Template, rather than sending a payload Meta would reject.

## [0.29.0] - 2026-09-13

Runtime scope is now consistently qualified by Platform and Inbox wherever it leaves a known Platform boundary. This closes same-native-ID collisions in SSE, Redis Pub/Sub, expiry, and scheduled work while retaining legacy raw WhatsApp identifiers at their existing compatibility boundaries. Explicit Inbox credentials now propagate the configured Meta Graph endpoint throughout outbound construction, and generated explicit-routing projects include the configuration and host-directory seams they need from the start.

### Added

- `InboxRef.from_cache_namespace()` and `parse_inbox_ref_from_expired_key()` for recovering qualified runtime identity from Wappa-owned cache keys.
- Platform-qualified Inbox filtering for SSE subscriptions and Redis Pub/Sub channels.
- `CronPlugin.add_cron(..., inbox_ref=...)` and `CronEvent.inbox_ref`, with the existing `inbox_id` argument retained as a WhatsApp compatibility convenience.
- `wappa init --inbox-routing explicit` scaffolding, including an explicit environment template, Inbox Directory source stub, and explicit application template.
- A bounded LRU Messenger construction cache, preventing unbounded growth for Hosts with a large number of active Inboxes.
- Pluggable `SSEHub` transport contracts: `SSEEventEnvelope`, delivery and
  publish results, typed metrics, local envelope delivery, and injectable hub
  factories or instances on `SSEEventsPlugin`.

### Changed

- Expiry, cron, API-event, and external-webhook dispatch contexts carry an `InboxRef` when Inbox scope is known; System work remains Inbox-free instead of using a fabricated Inbox ID.
- Explicit Inbox runtime construction and detailed health reporting now use the configured Meta Graph API version and base URL rather than legacy process-level settings.
- Webhook status reports registered Platform routes separately from installed adapter capabilities, keeping route registration independent of a single Platform implementation.
- Rate-limit scope resolution first uses the trusted Inbox Execution Context; payload-routed callbacks can instead use client-IP or Host-defined post-authentication policy.
- Public docs, examples, templates, and architectural language describe Platform capability seams without baking application context into webhook URL shape.
- SSE queue overflow now closes only the affected stream with a visible
  delivery gap, allowing EventSource reconnection instead of silently
  continuing after data loss.

### Fixed

- Logging context uses `I` for Inbox and accepts historical `T` records when parsing, removing stale tenancy vocabulary without breaking existing log consumers.
- Corrected the v0.28 external-webhook URL in the changelog and removed stale configuration and route examples from generated documentation.

## [0.28.0] - 2026-09-13

External webhooks are now Inbox-independent. Their canonical route is `POST /webhook/{provider}`; `POST /webhook/{provider}/{webhook_id}` is an explicit opt-in for opaque provider route identifiers, not Inbox identity. Hosts resolve runtime context after authentication and parsing from trusted payload evidence, request headers, or middleware state through `IExternalWebhookContextResolver`.

### Upgrade watch-outs

- **Remove Inbox IDs from external webhook URLs.** Replace `/webhook/{provider}/{inbox_id}` with the ID-less route. If a provider requires an identifier in its configured URL, use `WebhookPlugin(..., include_webhook_id=True)` and treat it as an opaque `webhook_id`.
- **Move context resolution into the Host boundary.** Implement `IExternalWebhookContextResolver` when a webhook needs an Inbox or user-scoped capability. It runs only after processor authentication and parsing, and may derive context from verified headers, payload data, or `request.state` set by trusted middleware. It must not infer context from URL construction.
- **External event payloads changed.** `ExternalWebhookEvent` no longer includes `inbox_id` or `user_id`; it includes only optional `webhook_id`. Handlers receive Inbox, Messenger, User, and Cache capabilities only when the resolver returns a corresponding trusted context.

The decision and design constraints are recorded in [ADR-0023](docs/adr/0023-inbound-webhooks.md); host migration steps are in [the migration guide](docs/migration/external-webhook-context-resolution.md).

## [0.27.0] - 2026-08-30

One Host Application can now run many WhatsApp Inboxes under one Meta App without treating `WP_PHONE_ID`, `WP_BID`, or `WP_ACCESS_TOKEN` as application-wide runtime identity. The Host owns its durable Inbox schema; Wappa owns the canonical credential record, encryption, the system-scoped Inbox Directory, payload routing, WABA membership checks, HTTP Inbox selection, and per-Inbox runtime construction. Every decision below was settled in the [2026-08-29 grilling session](docs/grill-me-sessions/260829_wappa-v0.27.0-multi-inbox-hardening.md) and is recorded in [ADR-0023](docs/adr/0023-inbound-webhooks.md) and [ADR-0022](docs/adr/0022-inbox-identity-and-directory.md). Host steps are in [docs/migration/v0.27.0-multi-inbox.md](docs/migration/v0.27.0-multi-inbox.md).

**This release contains breaking changes.** It replaces the first, unreleased v0.27 candidate (a Host-defined `IInboxCredentialStore`, a prescribed `wappa_inboxes` table, plaintext cache rows, an `auto` routing mode, and a verify-token HMAC helper) with the settled contract.

### Upgrade watch-outs

- **Meta callback authentication is mandatory.** Set `META_APP_SECRET` next to `WP_WEBHOOK_VERIFY_TOKEN` in every environment that mounts the callback, including development. Wappa verifies the exact POST body bytes against `X-Hub-Signature-256` before it parses JSON, reads the directory, or schedules work; a missing, malformed, or mismatched signature answers a generic `401`. The verify token is used only for the GET challenge. There is no bypass.
- **Change the Meta callback URL** to `GET + POST /webhook/inboxes/whatsapp`. The per-Inbox route and the verify-only route return 404 with no alias or redirect. Rollback needs both the previous package and the previous URL.
- **Pick one Inbox Routing Mode.** `legacy` (default) requires the complete `WP_ACCESS_TOKEN` + `WP_PHONE_ID` + `WP_BID` bundle and rejects an `IInboxDirectorySource`. `explicit` requires an `IInboxDirectorySource` and `SYSTEM_TOKEN_ENC_KEY` and rejects every legacy variable. `auto` no longer exists; mixed configuration fails at build time with `InboxConfigurationError`.
- **Public imports removed:** `IInboxCredentialStore`, `InboxCredentials`, `DatabaseInboxCredentialStore`, `WappaInbox`, `SettingsInboxCredentialStore`, `select_inbox_credential_store`, `Wappa(inbox_credential_store=...)`, `with_inbox_credential_store`, `OutboundRuntime.invalidate_inbox_credentials`. Explicit-mode Hosts implement `IInboxDirectorySource` and call Wappa's commands instead.
- **Table Cache construction uses `context_id`.** `RedisTable`, `MemoryTable`, `JSONTable`, and `ICacheFactory.create_table_cache` take `context_id` (positional calls keep working; `inbox_id=` / `inbox=` raise `TypeError`). Stored keys are unchanged, so no Redis migration is needed. Other cache families keep `inbox_id`.
- **`X-Wappa-Inbox-ID` selects, it does not authorize.** Inbox-dependent `/api/whatsapp/*` routes resolve one Inbox Execution Context per request; in explicit mode the header is required (400 without it), an unknown or inactive Inbox is 404, and a directory outage is 503. Local-only routes (limits, validation, root health, docs) ignore the header entirely.
- **`/interactive/send-complex-buttons` and `/interactive/send-menu-list` are gone** from the HTTP contract; the demonstrations live in `wappa_full_example/app/handlers/interactive_demos.py`.
- **Error mappings changed:** an authenticated unknown payload Inbox is `400` (was `401`), a non-object JSON root is `400` (was `503`), and credential failures during Messenger construction surface as typed directory errors (503), never as an unclassified 500.
- **Account-scoped handlers must be idempotent.** Delivery stays at least once; Meta retries, batch splitting, and WABA fan-out can repeat one Platform event. Wappa defines no delivery fingerprint.

### Why the contract looks like this

Every breaking change below is the recorded outcome of a design question in the [2026-08-29 grilling session](docs/grill-me-sessions/260829_wappa-v0.27.0-multi-inbox-hardening.md). The reasoning matters more than the diff, so the load-bearing decisions are linked directly:

- **The Host adapts, it does not extend.** [§1d](docs/grill-me-sessions/260829_wappa-v0.27.0-multi-inbox-hardening.md#1d-is-iinboxcredentialstore-still-a-public-extension-point) removed `IInboxCredentialStore` as a public extension point because an object with the right method names could silently change active-Inbox rules, WABA fan-out, cache renewal, error semantics, and invalidation. The Host's one adaptation point is now `IInboxDirectorySource`, which maps durable Host data into Wappa's canonical records; Wappa owns everything after that boundary. The internal resolver port survives only because Wappa itself has two production policies — legacy settings and the directory — and no caller should branch on boot mode. [§10b](docs/grill-me-sessions/260829_wappa-v0.27.0-multi-inbox-hardening.md#10b-where-does-inboxdirectory-live) places the directory in the domain, and [§1c](docs/grill-me-sessions/260829_wappa-v0.27.0-multi-inbox-hardening.md#1c-who-is-allowed-to-mutate-the-redis-directory) makes Wappa the only writer.
- **The directory is a cache over the Host's authority, not a second source of truth.** [§3a](docs/grill-me-sessions/260829_wappa-v0.27.0-multi-inbox-hardening.md#3a-is-redis-the-runtime-authority-or-only-a-cache) keeps the Host database durable authority and Redis a read-through cache; [§3c](docs/grill-me-sessions/260829_wappa-v0.27.0-multi-inbox-hardening.md#3c-do-credential-records-expire-by-ttl) sets the sliding TTL for active rows against the fixed, never-renewed TTL for negative rows, so an outage can never harden into a cached "no". [§1b](docs/grill-me-sessions/260829_wappa-v0.27.0-multi-inbox-hardening.md#1b-can-the-inbox-directory-reuse-itablecache) reuses `ITableCache` under System Scope rather than inventing a directory-specific Redis adapter, and [§1i](docs/grill-me-sessions/260829_wappa-v0.27.0-multi-inbox-hardening.md#1i-does-context_id-replace-inbox_id-across-every-cache-contract) confines the `context_id` rename to Table Cache alone — which is why stored keys are byte-identical and no Redis migration is needed.
- **Tokens are encrypted, never hashed.** [§2e](docs/grill-me-sessions/260829_wappa-v0.27.0-multi-inbox-hardening.md#2e-what-is-wappas-secret-at-rest-boundary) settles the secret-at-rest boundary: Meta needs the exact bearer value, so a hash is disqualified by definition, `SecretStr` masks without encrypting, and the accepted representation is a Wappa-created `EncryptedSecretEnvelope` binding format version, Platform, `inbox_id`, and field name — so ciphertext moved between Inbox rows fails validation even under the same key. [§2e.1](docs/grill-me-sessions/260829_wappa-v0.27.0-multi-inbox-hardening.md#2e1-how-does-system_token_enc_key-rotate) defines the MultiFernet rotation ring, and [§2d](docs/grill-me-sessions/260829_wappa-v0.27.0-multi-inbox-hardening.md#2d-may-several-inboxes-share-one-access-token) allows several Inboxes to share one physical token while each keeps its own ciphertext. [§2c](docs/grill-me-sessions/260829_wappa-v0.27.0-multi-inbox-hardening.md#2c-is-inbox_id-globally-unique-or-unique-only-within-a-platform) is why identity is qualified as `InboxRef(platform, inbox_id)`: `inbox_id` is unique only inside one Platform.
- **Callback authentication has no escape hatch.** [§5d](docs/grill-me-sessions/260829_wappa-v0.27.0-multi-inbox-hardening.md#5d-should-hmac-validation-be-optional-in-development) rejected a development bypass outright — including a `DISABLE_WEBHOOK_SIGNATURE_VALIDATION` setting — so tests and local tools sign exact bytes instead of weakening the runtime. [§5c](docs/grill-me-sessions/260829_wappa-v0.27.0-multi-inbox-hardening.md#5c-what-are-the-signature-failure-semantics) makes every signature failure a generic `401` that reveals nothing, and [§5a](docs/grill-me-sessions/260829_wappa-v0.27.0-multi-inbox-hardening.md#5a-is-one-wappa-process-bound-to-one-meta-app-secret) binds one process to one Meta App Secret. [§4d](docs/grill-me-sessions/260829_wappa-v0.27.0-multi-inbox-hardening.md#4d-must-a-phone-scoped-payload-prove-waba-membership) is why an authenticated payload must still prove WABA membership, and [§4a](docs/grill-me-sessions/260829_wappa-v0.27.0-multi-inbox-hardening.md#4a-should-account-lookup-use-a-composite-identity) is why the account lookup is composite.
- **`X-Wappa-Inbox-ID` selects scope; it authorizes nothing.** [§6b](docs/grill-me-sessions/260829_wappa-v0.27.0-multi-inbox-hardening.md#6b-does-the-header-authorize-the-operation) states it plainly — a valid Inbox ID in a header is not a security credential, and the Host or the auth plugin must authorize the caller before Wappa resolves the Inbox Execution Context. [§6c](docs/grill-me-sessions/260829_wappa-v0.27.0-multi-inbox-hardening.md#6c-should-local-only-routes-ignore-or-reject-a-supplied-header) is why local-only routes ignore the header rather than rejecting it, and [§6f](docs/grill-me-sessions/260829_wappa-v0.27.0-multi-inbox-hardening.md#6f-should-the-two-example-interactive-send-endpoints-remain-production-routes) is why the two demonstration interactive endpoints left the HTTP contract.
- **One authority per process, chosen at build time.** [§7c](docs/grill-me-sessions/260829_wappa-v0.27.0-multi-inbox-hardening.md#7c-what-happens-when-both-a-complete-environment-bundle-and-an-explicit-directory-are-configured) replaced the earlier "warn and prefer the directory" behaviour with a hard startup failure, and deleted `auto`: a warning still leaves two credential sources configured and invites an operator to believe the environment token is live. The selected mode is visible in health output.
- **Failures are typed, intake is atomic, and delivery is at least once.** [§9a](docs/grill-me-sessions/260829_wappa-v0.27.0-multi-inbox-hardening.md#9a-what-status-codes-distinguish-caller-errors-from-infrastructure-errors) separates caller errors from infrastructure errors, which is why an authenticated unknown Inbox became `400` and a non-object JSON root stopped being `503`. [§9d](docs/grill-me-sessions/260829_wappa-v0.27.0-multi-inbox-hardening.md#9d-should-a-credential-store-failure-during-messenger-construction-remain-an-unclassified-500) is why credential failures during Messenger construction surface as typed directory errors instead of an unclassified 500. [§9b](docs/grill-me-sessions/260829_wappa-v0.27.0-multi-inbox-hardening.md#9b-must-a-batched-webhook-remain-all-or-nothing-before-scheduling) makes a batched webhook all-or-nothing before anything is scheduled, and [§9c](docs/grill-me-sessions/260829_wappa-v0.27.0-multi-inbox-hardening.md#9c-should-wappa-deduplicate-waba-fan-out-deliveries) explicitly declines deduplication in this release: batch positions shift when Meta repackages a delivery and a payload hash can collapse two legitimate identical events, so delivery identity gets its own design before Wappa claims a stable identifier. Until then, account-scoped handlers must be idempotent on Platform-supplied identifiers.

### Added

- `InboxRef(platform, inbox_id)` and `PlatformAccountRef(platform, platform_account_id)`: qualified, immutable, orderable identity with one Wappa-owned `cache_namespace`. WhatsApp keeps its raw `phone_number_id` namespace so deployed keys stay readable; other Platforms are qualified.
- `SYSTEM_SCOPE = "__system__"`, `create_system_table_cache(cache_type)`, and `validate_context_id` in `wappa.persistence`; Table Cache is the only family that accepts a general `context_id` (System, Host-defined, or Inbox scope; siblings, no fallback).
- Canonical credential records: `WhatsAppActiveInboxCredentialRecord`, `WhatsAppInactiveInboxCredentialRecord`, the `InboxCredentialRecord` union, `EncryptedSecretEnvelope`, `parse_inbox_credential_record`, `dump_record_for_storage`, and the `PlatformAccountActiveIndexRecord` / `PlatformAccountEmptyIndexRecord` index rows.
- `CredentialCodec` (Fernet, MultiFernet reads) with context-bound envelopes that bind format version, Platform, `inbox_id`, and field name; `SYSTEM_TOKEN_ENC_KEY` plus the optional `SYSTEM_TOKEN_ENC_PREVIOUS_KEYS` ring; previous-key cache reads are rewritten under the active key.
- `InboxCredentialService` (`create_active_record`, `rotate_active_record`, `create_inactive_record`, `rotate_encrypted_record`) and `InboxDirectory` (`resolve_credentials`, `list_inbox_refs_for_platform_account`, `refresh_inbox`, `deactivate_inbox`, `subscribe_evictions`, `check_health`) over the Wappa-owned `InboxDirectoryTable`: read-through loading, 60-minute sliding TTL for active rows and indexes, fixed 60-minute negative rows, monotonic `credential_version` rules with compare-and-set, primary-before-index writes with retry repair, and Messenger eviction.
- `IInboxDirectorySource`, the one Host adaptation point, and the internal `IInboxCredentialResolver` with `SettingsInboxCredentialResolver` (legacy) and `InboxDirectory` (explicit) as Wappa's only implementations.
- `InboxRoutingMode` (`legacy` / `explicit`), `SYSTEM_INBOX_ROUTING_MODE`, `Wappa(inbox_routing=..., inbox_directory_source=..., meta_application_config=...)`, `WappaBuilder.with_inbox_routing/with_inbox_directory_source/with_meta_application_config`, and `app.state.inbox_runtime` (`InboxRuntimeConfiguration`).
- `MetaApplicationConfig` with one configuration source (explicit or `META_APP_SECRET` / `WP_WEBHOOK_VERIFY_TOKEN` / `META_API_VERSION` / `META_BASE_URL`); `MetaCallbackAuthenticator` and `SIGNATURE_HEADER`.
- WABA membership proof for phone-scoped changes, validated reverse-index fan-out with one synchronous source repair, empty-account 400, and repair-failure 503.
- `InboxExecutionContext` and `get_inbox_execution_context`; `INBOX_ID_HEADER`; the documented route capability matrix.
- `DispatchContextBuilder` / `RuntimeCapabilities` shared by webhook, API-message, cron, and External Webhook Source paths; `WappaEventHandler.require_database()`.
- Typed failures: `InboxDirectoryError`, `InboxConfigurationError`, `InboxNotFoundError`, `InboxMembershipError`, `InboxDirectoryUnavailableError`, `InboxCredentialIntegrityError`, `InboxMutationConflictError`.
- Test groups for identity collisions, Table Cache scope and key compatibility, codec binding and rotation, directory conformance on memory/JSON/Redis, HMAC ordering and generic failures, object-root validation, membership and fan-out, mixed-batch admission, the full HTTP route matrix, routing-mode startup matrix, health redaction, and public imports; plus the gap-closing pass below (`uv run pytest -q` → 920 passed, 1 skipped).
- `cryptography` dependency.

### Changed

- The WhatsApp callback authenticates raw bytes first; the route reads the body once and the controller maps typed failures to the settled status matrix (401 signature, 403 GET token, 400 unroutable/unknown/mismatch/empty, 503 unavailable, 500 defect).
- Payload routing binds each delivery to an `InboxRef`, `PlatformAccountRef`, and already-resolved credentials; the Inbound Runtime builds every Dispatch Context (binding and resetting identity per item) before scheduling the batch, and the dead single-delivery `accept_webhook` entry point is removed.
- `MessengerFactory` keys by `InboxRef`, accepts pre-resolved credentials, subscribes to directory evictions, and lets directory errors propagate typed.
- `OutboundRuntime`, `WappaContextFactory`, expiry helpers, and `APIEventDispatcher` resolve credentials and `db` / `db_read` through the shared builder.
- `InboxMiddleware` only isolates the ambient logging context per request; Inbox selection moved to route dependencies.
- Template info routes derive the WABA from the selected Inbox's record; media download resolves the media object with the selected Inbox token.
- Health reports `inbox_routing_mode`, directory configuration and reachability, the legacy default Inbox, and Meta callback readiness, with every secret redacted.
- `WhatsAppWebhookProcessor.validate_webhook_signature` requires `app_secret` and never reads the verify token.
- `db` and `db_read` keep their names and remain optional; v0.27 does not claim enforced read-only replica sessions, replica cooldown, or configurable fallback (separate PostgreSQL plugin work), nor Instagram credentials, exactly-once delivery, or multi-Meta-App support.

### Documentation

- `CONTEXT.md`, `ARCHITECTURE.md`, `wappa/persistence/CONTEXT.md`, `wappa/persistence/ARCHITECTURE.md`, `AGENTS.md`, and `CLAUDE.md` use Platform language and describe qualified identity, routing modes, callback authentication, the Inbox Execution Context, and the Inbox Directory dependency direction.
- [ADR-0023](docs/adr/0023-inbound-webhooks.md) amended; [ADR-0022](docs/adr/0022-inbox-identity-and-directory.md) added; ADR-0022 and ADR-0023 carry superseding banners.
- `docs/public-contract.md` rewritten for identity, modes, the directory, commands, encryption and rotation, Meta configuration, the header matrix, typed errors, `db` / `db_read`, and cutover. `docs/migration/v0.27.0-multi-inbox.md` added.
- `.env.example`, the CLI env template, every example `.env.example` and startup validation, the README, and the Railway guide teach the two modes and the callback secrets without mixing them.
- `CONTRIBUTING.md` added — the README linked to it but it did not exist. It documents setup, the five gates, code and test conventions, the documentation graph, and the commit format.
- The full example's README stated the wrong license (MIT); Wappa and its examples are Apache 2.0. `AuthPlugin.md` no longer conflates `DEFAULT_EXCLUDES` with the public-route-prefix seam that actually exempts `/health` and `/webhook/...`. `Owner`, `tenant`, and `provider` language removed from the plugin READMEs, `Architecture.md`, `CONTEXT-MAP.md`, ADR-0005, and the Redis PubSub example, whose documented notification fields and messenger construction had drifted from the code.
- Every example that names `WP_ACCESS_TOKEN` now also names `META_APP_SECRET`, and the Docker Compose and Railway files use the current `SYSTEM_*` and `META_*` variable names. Two zero-byte example READMEs were written; `wappa/persistence/redis/README.md`, which documented an entirely different codebase and shipped in the wheel, was deleted.

### Verification

`uv run ruff check .` clean, `uv run ruff format --check .` clean, `uv run mypy wappa` clean, `uv run pytest -q` → 920 passed, 1 skipped (Redis-backed cases run against a live server when reachable), `git diff --check` clean, `uv build` produced `wappa-0.27.0-py3-none-any.whl` and `wappa-0.27.0.tar.gz`, and a clean-venv install of the wheel imports the public surface and reports `0.27.0`. The operator confirmed the published-package gate on 2026-11-06 and requested deletion of the completed v0.27 backlog series. Historical release reports remain available in git history.

## [0.26.3] - 2026-08-23

Meta omits `ctwa_clid` from the `referral` object for WhatsApp Status ad placements. Wappa's provider-facing schema declared it required, so every message arriving from a Status ad failed validation before a universal webhook could be built — the processor reported "Failed to create universal webhook" and the message never reached the host application. Only the click ID is now nullable; the referral and its `source_id` survive, so ad context and analytics keep working and downstream attribution can filter on a null click ID.

### Fixed
- **`AdReferral.ctwa_clid` is now `str | None`** in `wappa/webhooks/whatsapp/base_models.py`. It was `Field(...)` — required — which contradicted the universal `AdReferralBase`, where `click_id` has always been optional. The strict provider layer was the only thing rejecting these payloads.
- **The emptiness guard split in two.** `source_id` keeps its required non-empty check; `ctwa_clid` passes `None` through and rejects only a present-but-blank string. Previously one shared validator applied the required-ID rule to both fields.

### Documentation
- `docs/public-contract.md` records that Click-to-WhatsApp referrals accept an omitted `ctwa_clid`, and that such referrals reach handlers as `click_id=None`.

### Verification
`uv run ruff check .` clean, `uv run ruff format --check` clean, `uv run pytest` → 533 passed. The new case parses a production-shaped Status-ad payload end to end and asserts `referral.ctwa_clid is None`, `get_ad_context() == ("status-ad-123", None)`, and `webhook.ad_referral.click_id is None`.

## [0.26.2] - 2026-08-06

Default Graph API version moves to **v26.0** (released 2026-07-29, current latest). v26.0 ships no WhatsApp Cloud API changes — its removals are Commerce Order Management, the Instagram Explore placement, Delivery Estimate fields, and legacy protocol behaviors, none of which Wappa touches; the WhatsApp-related additions are Marketing API Status Ads. Messaging, media, Template, and webhook payload contracts are unchanged, so this is a default bump with no code path affected. Override with `META_API_VERSION` as before.

### Changed
- **`META_API_VERSION` defaults to `v26.0`** (was `v25.0`) in `wappa/core/config/settings.py`. Applied consistently across the scaffolding template (`cli/templates/env.template`), the root `.env.example`, all six example `.env.example` files, and `wappa_full_example/docker-compose.yml`.

### Fixed
- **`json_cache_example/README.md` documented an unreadable env block.** It listed `WHATSAPP_API_URL=https://graph.facebook.com/v18.0` plus `WHATSAPP_ACCESS_TOKEN` / `WHATSAPP_PHONE_NUMBER_ID` / `WHATSAPP_WEBHOOK_VERIFY_TOKEN` / `WHATSAPP_WEBHOOK_SECRET` and `LOG_LEVEL` / `ENVIRONMENT` — names `settings.py` stopped reading in 0.19.0. Anyone copying that block got empty credentials and a failed startup validation. Rewritten to the canonical `META_BASE_URL` / `META_API_VERSION` / `WP_*` / `SYSTEM_*` names.

### Verification
`uv run ruff check .` clean, `uv run ruff format --check` clean, `uv run pytest` → 532 passed. The Template transport golden contract stays pinned to its v25.0-captured fixtures — v26.0 changes no `marketing_messages` payload shape, and re-labelling fixtures without re-capturing them against a live v26.0 response would misstate their provenance; the pinning rationale is now recorded in the test's docstring.

## [0.26.1] - 2026-08-05

Security follow-up to 0.26.0. Ejecting Wappa's send routes left three unauthenticated routes that still mutate: `DELETE /media/{id}`, and the `/state-handlers/*` pair that reads, overwrites, and deletes the cached conversational state of **any** recipient named in the request. Route grouping is now drawn along what an unauthenticated caller could *do*, not along whether a route sends a message. Recorded in [ADR-0024](docs/adr/0024-outbound-http-routes-and-transports.md).

Standalone applications are unaffected — the surface is byte-identical. Hosts already passing `include_outbound_transport_api=False` get the wider gating automatically, without changing a line.

### Added
- **`Wappa(route_profile="embedded")`** — one argument that omits every route which sends a message, destroys a media asset, or rewrites a recipient's cached state. Reads, lookups, media upload, Template info, webhooks, health, and every `wappa.messaging` service stay. `"standalone"` (the default) is the surface a standalone Wappa app has always had.
- **Three further capability flags**, each defaulting to `None` ("take it from the profile") and each overriding the profile when named: `include_media_management_api` (`DELETE /media/{id}`), `include_media_upload_api` (`POST /media/upload`), `include_state_handler_api` (`/state-handlers/*`). Available on `Wappa`, `WappaCorePlugin`, and `create_whatsapp_router`.
- `WhatsAppRouteProfile` and `WhatsAppRouteCapabilities` in `wappa.api.routes.whatsapp.route_families`, plus `RouteFamily`, which mints one router per capability group from a single prefix/tag/response description.

### Changed
- **`include_outbound_transport_api=False` now implies the embedded profile** when no profile is named. Ejecting sends also ejects media management and the state-handler API, because a host that owns its send boundary owns the rest of the mutation surface. Name any capability explicitly to override.
- **`/state-handlers/get` is grouped with the state writes, not the reads.** It exposes an arbitrary recipient's state, so a host ejecting the writes almost never wants the read left open.
- `POST /media/upload` and `DELETE /media/{id}` moved to their own routers inside `whatsapp_media.py`, so the media prefix now serves four capability groups instead of two.

### Security
- Under the embedded profile the only mounted route that reaches the platform or rewrites stored state is `POST /media/upload`, kept because an embedding host still needs Wappa's upload path and closable with `include_media_upload_api=False`. The `/specialized/validate-*` routes are `POST` because they take a body; they perform no I/O and change nothing.
- The invariant is asserted directly against the composed route table rather than the constructor flags: `EVERY_MUTATION & mounted == MEDIA_UPLOAD_ROUTES`.

### Verification
`uv run ruff check .` clean, `uv run ruff format --check` clean, `uv run mypy wappa` clean, `uv run pytest` → 532 passed (11 new route-composition tests, 20 in that suite).

## [0.26.0] - 2026-08-05

Hardening for embedding hosts: atomic cache transitions so a race has one winner, an explicit opt-out for Wappa's raw outbound HTTP routes, one classifier so nothing re-derives what kind of send a payload is, and two correctness fixes in the Redis cache layer. Every existing default is preserved, but **this release contains breaking changes** for hosts that implement `ITableCache` themselves or call `IExpiryCache.delete_all_for_user()`. See Fixed and the watch-outs below.

### Upgrade watch-outs

- **A custom `ITableCache` implementation will not instantiate** until it adds `create_if_absent` and `replace_if`. The two methods are abstract on the interface. Wappa's own three backends implement them; nothing else in this repo does. If you subclass `ITableCache` in your host, add both before upgrading.
- **`IExpiryCache.delete_all_for_user()` is gone.** Replace `expiry_cache.delete_all_for_user()` with `expiry_cache.delete_all_by_identifier(user_id)` — that is exactly what it did. See Fixed for why the name was removed rather than kept.

### Added
- **Atomic table-cache row transitions.** `ITableCache.create_if_absent(...)` and `ITableCache.replace_if(..., expected=...)` perform their condition and their write as one backend operation — a Lua script on Redis, the namespace lock in memory, the file lock in JSON — so a transition cannot be lost to an interleaved write. `TypedTableCache[T]` and `VersionedTableCache[T]` expose typed equivalents returning `TypedRowTransition[T]`.
  - `TableRowTransition` distinguishes `created`, `replaced`, `already_exists`, `condition_not_met`, and `missing`; `written` is true for the first two.
  - A refusal carries back the row that blocked it — the winner of a create race, or the row that moved on — already validated against the model, so no follow-up read is needed.
  - `expected` compares scalar field values through one canonical encoding, so `Status.PENDING` and `"pending"` match the same stored row on every backend. Containers and empty conditions are rejected.
  - A refused transition writes nothing and leaves the row's TTL untouched. A successful replacement is a whole-row write on every backend, not a field merge.
- **`Wappa(include_outbound_transport_api=False)`** — an embedding host that owns its own authenticated send boundary omits every ordinary and interactive outbound mutation route (`/messages/send-text`, `/messages/mark-as-read`, `/media/send-*`, `/interactive/send-*`, `/specialized/send-*`) and keeps everything else: media upload/download/lookup, every `/limits` endpoint, `/specialized/validate-*`, Template info, state handlers, webhooks, and health. `wappa.messaging` services are unaffected. Defaults to `True`, so standalone applications see no change. Reasoning in [ADR-0024](docs/adr/0024-outbound-http-routes-and-transports.md).
- **`classify_outbound_payload(payload)`** (`from wappa.messaging import ...`) — one pure classifier over Wappa's validated outbound schemas, returning an `OutboundClassification` with a `family` (text, media, interactive, location, contact, template, read_receipt) and a `subkind` where the family has several. All three Template envelope variants collapse to one `template` family, keeping their header as a subkind. Classification is transport shape only: a payload is a Template because it is a Template envelope, never because of actor, Origin, or metadata. Whether a send is *permitted* remains a Host Application question.

- **`scripts/verify_redis_cache_live.py`** — a live verification harness for `RedisCacheFactory`. It exercises all five caches, the atomic transitions, the boolean encoding contract, and the glob hazard against a real server, printing what each step expects, what it observed, the raw keys with their TTLs and field values, and per-call timings. Namespaced under `wappa-verify-<pid>:*`, cleans up after itself (`--keep` to inspect), exits non-zero on any failure.

### Changed
- **`create_whatsapp_router()` takes `include_outbound_transport` (default `True`)** alongside the existing `include_template_transport`. Route modules that mix sends with reads now expose a `send_router` and a `router`.
- **`dispatch_message_event()`'s `message_type` argument is optional.** Omitted — now the default on every Wappa route — the label is classified from the route's validated request payload instead of restated as a literal, so a route cannot drift from what it actually sends. Emitted `APIMessageEvent.message_type` values are unchanged.
- **The specialized route models extend the canonical outbound schemas** (`ContactRequest(ContactMessage)`, `LocationRequest(LocationMessage)`, `LocationRequestRequest(LocationRequestMessage)`) rather than restating their fields. Accepted request bodies are unchanged.
- `FileManager` gained `locked()` / `read_unlocked()` / `write_unlocked()` so a conditional write can hold one file lock across its read and write. `MemoryStore` gained the equivalent compound operations under its namespace lock.

### Fixed
- **Bulk Redis operations no longer silently match nothing** when an identifier contains glob syntax. Every enumeration (`delete_table`, `list_pkids`, `get_all`, `find_by_field`, `delete_all_by_pkid`, `list_handlers`, `delete_by_handler_prefix`, `delete_all_by_identifier`, the AI-state and PubSub patterns) is a SCAN glob, and a literal segment containing `*`, `?`, `[`, `]`, or `\` changed what the glob meant — so a delete built from an `inbox_id` of `a[1]` matched nothing and reported success. Patterns are now built through `KeyFactory.*_pattern()` helpers that escape literal segments and place wildcards deliberately; no handler builds a glob with an f-string. Meta `phone_number_id`s are digits, so production was not affected, but a host-chosen `cache_space`, table name, or `user_id` could be.
- **`IExpiryCache.delete_all_for_user()` removed** rather than renamed. A trigger key is `{inbox}:EXPTRIGGER:{action}:{identifier}` and carries no user, so the method actually deleted triggers whose *identifier* happened to equal the `user_id` — a different meaning from the identically named methods on `IStateCache` and `IAIStateCache`, which are genuinely user-scoped. Same name, two meanings, reached through the same factory. It was a one-line alias for `delete_all_by_identifier(self.user_id)`, so callers now write that and the ambiguity has nowhere to live.

### Documentation
- **[ADR-0024](docs/adr/0024-outbound-http-routes-and-transports.md)** records why the two route-composition defaults are asymmetric: Template mutations stay opt-in because nothing ever depended on them being mounted, while ordinary mutations stay mounted by default because they are the documented standalone surface and flipping them would be a silent break for every existing deployment.
- **[ADR-0008](docs/adr/0008-redis-hash-boolean-encoding.md)** records the Redis hash boolean encoding (`"1"`/`"0"` for a top-level bool, JSON spelling when nested) as a deliberate compatibility contract rather than an implementation detail. Host Applications read these fields outside Wappa, so the spelling cannot change on their behalf. The ADR states the accepted cost — an untyped read cannot tell `1` from `True` — its mitigation (read through a Pydantic model) and its one hard prohibition (never store `"1"`/`"0"` as a *string* value). `tests/test_redis_value_encoding.py` pins all of it.

### Verification
`uv run ruff check .` clean, `uv run ruff format --check` clean, `uv run mypy wappa` clean, `uv run pytest` → 521 passed (up from 402 at 0.25.0; 119 new tests).

The cache-transition suite runs one contract against all three backends, including Redis contention tests for a single create winner and no lost conditional replacement. The globbing suite was confirmed to fail against the pre-fix code (9 of 12) before being confirmed to pass against the fix. Redis-backed tests skip when no server is reachable at `WAPPA_TEST_REDIS_URL` (default `redis://localhost:6379`) and were run against a live Redis for this change.

`uv run python scripts/verify_redis_cache_live.py` exercises all five caches, the atomic transitions, the boolean encoding contract, and the glob hazard against a real server: 68 checks, exit 0, no keys left behind. No live provider sends were exercised.

## [0.25.0] - 2026-08-03

Finishes the clean break started in 0.24.0. The unused repository-interface family is gone, so Wappa now has exactly one persistence contract family — the type-specific cache interfaces — instead of two overlapping ones. The rest of the release is a repository-wide typing pass: explicit annotations, narrowed return types on the WhatsApp processor, and typed stats containers in the default handlers, with the Pydantic mypy plugin enabled and the blanket `ignore_missing_imports` overrides for `redis`, `openai`, and `cv2` removed. No runtime behavior changes.

**This release contains breaking changes** for anyone importing the repository interfaces. See Removed.

### Removed
- **The repository-interface family**: `IBaseRepository`, `IUserRepository`, `IStateRepository`, `ISharedStateRepository`, `IExpiryRepository`, `IPubSubRepository`, `IRepositoryFactory`, and `ITablesRepository` are deleted from `wappa.domain`, `wappa.domain.interfaces`, and `wappa.persistence`. They were a parallel contract set that no backend implemented. Use the cache contracts that were already the real thing: `IUserCache`, `IStateCache`, `IExpiryCache`, `ITableCache`, and `ICacheFactory` — all still exported from `wappa.persistence`.
- **`wappa.domain.enums`**, including `create_messenger_platform_enum()` and the dynamic `MessengerPlatformEnum` it built from settings. Nothing referenced it; `PlatformType` in `wappa.schemas.core.types` is the platform enum.
- **`TemplateMessageStatus`** from `wappa.messaging.whatsapp.models` — the last model belonging to the Template status endpoint removed in 0.24.0.

### Changed
- **`UniversalMessageData`** is now `dict[str, Any]` instead of `dict[str, str | int | bool | None | dict | list]`. The old union was not enforceable in practice and rejected legitimate nested payloads at type-check time.
- **Default handler statistics are typed containers.** `DefaultMessageHandler`, `DefaultStatusHandler`, `DefaultErrorHandler`, and `DefaultSystemHandler` keep their counters in dataclasses rather than free-form dicts. `get_stats()` returns the same keys and shape as before (`asdict` of the container).
- **The WhatsApp processor returns concrete types.** `parse_webhook_container()` is annotated `WhatsAppWebhook` and `create_status_from_data()` is annotated `WhatsAppMessageStatus` instead of the `BaseWebhook` / `BaseMessageStatus` supertypes — callers already received these objects at runtime.
- **Repository-wide annotations**: `-> None` on `__init__`, `**kwargs: Any` on handler and processor signatures, and explicit casts where a `dict[str, Any]` lookup feeds a typed return. Internal only.
- **mypy configuration**: the Pydantic plugin is enabled and the `redis` / `openai` / `cv2` `ignore_missing_imports` overrides are dropped now that those packages ship types.
- Tech requests 001–005 are marked `implemented` and `docs/public-contract.md` lists the cache interfaces in place of the removed repository interfaces.

### Verification
`uv run ruff check .` clean, `uv run ruff format .` clean, `uv run pytest` → 402 passed. No live provider sends were exercised for this release; it contains no outbound behavior changes.

## [0.24.0] - 2026-08-03

Adds an Inbox-scoped Template transport so embedding applications can send Templates through a small public capability instead of constructing Wappa's credential lookup, HTTP session, WhatsApp client, handlers, Messenger, and pipeline. The result type distinguishes a proven rejection from a call whose platform outcome is unknown, so a host never automatically retries an irreversible send. This release also takes a clean break on the internals that leaked through Wappa's public surface — raw `app.state` client aliases, compatibility status aliases, and duplicate Template models are gone rather than deprecated. Reasoning is recorded in [ADR-0024](docs/adr/0024-outbound-http-routes-and-transports.md), which extends ADR-0027.

**This release contains breaking changes.** See the Removed and Changed sections below.

### Added
- **`OutboundRuntime`** (`from wappa.messaging import OutboundRuntime`) — public factory that resolves Inbox credentials and active HTTP clients, constructs the platform Messenger and Messenger Pipeline, and hands back small Inbox-scoped capabilities. `OutboundRuntime.from_app(app).templates(inbox_id)` returns an `InboxTemplateTransport`.
- **`InboxTemplateTransport.send(request)`** — the Template capability. Requests are a strict discriminated union: `TextTemplateTransportRequest`, `MediaTemplateTransportRequest`, `LocationTemplateTransportRequest`. They reject unknown fields and carry platform-facing values only — no Agent, Campaign, attribution, Conversation, Reply State, or persistence concepts cross the boundary.
- **Typed Delivery Addresses** — each request carries exactly one: `PhoneNumberTemplateRecipient` (serialized as Meta's `to`) or `BsuidTemplateRecipient` (regular or parent BSUID, serialized as Meta's `recipient`). Usernames are webhook/response evidence and are not accepted as outbound addresses. Authentication Templates require a named method and reject BSUID addresses.
- **`TemplateTransportOutcome`** with four meanings: `accepted` (platform acceptance *and* a platform Message ID are proven), `rejected` (evidence the call was not accepted), `transport_unavailable` (no call could be started, including drain), `indeterminate` (acceptance cannot be proven). A success response without a Message ID is `indeterminate`. Acceptance never claims delivery, read, reply, or Host Application commit — and callers must not auto-resend an `indeterminate` result.
- **Explicit endpoint routing** — marketing Templates go to `/marketing_messages` and utility/authentication to `/messages` by category default. The only fallback is the named `cloud_messages_fallback` policy, selected before I/O. Wappa never retries a rejection or an ambiguous response through the other endpoint. `TemplateTransportResult` reports the selected `TemplateEndpoint` and `TemplateRoutingReason`.
- **`Wappa(include_template_transport_api=True)`** — opt-in for Wappa's standalone Template HTTP routes. Embedding hosts get no raw Template mutation routes unless they ask.
- **Richer recipient evidence on `MessageResult`** — `recipient_parent_bsuid` and `recipient_username`, plus `ResponseContact.parent_bsuid`, `.username`, `.profile`, and `.resolved_username`.
- **ADR-0024**, a `Delivery Address` / `Outbound Runtime` / `Template Transport` / `Template Transport Outcome` glossary in `CONTEXT.md`, a Template transport flow in `ARCHITECTURE.md`, and a verification record under `docs/verification/`.

### Changed
- **`IMessenger` Template methods take `routing_policy` instead of `override`.** The old boolean `override` did not say what it selected; `routing_policy: str = "category_default"` names the choice. Update `send_text_template(..., override=True)` to `send_text_template(..., routing_policy="cloud_messages_fallback")`.
- **`WappaCorePlugin.recreate_http_session()` no longer takes an `app` argument.** The plugin already owns the lifecycle. Replace `recreate_http_session(app)` with `recreate_http_session()`.
- **`SessionLifecycle` is the sole owner of Wappa's HTTP clients.** Consumers receive provider callables (`get_session`, `get_media_download_client`); the media-download client is no longer created ad hoc by the media handler. ADR-0027 are amended to record this.
- **`whatsapp_router` is now `create_whatsapp_router(include_template_transport=...)`** in `wappa.api.routes`.
- **`HTTPSessionNotAvailableError` is renamed `SessionLifecycleNotAvailableError`** (`wappa.core.expiry`).
- **Outbound failures return a sanitized `error` message and a stable `error_code`** instead of `str(exception)`. Codes: `runtime_unavailable`, `platform_outcome_indeterminate`, `invalid_template_request`, Meta's numeric error code, or `http_<status>`. Raw exception text no longer reaches callers.
- **`APIEventDispatcher.dispatch()` requires its `request` argument** — it is no longer optional.
- Universal enums in `wappa.schemas.core.types` are `StrEnum` rather than `str, Enum`.

### Removed
- **`wappa.messaging` no longer re-exports adapter internals**: `WhatsAppClient`, `WhatsAppMessenger`, `WhatsAppUrlBuilder`, `WhatsAppFormDataBuilder`, `WhatsAppMediaHandler`, `WhatsAppInteractiveHandler`, `WhatsAppTemplateHandler`, `WhatsAppSpecializedHandler`. Host Applications receive `IMessenger` from Wappa runtime contexts or resolve the Template capability through `OutboundRuntime`; they do not construct clients, handlers, factories, or sessions.
- **Template request models** `TextTemplateMessage`, `MediaTemplateMessage`, `LocationTemplateMessage`, their `*Metadata` classes, `BaseTemplateMessage`, `TemplateLanguage`, `TemplateComponent`, and `TemplateValidationResult`. The public Template request surface is now the transport request union in `wappa.messaging`.
- **Status compatibility aliases** `StatusType`, `DeliveryStatus`, `ReadStatus`, `SentStatus`, `FailedStatus` from `wappa.webhooks.whatsapp` — all five were aliases of `MessageStatus` / `WhatsAppMessageStatus`, which are exported directly.
- **Raw client aliases in application state**: `app.state.http_session`, `app.state.get_http_session`, `app.state.media_download_client`. Use `app.state.session_lifecycle`, or the `OutboundRuntime` seam.
- **The shadow `wappa/sse.py` module.** The `wappa/sse/` package is the sole SSE public surface; imports are unchanged.
- **Media payload creation on `MessageFactory`** (`create_image_message`, `create_video_message`, `create_audio_message`, `create_document_message`, `create_sticker_message`) — `MediaFactory` is the single owner of media payloads.
- **`get_api_logger()`** from `wappa.core.logging.logger`, an alias of `get_app_logger()`.

### Verification
`uv run ruff check .` clean, `uv run ruff format --check .` clean, `uv run pytest` → 402 passed. Strict mypy passes on the new transport, lifecycle, expiry composition, and Template route adapter (the repository-wide mypy baseline is not green and is unchanged by this work). Controlled live sends through `/messages` and `/marketing_messages` against Meta have **not** been run — no provider credentials were available during implementation. See `docs/verification/260803-template-runtime-seam.md`.

## [0.23.2] - 2026-07-29

Fixes a second rejected shape on the same `user_actions` payload. Meta started
sending `client_user_agent` inside `marketing_messages_link_click_data`
(e.g. `"(Android 14)"`) without announcing it, and that sub-object was
`extra="forbid"`, so every click carrying it still 400'd with
`extra_forbidden` even after 0.23.1. The dispatch fix from 0.23.1 was already
working correctly — this is purely the nested payload validation.

### Fixed
- `marketing_messages_link_click_data` no longer 400s on `client_user_agent`
  (now a typed field) or on any other undocumented sibling field.

### Added
- `MarketingMessagesLinkClickData` is now `extra="allow"`, matching the
  tolerance policy already applied to `UserActionEntry`.
- Both models now log a `WHATSAPP_WEBHOOK_UNDOCUMENTED_FIELDS` warning
  (field names + raw values) whenever Meta sends a field outside the typed
  contract, so new additions are visible in logs instead of silently
  dropped.
- 2 contract tests covering the `client_user_agent` payload and the new
  warning log.

## [0.23.1] - 2026-07-26

Fixes rejected marketing-message interaction webhooks. Meta's Marketing Messages
API delivers a `user_actions` array when a user clicks the body or call-to-action
of a marketing message — on the `messages` field, but in a `value` carrying
neither `messages` nor `contacts`. `WebhookValue` is `extra="forbid"`, so every
one of those deliveries failed with
`WHATSAPP_WEBHOOK_CONTRACT_DRIFT error_type=extra_forbidden fields=entry.0.changes.0.user_actions`
and returned `HTTP 400`. Ordinary messages kept working, but Meta retried each
rejected click event, and sustained 400s put the webhook at risk of being
throttled. Payload shapes and the reasoning are recorded in
[META-CHANGELOGS.md](META-CHANGELOGS.md).

### Fixed
- `user_actions` webhooks now parse and dispatch instead of returning `HTTP 400`.

### Added
- `WebhookValue.user_actions`, typed as `list[UserActionEntry]` and accepted as
  webhook content, so a `value` carrying only user actions is valid.
- `UserActionEntry` and `MarketingMessagesLinkClickData` in
  `wappa.webhooks.whatsapp.system_events`. The entry is `extra="allow"` on
  purpose: Meta ships action types it has not documented, and an unrecognized
  one must not become a sustained 400. Strictness stays at `WebhookValue`, which
  still rejects unknown top-level keys as contract drift.
- `SystemEventType.USER_ACTION`, plus `SystemEventDetail.action_type` and
  `SystemEventDetail.user_action` (the action entry serialized without field
  loss). These events are Inbox-scoped and dispatch with
  `SystemWebhook.user is None` — the payload carries no user identity. Hosts that
  want click attribution handle them in `process_system_webhook`.
- `WhatsAppWebhook.is_user_action` and `WhatsAppWebhook.get_user_actions()`.
- 5 contract tests covering the documented click payload, an undocumented action
  type, drift still being reported for unknown `value` keys, dispatch, and the
  messages-take-precedence case.

### Changed
- When a `value` carries both `messages` and `user_actions`, the inbound-message
  path wins; the actions remain reachable via `get_user_actions()`. Meta only
  documents them arriving standalone, but a future combined payload must not
  swallow a real message.

## [0.23.0] - 2026-07-25

Promotes a set of generic runtime primitives into Wappa so host platforms stop
hand-rolling them: signed-webhook verification, external event routing, cache
namespacing and versioned invalidation, request correlation IDs, and retry
helpers for transient HTTP and database failures. All of it is domain-neutral
and reachable through shallow public imports. The trade-offs behind each
primitive are recorded in
[ADR-0005](docs/adr/0005-runtime-primitives-for-host-platforms.md).

Everything here is additive — no existing public surface changed.

### Added
- `HMACSignatureVerifier` (`from wappa import HMACSignatureVerifier`) for signed
  External Webhook Sources. Handles hex/base64 encodings, algorithm prefixes
  (`sha256=`), case-insensitive header lookup, and constant-time comparison.
  Returns a verdict instead of raising; misconfiguration raises at construction.
- `ExternalEventRegistry` and `DispatchReport` (`from wappa import ...`) for
  routing `ExternalEvent`s to async handlers by `(source, event_type)`. Matches
  exact, prefix (`payment.*`), and any (`*`) subscriptions; dispatch is
  best-effort per handler so one broken subscriber cannot silence the rest.
- `VersionedTableCache[T]` (`from wappa.persistence import VersionedTableCache`)
  invalidates a whole read model with one `bump_version()` — no key enumeration,
  visible across processes, scoped per logical table.
- Optional `cache_space` on `TypedTableCache` and `VersionedTableCache`, plus the
  `build_table_name()` helper, so host modules can share a table name inside one
  Inbox without colliding.
- `TypedTableCache.renew_ttl()` for extending a row's TTL without rewriting it.
- `RequestIdMiddleware`, installed by `WappaCorePlugin` as Wappa's outermost
  middleware. Reuses a trusted inbound `X-Request-ID`, otherwise generates one;
  echoes it on the response and adds `request_id` to JSON log records.
- `get_current_request_id()` and a `request_id` argument on
  `set_request_context()`, both exported from `wappa.core.logging`.
- `wappa.resilience`: `RetryPolicy`, `retry_async`, `retry_transient_http`,
  `retry_transient_db`, `is_transient_http_error`, `is_transient_db_error`.
  Bounded exponential backoff with jitter; `CancelledError` is never retried and
  the final attempt's exception propagates unchanged.
- ADR-0005 recording the decisions behind these primitives, and 81 new tests
  covering retry classification, signature verification, event dispatch, cache
  versioning, request IDs, and SSE hub fan-out/overflow/cleanup.

### Changed
- `PostgresSessionManager` transient-error classification now delegates to
  `wappa.resilience.is_transient_db_error`, so the session manager and host-owned
  retry decorators agree on what "transient" means. Behavior is unchanged,
  including the deliberate fast-fail on SQLAlchemy pool checkout timeouts.

## [0.22.1] - 2026-07-24

Fixes dropped template quick-reply taps. When a user tapped a quick-reply button
on a template message, Meta sent a `type: "button"` message with no `context`
block, `WhatsAppButtonMessage` rejected it as a missing required field, and the
webhook returned `HTTP 400` — every button tap on a promo template was silently
lost while plain text messages kept working.

### Fixed
- `WhatsAppButtonMessage.context` is now optional, matching Meta's real payload
  for template quick-reply taps. Contexts that *are* present keep their previous
  validation (forwarded and product contexts are still rejected).
- `original_message_id`, `business_phone`, and `get_button_context()` return
  `None` instead of raising when there is no context; `has_context()` now
  reflects the payload, and platform/universal dicts serialize `context: None`.

### Added
- `WhatsAppButtonMessage.text_content`, so `webhook.get_message_text()` returns
  the button label (e.g. `"QUIERO PROMO SUERO"`) instead of an empty string for
  template button replies.

## [0.22.0] - 2026-07-21

Updates Wappa's WhatsApp identity contract for Meta's 2026 BSUID and username
rollout. The production trigger, exact payload changes, host migration work,
Meta restrictions, and API-family boundaries are recorded in
[META-CHANGELOGS.md](META-CHANGELOGS.md#2026-07-21-bsuids-usernames-and-optional-phone-numbers).

### Added
- Parent BSUID and username-only webhook coverage for inbound messages,
  reply contexts, contacts, statuses, group participant statuses, and system
  identity events.
- Parent BSUID outbound routing through Meta's `recipient` field.
- `WhatsAppMessenger.send_contact_request()` and parsing for the returned
  contact `origin` / `vcard` fields.
- Critical `WHATSAPP_WEBHOOK_CONTRACT_DRIFT` log events for strict
  `extra_forbidden` failures, with field paths and no payload values.
- Native typed webhook coverage for business username changes, group
  participants, Calling, Coexistence history, SMB message echoes, SMB app-state
  sync, and consumer message edits and revokes.
- `CallWebhook` and the optional `WappaEventHandler.process_call()` hook.

### Fixed
- `MessageContext` now accepts Meta's `context.from_user_id`; this was the
  missing field that caused production webhook retries and dropped messages.
- System message webhooks no longer require a `contacts` array, matching Meta's
  `user_changed_user_id` shape.

### Changed
- Phone identifiers remain optional attributes. Canonical user and recipient
  accessors prefer BSUIDs when Meta supplies them.
- Built-in webhook models keep `extra="forbid"`. Unknown Meta fields still
  return `HTTP 400`; operators must alert on the drift signature above.
- `AccountWebhookValue` now uses `extra="forbid"`, replacing the narrow
  forward-compatibility exception introduced in 0.20.0.
- Coexistence history, echo, and app-state values dispatch as `SystemWebhook`
  events with their typed payload retained in
  `event_detail.coexistence_payload`.

## [0.21.3] - 2026-07-05

Hardens the PostgreSQL session manager against a fresh-connection hang. When a brand-new asyncpg connection could not be established — a WSL2/dev DNS blip, an unroutable or stalled host — the request hung on asyncpg's ~60s default connect deadline, and the transient failure surfaced mid-handler where retry is unsafe. Both are now bounded and recoverable, without touching the non-retrying query/transaction invariant introduced in 0.21.0.

### Added
- **`connect_timeout` (default `10.0`)** on `PostgresSessionManager` and `PostgresDatabasePlugin`, threaded to asyncpg as the connect-arg `timeout`. A stalled/unroutable host now fails per-attempt in ~10s instead of hanging ~60s on the driver default. Set to `None` to fall back to the driver default.
- **`connect_max_retries` (default `2`, i.e. 3 attempts total)** on both classes. `_acquire_session` now forces the pool checkout (`session.connection()`) *before* yielding to the caller, wrapped in a bounded retry that replays only transient connection-*establishment* errors (DNS blips, connection refused/reset, network unreachable — reusing the existing `_is_transient_error` / `_calculate_backoff`). Because no user query has run yet, replaying a fresh connect is safe. `CancelledError`, non-transient errors (bad credentials, SQL), and exhausted attempts are never retried; the half-open session is shielded-closed before each retry/raise. Set to `0` to restore fully-lazy acquisition (no eager checkout) and disable connect retries.

### Changed
- No new round-trips: `pool_pre_ping` already validated the connection at checkout; the checkout was only moved earlier so a connect failure is catchable and retryable instead of escaping into the caller's first query. The query/transaction path remains non-retrying — the 0.21.0 core invariant is untouched, and `connect_max_retries=0` reproduces today's exact fully-lazy behavior.

## [0.21.2] - 2026-07-02

Fixes `InboxMiddleware` mislabeling downstream errors. The middleware wrapped the entire downstream request inside the try block that guards inbox resolution, so any exception raised by a route or handler below it was re-wrapped as a `500: InboxMiddleware failed while resolving inbox context…` — stealing attribution from the real error (e.g. a Pydantic `ValidationError`) and making 500s much harder to diagnose.

### Fixed
- **`InboxMiddleware` no longer re-labels downstream exceptions.** `return await call_next(request)` moved out of the inbox-resolution `try` block to after the `except` handlers. Inbox resolution (path parsing, `set_request_context`, invalid-ID handling) is still guarded and still surfaces as a `400`/`500` inbox error; but route and handler exceptions now propagate with their true origin to the app's own exception/validation handlers instead of being misattributed to the middleware.

## [0.21.1] - 2026-07-02

Makes `wappa init` scaffolding produce a project that actually boots. The generated `.env` used legacy variable names that `settings.py` no longer reads, so a freshly scaffolded project failed startup credential validation. Ships the fixes merged in #7.

### Fixed
- **Scaffolded `.env` now boots.** `cli/templates/env.template` used legacy names that `settings.py` no longer reads — the required WhatsApp credentials came back empty and startup validation failed. Renamed to the canonical names: `WHATSAPP_WEBHOOK_VERIFY_TOKEN` → `WP_WEBHOOK_VERIFY_TOKEN`; `TIME_ZONE`/`LOG_LEVEL`/`LOG_DIR`/`ENVIRONMENT` → `SYSTEM_TIME_ZONE`/`SYSTEM_LOG_LEVEL`/`SYSTEM_LOG_DIR`/`SYSTEM_ENVIRONMENT`; `BASE_URL`/`API_VERSION` → `META_BASE_URL`/`META_API_VERSION`.
- **Scaffolded `master_event.py` `mark_as_read` call.** The template passed `webhook.user.user_id` (a phone string) as the second positional argument, which is `typing: bool` — not a recipient. Corrected to `mark_as_read(webhook.message.message_id)`.

### Changed
- `CLAUDE.md` setup examples now document the real API — `Wappa(cache=...)`, `add_plugin()`, `set_event_handler()`, and the builder's `add_plugin()/configure()/build()` — replacing a fictional `WappaBuilder` fluent API (`.with_whatsapp()`, `.with_redis_cache()`, …) and `Wappa(whatsapp_token=...)`/`register_handler()` that had propagated into the docs site.

## [0.21.0] - 2026-07-02

Closes a proven database connection-leak and hardens the PostgreSQL session manager against the transaction-hold pattern that can exhaust a Supavisor/pgBouncer pool and hang the whole app. Under any cancellation source (edge proxy aborts, statement timeouts, worker shutdown), a request wrapped in an anyio cancel scope — which every Starlette `BaseHTTPMiddleware` creates — no longer orphans its server-side backend `idle in transaction`.

### Fixed
- **Cancellation-safe session teardown.** `PostgresSessionManager` session teardown now catches `BaseException` (not `Exception`), so `asyncio.CancelledError` — which derives from `BaseException` — can no longer slip past the rollback. Commit/rollback/close run inside a shielded, 10s-bounded scope (`anyio.move_on_after(shield=True)`) so the ROLLBACK/DISCARD reaches Postgres even while the enclosing cancel scope is being torn down. Previously the app-side pool silently discarded the connection while the server backend leaked mid-transaction until the pool exhausted.
- **Pool-exhaustion is no longer retried.** SQLAlchemy's `QueuePool` checkout timeout (`sqlalchemy.exc.TimeoutError`, message contains "connection timed out") is now classified as non-transient and fails fast instead of being retried 3× with backoff, which previously amplified saturation and could stall even DB-free endpoints like `/health`.
- **`connect_args=None` startup crash.** `connect_args` is now always a dict, never `None` — `create_async_engine(connect_args=None)` raised `TypeError: 'NoneType' object is not iterable` for any consumer that didn't set `statement_cache_size`.

### Added
- `command_timeout` (default `30.0`) on `PostgresSessionManager` and `PostgresDatabasePlugin`, threaded to asyncpg as a per-statement deadline so a stalled query cannot pin its connection indefinitely. Set to `None` to disable.
- `tests/test_session_cancel_rollback.py` — regression coverage for the leak: deterministic cancellation/teardown unit tests plus real-Postgres integration tests asserting zero `idle in transaction` backends and `pool_checked_out == 0` after mid-query cancellation (auto-skipped when PostgreSQL server binaries are absent).

### Changed
- **Session path no longer retries, and the eager `SELECT 1` validation is removed** (intentional semantics change). The session's transaction now begins on the first real query instead of at checkout, shrinking the transaction window from the whole request to actual query time. Dead-connection-at-checkout is covered by `pool_pre_ping`; startup connectivity is still covered by `_initialize_with_retry`. Use + teardown is a single shielded, non-retryable path. `TransientDatabaseError` remains exported for backwards compatibility but is no longer raised by the session path.

## [0.20.0] - 2026-06-25

Adds first-class parsing for Meta's Coexistence account-level webhooks, surfaced as typed `SystemWebhook` events so any consumer receives them without registering a custom field. These fire on WABAs connected via Embedded Signup + Coexistence (now available to verified Tech Providers).

### Added
- `SystemEventType.ACCOUNT_OFFBOARDED` and `SystemEventType.ACCOUNT_RECONNECTED` — account-scoped (Platform Account / WABA) coexistence events. They dispatch through `process_system_webhook` with `SystemWebhook.user is None`.
- `SystemEventDetail` gains `waba_id`, `phone_number_id`, and `reason` fields for account-scoped events.
- Strict `AccountWebhookValue` model parsing the flat, WABA-scoped change value (`waba_id`/`timestamp` required, `reason`/`phone_number_id` optional, `extra="ignore"` for forward compatibility).

### Changed
- Account-level coexistence fields validate against the strict `AccountWebhookValue` model instead of the permissive custom-field path — malformed payloads now surface as clear validation errors. `WebhookValue` is unchanged.
- `ACCOUNT_EVENT_FIELDS` is the single source of truth in `field_registry`; `BUILTIN_WEBHOOK_FIELDS` composes from it.

## [0.19.0] - 2026-06-14

Upgrades to FastAPI 0.137 (router-tree architecture), deepens the plugin system with public route prefixes and lazy route registration, and slims the WappaPlugin protocol to a single method.

### Changed
- FastAPI minimum version bumped from 0.135.1 to 0.137.0, adopting the preserved router-tree architecture where `include_router` stores relationships as tree nodes instead of flat clones.
- `WappaBuilder.add_router()` accepts `public=True` to declare router prefixes as unauthenticated. Public prefixes are exposed on `app.state.public_route_prefixes` and checked by `AuthMiddleware` at request time.
- `AuthPlugin.DEFAULT_EXCLUDES` reduced from 7 to 4 entries — `/health` and `/webhook/*` paths are now declared as public by their owning plugins instead of being hardcoded in the auth exclude list.
- `AuthMiddleware._requires_auth()` reads `app.state.public_route_prefixes` in addition to static excludes, so adding a new public router no longer requires updating the auth configuration.
- `WappaBuilder` now owns all route composition — the webhook router is registered through the builder instead of being included directly on the app after build.
- `CronPlugin` uses lazy route registration: registers an empty router shell in `configure()` and populates it with fastapi-crons monitoring routes during startup, eliminating the builder bypass.
- `WappaPlugin` protocol slimmed to a single `configure()` method. The framework never called `startup()`/`shutdown()` directly on plugins — lifecycle is managed entirely through hooks registered in `configure()`.
- Dead `startup()`/`shutdown()` implementations removed from 11 plugin files (~200 lines).
- `RateLimitPlugin` startup/shutdown hooks made private; tests exercise `LocalRateLimiter` directly.

## [0.18.0] - 2026-06-09

Adds Wappa-native runtime primitives for External Webhook Sources, typed
best-effort SSE publishing, Inbox-scoped typed table caches, and local
route-level rate limiting.

### Breaking Changes
- `RateLimitPlugin` now accepts named `RateLimitProfile` objects and stores a
  local per-process limiter on application state. The previous
  bring-your-own-middleware constructor is removed.

### Added
- `ExternalWebhookRuntime` returns typed internal process outcomes for accepted
  dispatch, Inbox mismatch, parse failure, unresolved User, and dispatch
  failure while preserving accepted HTTP delivery semantics.
- `TypedTableCache[T]` binds an existing Inbox-scoped `ITableCache` to a table
  name and Pydantic model with typed reads, validated writes, and default TTL
  forwarding.
- `RateLimitProfile`, `RateLimitPlugin`, and `rate_limit()` provide opt-in local
  fixed-window limits keyed by client IP, Inbox, or both.
- SSE publishers deliver registered custom event types and reject unknown event
  types before reaching the low-level event hub.

### Changed
- External Webhook Source route handling delegates parsing, context creation,
  user resolution, and dispatch to `ExternalWebhookRuntime`.
- `publish_sse_event()` is the official best-effort publisher and returns `0`
  when the event type is unknown or the hub fails.
- API event background dispatch avoids creating unawaited coroutines while the
  runtime is draining.

### Fixed
- Memory table caches now fully implement `ITableCache.delete_table()` and
  `ITableCache.list_pkids()`.

## [0.17.5] - 2026-06-02

Fix Redis expiry PubSub listener reconnection storm under redis-py 8's finite default socket timeout.

### Fixed
- Redis expiry listener now disables the read timeout on its dedicated PubSub connection after subscribing, preventing idle keyspace notification waits from being treated as failures and triggering reconnection loops under redis-py 8. Command pool connections keep their normal timeout behavior.
- `RedisConnectionManager._get_db_number` now casts the `db` value to `int`, guarding against string-typed connection kwargs.

## [0.17.4] - 2026-05-28

Fixes a broken import in the v0.17.3 debug SSE endpoint. The endpoint referenced
a nonexistent `set_sse_context` function; now uses the public `sse_event_scope`
context manager, which also ensures the ContextVar is properly cleaned up after
each request.

### Fixed
- Debug SSE publish endpoint: replaced broken `set_sse_context` import with the
  public `sse_event_scope` async context manager, fixing the import error and
  adding proper ContextVar cleanup.

## [0.17.3] - 2026-05-28

Adds a debug-only SSE publish endpoint for testing event delivery without a live
WhatsApp webhook. The endpoint is excluded from the OpenAPI schema and intended
for local development and integration debugging.

### Added
- `POST /sse/debug/publish` — debug endpoint that publishes a test SSE event
  with configurable `event_type`, `payload`, `inbox_id`, and `user_id`.
  Hidden from the public schema (`include_in_schema=False`).

## [0.17.2] - 2026-05-27

Adds a pooled unauthenticated HTTP client for public/third-party media downloads,
strictly isolated from the authenticated WhatsApp API client. Connection reuse
reduces overhead under volume while enforcing credential isolation. Updates DDD
documentation (CONTEXT.md, ARCHITECTURE.md, messaging and plugins architecture)
to reflect the lifecycle and credential boundary patterns established since v0.16.0.

### Added
- `SessionLifecycle.get_media_download_client()` — lazily-created pooled
  `httpx.AsyncClient` (20 connections, 5 keepalive, 60s timeout) with no auth
  headers, for downloading public/third-party media URLs.
- `WhatsAppMediaHandler` accepts optional `media_download_client` kwarg; uses
  pooled client when available, falls back to per-call client otherwise.
- Media download client wired through both injection paths: API route DI
  (`whatsapp_dependencies.py`) and inbound dispatch (`MessengerFactory` →
  `InboundRuntimeDependencies` → `WebhookController`).
- `tests/test_media_download_client_isolation.py` (10 tests): lazy creation,
  instance isolation, drain rejection, shutdown closure, no-auth-headers,
  pooled vs fallback handler paths.
- DDD documentation updates: lifecycle terms in CONTEXT.md, HTTP client
  lifecycle section in root ARCHITECTURE.md, credential isolation in messaging
  ARCHITECTURE.md, shutdown phases in plugins ARCHITECTURE.md.

### Changed
- `SessionLifecycle.close()` now closes both authenticated and media download
  clients.
- `InboundRuntimeDependencies` gained `media_download_client_provider` field.
- Existing `test_media_upload_from_url.py` mock updated for the new client
  construction pattern (no longer context-manager-wrapped).

## [0.17.1] - 2026-05-27

Removes the last `asyncio.create_task` fallback from the Redis pub/sub example
and adds regression tests for the lifecycle fixes shipped in v0.17.0. Closes
Issue #5.

### Changed
- Redis pub/sub example requires `BackgroundWorkTracker` — removed
  `asyncio.create_task` fallback path. The example now fails loudly if the
  tracker is missing, matching the framework's clean-break contract.

### Added
- `tests/test_api_event_tracking.py` (8 tests): regression coverage for
  `dispatch_api_message_event()`, `fire_api_event()`, and the
  `dispatch_message_event()` decorator — verifies tracker submission, raises
  without tracker, and skips during drain.
- `tests/test_memory_store_shutdown.py` (3 tests): verifies
  `WappaCorePlugin._core_shutdown()` stops the memory store cleanup task and
  skips it for non-memory cache types.

## [0.17.0] - 2026-05-27

Completes the lifecycle contract that v0.16.0 documented but partially shipped.
Four areas were reverted during the v0.16.0 release process: API event dispatch
tracking, memory store shutdown ownership, the `MessengerFactory` clean break,
and the Redis pub/sub example alignment. This release fixes all four and closes
Issue #4.

### Breaking Changes
- **`MessengerFactory` signature changed** — the `http_session` positional
  parameter is removed. Constructor is now
  `MessengerFactory(session_provider, credential_store)` where `session_provider`
  is a `Callable[[], httpx.AsyncClient]`. The `validate_session` fallback path
  is removed.

### Changed
- `dispatch_api_message_event()`, `dispatch_message_event()`, `fire_api_event()`
  use `BackgroundWorkTracker.track()` instead of raw `asyncio.create_task()`.
  During drain, dispatch is skipped with a warning rather than silently spawning
  untracked work.
- Redis pub/sub example uses `session_lifecycle.get_session` as session provider
  and `BackgroundWorkTracker.track()` for the listener task.

### Fixed
- Memory store TTL cleanup task now stopped during
  `WappaCorePlugin._core_shutdown()` when memory caching is configured.
- `MessengerFactory` no longer accepts the legacy `http_session` positional
  parameter, matching the v0.16.0 release notes and public contract.
- `tests/test_http_session_lifecycle.py` updated for the provider-only factory
  signature.

## [0.16.0] - 2026-05-27

Template pipeline keyword-only argument fix, JWT leeway, and partial lifecycle
contract adoption. Resolves the two Symphonai compatibility blockers (template
`TypeError` and JWT clock-skew) and advances `SessionLifecycle` adoption for
inbound runtime and webhook controller paths.

### Added
- `JWTStrategy` accepts `leeway: int | float = 0` keyword argument, forwarded to
  `jwt.decode()`. Negative values raise `ValueError`.
- `MessengerPipeline._invoke()` accepts `keyword_only` parameter to separate
  keyword-only arguments from positional dispatch.
- `SSEEventContext._tracker` field and `sse_event_scope(tracker=...)` parameter
  for lifecycle-aware SSE flush.
- `DispatchContext` carries `background_work_tracker` for SSE tracker propagation.
- 11 new tests: `test_template_pipeline.py` (4), `test_jwt_leeway.py` (7).

### Changed
- **`InboundRuntimeDependencies.http_session` replaced** with `session_provider:
  Callable[[], httpx.AsyncClient]` — a required field.
- **`WebhookController`** reads `app.state.session_lifecycle.get_session` instead
  of `app.state.http_session`.
- Template pipeline methods (`send_text_template`, `send_media_template`,
  `send_location_template`) pass `template_type`/`override` as kwargs, fixing
  `TypeError` when the raw messenger enforces keyword-only signatures.
- `flush_incoming_sse()` uses tracker when available, falls back to raw task.
- Logger calls in `api_event_dispatcher`, `session_manager`, and
  `wappa_core_plugin` converted from f-strings to `%s` lazy evaluation.

### Fixed
- Failed read-replica disposal during `PostgresSessionManager.initialize()` now
  uses `dispose(close=False)` — non-blocking, matching shutdown behavior.
- `tests/test_session_lifecycle.py` fixtures converted to async — fixes teardown
  under Python 3.12 with pytest-asyncio 1.3.0.
- Removed `_template_options` dead helper from pipeline.
- Removed unreachable code in `SessionLifecycle.recreate()`.

### Known Issues (fixed in v0.17.0)
- `MessengerFactory` still accepted the legacy `http_session` positional parameter.
- API event dispatch (`event_dependencies.py`, `event_decorators.py`) still used
  raw `asyncio.create_task()`.
- Memory store TTL cleanup task not stopped at shutdown.
- Redis pub/sub example still used stale `app.state.http_session` pattern.

## [0.15.1] - 2026-05-27

Graceful background work drain and HTTP session lifecycle completion. Wappa now
stops accepting new background work, drains in-flight tasks with bounded
timeouts, and only then closes HTTP sessions, database pools, and Redis
connections. All fire-and-forget `asyncio.create_task()` calls in framework code
are replaced by a tracked `BackgroundWorkTracker`. A unified `SessionLifecycle`
service provides draining-aware session access with serialized recreation.

### Added
- `BackgroundWorkTracker` — lifecycle-aware task tracking with `track()`,
  `begin_drain()`, and `drain(timeout)`. Stored on `app.state.background_work_tracker`.
- `SessionLifecycle` — unified session acquisition with three states (active,
  recoverable, draining). Provides `get_session()`, `recreate()` (lock-serialized),
  and `begin_drain()`. Stored on `app.state.session_lifecycle`.
- `RuntimeDrainingError` — raised when session access is attempted during
  shutdown. Exported from `wappa.domain.interfaces.session_provider`.
- `MessengerFactory` accepts `session_provider` keyword argument — a callable
  returning `httpx.AsyncClient`, replacing direct session references.
- ADR-0027: Graceful Shutdown and Background Work Drain.
- 21 new tests: `test_background_work_tracker.py`, `test_session_lifecycle.py`,
  `test_shutdown_lifecycle.py`.

### Changed
- **Shutdown priority reordering** — HTTP session now closes at priority 10
  (last) instead of 90 (first). Cron stops at 85, expiry at 80, background
  drain at 70, infrastructure cleanup at ≤25.
- `ExpiryPlugin` now calls `AppContext.clear()` on shutdown.
- `CronPlugin` shutdown wraps `stop()` in a 15-second bounded timeout.
- `ExpiryDispatcher` requires `BackgroundWorkTracker` — no fallback to raw
  `asyncio.create_task()`.
- `InboundRuntime.accept_webhook()` dispatches through `BackgroundWorkTracker`.
- `WebhookPlugin._handle_webhook()` dispatches through `BackgroundWorkTracker`.
- `InboundRuntimeDependencies.background_work_tracker` is now required (non-optional).
- All messenger construction paths (`context_helpers`, `WappaContextFactory`,
  `whatsapp_dependencies`) use `SessionLifecycle.get_session` — no direct
  `app.state.http_session` reads in framework code.
- `WappaCorePlugin.recreate_http_session()` delegates to `SessionLifecycle.recreate()`
  with lock serialization and draining guard.

### Fixed
- All messenger construction paths (`create_expiry_messenger`, `WappaContextFactory`,
  `redis_pubsub_example`) now propagate `credential_store` to `MessengerFactory`.
- `whatsapp_dependencies.get_whatsapp_client()` and `WebhookPlugin._handle_webhook()`
  use explicit checks with actionable errors instead of bare `app.state` access.
- Plugin shutdown docstrings updated to reflect new priority scheme.

### Removed
- Backward-compat fallbacks for missing `BackgroundWorkTracker` or `SessionLifecycle`
  on `app.state`. Framework code requires both — clean break.

## [0.14.0] - 2026-05-27

HTTP client lifecycle ownership and actionable error messages across the entire
framework. Wappa now owns session validity for all messenger instances — host
applications no longer need to detect or repair closed httpx sessions. Every
error response identifies what failed, why, and how to fix it.

### Added
- `HTTPSessionClosedError` and `validate_session()` in
  `wappa.domain.interfaces.session_provider` — centralized session guard.
- `WappaCorePlugin.recreate_http_session(app)` — supported hook for host
  applications that hot-reload or need to restore a closed transport.
- `app.state.get_http_session` provider callable — returns a guaranteed-open
  session or raises `HTTPSessionClosedError`.
- `MessengerFactory._get_session()` — validates session before creating or
  returning cached messengers; stale cache entries auto-evict.
- ADR-0027: HTTP Client Lifecycle Ownership — records adapter ownership rules,
  credential boundary separation, and session recreation contract.
- `tests/test_http_session_lifecycle.py` — 11 tests covering all lifecycle
  guard paths.

### Changed
- All API error responses now include: operation context (recipient, inbox_id,
  media_id), exception type, and actionable remediation guidance.
- Error handler middleware returns `error_class` field and descriptive messages
  instead of generic "Internal server error".
- Webhook controller verification errors explain which env var to check and
  the expected query parameter format.
- Auth middleware errors name the strategy class that failed.
- `WP_PHONE_ID` validation error explains where to find the value in the Meta
  Business dashboard.
- `InboundRuntime` dispatch context errors include inbox/user/platform context.
- Extracted `_new_http_client()` in WappaCorePlugin to eliminate duplicate
  transport construction (DRY).

### Fixed
- `MessengerFactory` no longer silently uses a closed `httpx.AsyncClient` —
  raises immediately with a diagnostic message.
- Expiry handlers detect closed sessions before attempting messenger creation,
  wrapping in `HTTPSessionNotAvailableError` with inbox-specific context.
- `WappaContextFactory._create_messenger` returns `None` gracefully when the
  session is closed instead of producing a broken messenger.

## [0.13.6] - 2026-05-21

Broadens the Redis serde JSON serialization handler to cover all common Python
types that Pydantic `model_dump()` can produce, preventing `TypeError` crashes
when cached models contain fields beyond `datetime`.

### Changed
- Replaced `_datetime_handler` with `_json_default_handler` in Redis serde,
  adding support for `date`, `time`, `timedelta`, `UUID`, `Decimal`, `Enum`,
  `bytes`, `set`/`frozenset`, `PurePath`, and IP address types.

## [0.13.5] - 2026-05-21

Fixes a Pydantic validation error when WhatsApp sends unsupported message webhooks
containing the `"unsupported": {"type": "unknown"}` sub-payload. The model now
accepts this provider field instead of rejecting it as an extra input.

### Fixed
- Added `unsupported: dict[str, Any] | None` field to `WhatsAppUnsupportedMessage`
  so the model accepts the provider sub-payload WhatsApp attaches to unsupported
  message webhooks (previously caused a 400 response due to `extra="forbid"`).
- Extracted magic error code `131051` to a named module constant.
- Removed dead code: redundant property aliases and a permanently-false predicate.

## [0.13.4] - 2026-05-20

Fixes WhatsApp webhook verification when host applications enable `AuthPlugin`.
Wappa now treats the canonical inbox-scoped webhook route as an unauthenticated
platform webhook surface, and removes stale generated/docs references to the old
inbox-scoped messenger path.

### Fixed
- Added `/webhook/inboxes` to `AuthPlugin.DEFAULT_EXCLUDES` so
  `GET /webhook/inboxes/{inbox_id}/{platform}` verification and
  `POST /webhook/inboxes/{inbox_id}/{platform}` processing bypass JWT/API auth
  and reach Wappa's webhook runtime.
- Updated `WebhookURLFactory` examples, parsing, generated platform details, and
  route extraction helpers to use `/webhook/inboxes/{inbox_id}/{platform}` as
  the canonical processing URL.
- Clarified public contract and generated/example docs so
  `/webhook/messenger/{platform}/verify` is verify-only, while platform webhook
  receiving happens only through `/webhook/inboxes/{inbox_id}/{platform}`.
- Added regression coverage for auth exclusion, verification success/failure,
  route method boundaries, generated `/webhook/platforms` payloads, and stale
  messenger processing path rejection.

## [0.13.3] - 2026-05-18

Upgraded FastAPI to 0.136.1 and all transitive dependencies including Starlette 1.0.0. Wappa now runs on Starlette 1.0+ out of the box — no upper pin. A sibling project (Symphonai) needed a temporary `starlette<1.0` pin due to a startup hang with AnyIO 4.12; that workaround lives in Symphonai's own `pyproject.toml`, not here. If you hit a similar issue in your host application, pin starlette locally until the root cause is identified.

### Changed
- Upgraded FastAPI from 0.135.1+ to 0.136.1 with Starlette 1.0.0 and AnyIO 4.13 in the lock file.
- Refreshed all transitive dependency versions in `uv.lock`.

## [0.13.2] - 2026-05-16

Release-hardening patch for the clean-break architecture release.

### Fixed
- Aligns `uv.lock` package metadata with `pyproject.toml` version `0.13.2`.
- Clears the remaining Ruff findings in the test and message-factory surfaces.
- Updates current plugin and persistence docs to use canonical `inbox_id` and `External Webhook Source` language instead of old `tenant_id` / provider wording.

## [0.13.1] - 2026-05-16

Centralizes Wappa's public import surface into stable, shallow paths so host applications no longer need to reach into internal module structure. Adds a `wappa/sse/` convenience package and populates `wappa/messaging`, `wappa/persistence`, `wappa/webhooks`, `wappa/api`, and `wappa/schemas` with the re-exports that Symphonai (and future consumers) actually use.

### Added
- **`wappa.sse` package** — stable re-exports for all SSE symbols (`publish_sse_event`, `sse_event_scope`, `classify_meta_identifier`, etc.).
- **`wappa.messaging` pipeline exports** — `MessengerMiddleware`, `MessengerPipeline`, `SendInvocation`, `SendNext`, `PRIORITY_CACHE`.
- **`wappa.persistence` Redis exports** — `RedisCacheFactory`, `RedisClient`, `redis_ops`.
- **`wappa.webhooks` base exports** — `BaseMessage`, `InboxBase`, `SystemEventDetail`.
- **`wappa.domain.interfaces`** — `IExpiryCache` now exported alongside other cache interfaces.
- **`wappa.core.logging`** — `get_current_inbox_context`, `set_request_context` re-exported.
- **`wappa.schemas`** — `looks_like_bsuid` re-exported at package level.
- **`wappa.api`** — `TemplateStateService`, `convert_body_parameters`, `raise_for_failed_result`, `require_inbox_context`, `resolve_event_user_id`, `dispatch_message_event`, `fire_api_event`.
- **`docs/public-contract.md`** — canonical import paths reference with v0.13.0 migration notes.

### Fixed
- Type annotation: `dict[str, any]` → `dict[str, Any]` in `SystemWebhook.get_summary`.
- Return type: `get_message_builder` now correctly typed as `Callable[[str], MessageBuilder]`.
- Logger consistency: f-strings → `%s`-style lazy formatting in `error_handler.py`.
- PEP 693: `timezone.utc` → `datetime.UTC` across logging and persistence handlers.

## [0.13.0] - 2026-05-16

Breaking architectural reset: Wappa now speaks its own language. The `inbox_id` replaces `tenant_id`/`owner_id` as the single runtime identity concept, all backward-compatibility shims from the schema migration era are removed, and webhook schema ownership is consolidated under `wappa/webhooks/` (the `wappa/schemas/` mirror is gone). Adds an inbound dispatch context for multi-inbox routing and a database-backed inbox credential store.

### Changed
- **`inbox_id` is the core runtime identity** — replaces `tenant_id`/`owner_id` throughout middleware, logging, cache key factories, context propagation, and plugin lifecycle.
- **Webhook schema consolidation** — `wappa/webhooks/` is now the single source of truth; the duplicated `wappa/schemas/` package (including factory, validators, all message type mirrors) is deleted.
- **Inbound dispatch context** — new `wappa/core/inbound/` module provides `InboundRuntime` for multi-inbox webhook routing with credential resolution.
- **Inbox middleware** — replaces the old `owner` middleware with inbox-aware request scoping.
- **Webhook controller** — simplified from monolithic handler to thin dispatch layer using the inbound runtime.
- **Code quality pass** — lazy log formatting, removed dead helpers, type annotation fixes (`any` → `Any`), collapsed trivial indirections.

### Added
- **`InboxCredentialStore` interface** + `DatabaseInboxCredentialStore` implementation for runtime credential lookup.
- **`InboxCredentialsService`** — domain service wrapping the credential store with caching.
- **`inbox_helpers.py`** — utility for `require_inbox_context()` extraction from requests.

### Removed
- **All compatibility shims** — `wappa/schemas/` package (factory, validators, base models, all WhatsApp message type mirrors, status models, webhook container), `messenger_wrapper.py` (both SSE and pubsub copies), `recipient_resolver.py`, `tenant_helpers.py`, `tenant_credentials_service.py`, `cache_interface.py` (old monolithic interface).
- **`wappa/webhooks/core/types.py`** — dead type aliases.

## [0.12.0] - 2026-05-16

Replaces aiohttp with httpx as the async HTTP client across the entire framework. httpx is the modern Python standard with a cleaner API, sync+async support, HTTP/2, and better typing. Includes SOLID improvements in the WhatsApp client: instance-level activity tracking, transport-agnostic form data builder, safe streaming via async context managers, and cleaner error handling.

### Changed
- **HTTP client migration** — all 6 source files migrated from `aiohttp` to `httpx` (`whatsapp_client.py`, `wappa_core_plugin.py`, `whatsapp_media_handler.py`, `whatsapp_template_info.py`, `messenger_factory.py`, example `media_handler.py`).
- **`WhatsAppClient`** — constructor now accepts `httpx.AsyncClient` instead of `aiohttp.ClientSession`. Request methods return responses directly (no context manager on response).
- **`WhatsAppFormDataBuilder.build_form_data()`** — now returns transport-agnostic `(data, files)` dicts instead of `aiohttp.FormData`.
- **`WhatsAppClient.stream_get()`** — replaces `get_request_stream()` with an `@asynccontextmanager` that eliminates leaked-response risk. Callers use `async with client.stream_get(url) as response:` instead of managing a raw `(session, response)` tuple.
- **`wappa_core_plugin.py`** — session creation uses `httpx.AsyncHTTPTransport` + `httpx.AsyncClient`. Shutdown uses `.aclose()`.
- **`whatsapp_media_handler.py`** — `upload_media_from_url()` uses `httpx.AsyncClient` for auth-isolated downloads. `download_media()` and `stream_media()` use the new `stream_get()` context manager.
- **`whatsapp_template_info.py`** — exception handling updated from `aiohttp.ClientResponseError` to `httpx.HTTPStatusError`.
- **Exception mapping** — `aiohttp.ClientResponseError` → `httpx.HTTPStatusError` (`.status` → `.response.status_code`), `aiohttp.ClientError` → `httpx.HTTPError`.

### Fixed
- **`WhatsAppClient.last_activity`** — moved from class-level (shared across all instances) to instance-level, fixing a bug where multiple tenants would overwrite each other's activity timestamp.
- **Fragile error text capture** — removed `"response" in locals()` antipattern in `get_request`/`delete_request`; httpx's `HTTPStatusError` carries `exc.response.text` directly.

### Removed
- **`aiohttp` direct dependency** — removed from `pyproject.toml`. (Still present as transitive dependency via `fastapi-crons`.)

## [0.11.0] - 2026-05-15

Adds `upload_media_from_url()` to `IMediaHandler` and `WhatsAppMediaHandler`, enabling consumers to download a public URL and re-upload it to the WhatsApp Media API in a single call. Uses an isolated HTTP session with no auth headers to prevent Bearer token leakage to third-party hosts.

### Added
- **`IMediaHandler.upload_media_from_url(url, *, filename, timeout)`** — new abstract method on the platform-agnostic media interface.
- **`WhatsAppMediaHandler.upload_media_from_url()`** — full implementation with MIME validation, two-phase file size enforcement (Content-Length header + streaming guard), automatic filename extension derivation, and auth-isolated download via a fresh `httpx.AsyncClient`.
- **9 unit tests** covering happy path, auth isolation, download failure, missing/unsupported MIME type, size limits (header and streaming), filename extension, and custom timeout.

## [0.10.0] - 2026-05-14

Adds `delete_all_for_user()` to the three user-scoped cache interfaces, allowing callers to wipe all cached state for a user without knowing individual handler/agent/action names. Designed for conversation-close cleanup where the full set of cache keys is unknown.

### Added
- **`IStateCache.delete_all_for_user()`** — deletes every handler state entry for the cache's `user_id`. Implemented in `RedisStateHandler`, `MemoryStateHandler`, and `JSONStateHandler`.
- **`IExpiryCache.delete_all_for_user()`** — deletes every expiry trigger whose identifier matches `user_id`. Implemented in `RedisExpiry`.
- **`IAIStateCache.delete_all_for_user()`** — deletes every AI agent state entry for `user_id` regardless of agent name. Implemented in `RedisAIState`, `MemoryAIState`, and `JSONAIState`.

## [0.9.0] - 2026-05-06

**Breaking** — Fixes doubled `/whatsapp` prefix in all WhatsApp API subrouter paths. Routes that were previously mounted at `/api/whatsapp/whatsapp/messages/...` are now correctly at `/api/whatsapp/messages/...`. All API consumers must update their request paths.

### Changed
- Subrouter prefixes stripped of redundant `/whatsapp` segment: `/whatsapp/messages` → `/messages`, `/whatsapp/media` → `/media`, `/whatsapp/interactive` → `/interactive`, `/whatsapp/templates` → `/templates`, `/whatsapp/state-handlers` → `/state-handlers`, `/whatsapp` (health) → empty.
- Combined router retains `prefix="/api/whatsapp"` — canonical API paths are now `/api/whatsapp/{resource}/...` as originally intended.

## [0.8.2] - 2026-05-05

Standardises the `SYSTEM_LOGS_RICH_FORMAT` env var to accept `TRUE`/`FALSE` (uppercase) consistent with the convention used across all other Wappa boolean env vars.

### Changed
- `SYSTEM_LOGS_RICH_FORMAT` now matches on `TRUE` / `FALSE` (uppercase). The value is uppercased before comparison, so mixed-case inputs are still accepted.

## [0.8.1] - 2026-05-05

Renames the logging format override env var to `SYSTEM_LOGS_RICH_FORMAT` and consolidates all env var reading into `Settings`, eliminating raw `os.getenv` calls from framework code.

### Changed
- **`SYSTEM_LOGS_RICH_FORMAT`** replaces `LOGS_RICH_FORMAT` as the env var that controls Rich vs JSON log formatting. Behaviour is identical; only the name changed.
- **`Settings.logs_rich_format`** (`bool | None`) added to `wappa.core.config.settings`. `setup_app_logging()` now reads this field instead of calling `os.getenv` directly, keeping all env var access in one place.

## [0.8.0] - 2026-05-05

Environment-aware logging that eliminates production log-rate-limit blowouts, plus fixes for the three Memory and JSON cache backends that could not be instantiated due to missing abstract-method implementations.

### Added
- **`WappaJSONFormatter`** — a `logging.Formatter` subclass that emits one valid JSON object per line (`ts`, `level`, `logger`, `msg`, and optionally `tenant`, `user`, `exc`). Exception tracebacks are serialised into the `exc` field with newlines escaped so the single-line contract is never broken. Context prefixes (`[T:…][U:…]`) injected by `ContextLogger` are parsed out and promoted to structured fields. Importable from `wappa.core.logging`.
- **`SYSTEM_LOGS_RICH_FORMAT` env var** — `TRUE` forces Rich output in any environment; `FALSE` forces JSON. When absent, falls back to `settings.is_development` (Rich in dev, JSON in prod). Takes precedence over `SYSTEM_ENVIRONMENT`.
- **`setup_logging(rich_format=True)`** — new keyword-only parameter. When `False`, attaches a plain `StreamHandler` with `WappaJSONFormatter` instead of `RichHandler`. Default `True` preserves existing behaviour for direct callers.
- **`MemoryStateHandler.delete_by_handler_prefix`**, **`list_handlers`**, **`list_users_with_handler`** — implementations of the abstract methods added to `IStateCache` in 0.7.2/0.7.3.
- **`JSONStateHandler.delete_by_handler_prefix`**, **`list_handlers`**, **`list_users_with_handler`** — same interface; `list_users_with_handler` globs per-tenant state files and extracts user IDs from stored keys.
- **`MemoryAIState.delete_by_agent_prefix`** and **`JSONAIState.delete_by_agent_prefix`** — implementations of the abstract method added to `IAIStateCache` in 0.7.2.

### Fixed
- `MemoryAIState`, `MemoryStateHandler`, `JSONStateHandler`, and `JSONAIState` could not be instantiated (`TypeError: Can't instantiate abstract class …`) because abstract methods added to `IStateCache` and `IAIStateCache` in 0.7.2–0.7.3 were never implemented in the non-Redis backends.
- Production deployments on Railway (and any per-line log-ingestion platform) would exceed the 500 events/sec rate limit on a single webhook error due to `RichHandler` with `tracebacks_show_locals=True` being applied unconditionally. `setup_app_logging()` now defaults to compact JSON in non-development environments.

## [0.7.3] - 2026-05-02

Adds `IStateCache.list_users_with_handler`, the tenant-scoped inverse of `list_handlers`. Callers can now enumerate every `user_id` that holds active state for a given handler name without importing internal Redis ops or building raw SCAN patterns.

### Added
- **`IStateCache.list_users_with_handler(cls, tenant_id, handler_name) -> list[str]`** — classmethod; scans `{tenant}:state:{handler_name}:*` across all users for the tenant and returns the matching `user_id` list. Fills the API gap that prevented `human_takeover/services/__init__.py:list_all_active` from migrating off raw `scan_keys`.

## [0.7.2] - 2026-05-02

Adds prefix/glob-aware bulk operations to `IStateCache`, `ITableCache`, and `IAIStateCache`, bringing them to parity with the `delete_all_by_identifier` pattern already present on `IExpiryCache`. Consumers can now wipe or enumerate namespaced entries without importing internal Redis ops or constructing raw key patterns.

### Added
- **`IStateCache.delete_by_handler_prefix(prefix)`** — deletes every handler entry whose name starts with `prefix` for the scoped `user_id`; pattern `{tenant}:state:{prefix}*:{user_id}`. Raises `ValueError` on empty prefix.
- **`IStateCache.list_handlers(prefix=None)`** — returns all handler names currently stored for the user; optional `prefix` filter narrows the result.
- **`ITableCache.delete_table(table_name)`** — deletes every row in `table_name` for the tenant; pattern `{tenant}:df:{table}:pkid:*`. Raises `ValueError` on empty name.
- **`ITableCache.list_pkids(table_name)`** — returns all pkids stored for a table under this tenant.
- **`IAIStateCache.delete_by_agent_prefix(prefix)`** — deletes every agent-state entry whose name starts with `prefix` for the scoped `user_id`; pattern `{tenant}:aistate:{prefix}*:{user_id}`. Raises `ValueError` on empty prefix.
- **`TenantCache._scan_keys_by_pattern(pattern)`** — shared internal helper (collect-without-delete SCAN loop) used by the new listing methods.

## [0.7.1] - 2026-05-02

WhatsApp message status webhook brought up to date with Meta's reference as of Apr 30 2026. Adds the two status values previously dropped at validation (`played` for voice-note playback receipts, `deleted` for sender-deleted messages), loosens inbound schema strictness so additive Meta payload changes no longer crash the parser, and corrects a pricing-category enum typo that was rejecting `authentication_international` payloads.

### Added
- `MessageStatus.PLAYED` enum value and corresponding `WhatsAppMessageStatus.is_played` / `is_deleted` helpers; `is_successful` now treats `played` as a delivery-equivalent terminal state.
- Per-status counters and emoji icons for `played` / `deleted` in the default status handler and event dispatcher; `IMPORTANT_ONLY` log strategy now surfaces both.

### Changed
- `WhatsAppMessageStatus.wa_status` literal extended to `sent | delivered | read | played | failed | deleted` — voice-played and deleted webhooks now parse instead of 422'ing.
- Status submodels (`WhatsAppMessageStatus`, `Conversation`, `ConversationOrigin`, `Pricing`, `MessageError`, `ErrorData`) flipped from `extra="forbid"` to `extra="ignore"` so future additive Meta fields are tolerated rather than rejected.
- `Pricing.billable` is now optional (`bool | None`); the field is being phased out under PMP (Per-Message Pricing).
- `validate_status_consistency` now only enforces the `failed → errors` invariant; informational errors on non-failed statuses are accepted.

### Fixed
- `Pricing.category` literal `authentication-international` → `authentication_international` (underscore) to match Meta's documented enum and `ConversationOrigin.type`.
- Dropped the hardcoded `wamid.` prefix check on message IDs and the empty-`statuses[]` rejection in `WhatsAppStatusWebhook` — both were stricter than the documented contract and could drop valid payloads.

## [0.7.0] - 2026-05-02

Identity-resolution seam (introduced in 0.6.1 for templates) now applies uniformly across every Wappa subsystem that scopes per-user state. Host applications register one `IIdentityResolver` and have it apply to template state, handler state, outbound API events, and pub/sub envelopes — eliminating the recurrent bug class where one Wappa surface keys cache by canonical id while another keys by raw transport recipient.

### Added
- **`HandlerStateService`** now accepts an optional `IIdentityResolver` (default `PassthroughIdentityResolver`). All four methods (`set_handler_state`, `get_handler_state`, `delete_handler_state`, `handler_state_exists`) gain an optional `user_id=` override kwarg that bypasses the resolver. Cached envelope now includes both `recipient` (transport) and `user_id` (canonical).
- **`user_id` query param** on `GET /whatsapp/state-handlers/get/{recipient}/{handler_value}` and `DELETE /whatsapp/state-handlers/delete/{recipient}/{handler_value}` — explicit canonical-id override for HTTP callers that already resolved identity upstream.
- **`SetHandlerStateRequest.user_id`** is now forwarded through to the service (was already present on `RecipientRequest` but ignored).
- **`resolve_event_user_id(recipient, explicit_user_id, fastapi_request)`** helper in `wappa.api.utils.event_decorators` — single resolution-precedence chain (explicit > resolver-on-app-state > raw recipient) used by all `APIMessageEvent` construction sites.
- **`user_id` kwarg on `dispatch_api_message_event(...)`** — fire-and-forget helper now resolves identity through `resolve_event_user_id` and populates the (previously missing) required `APIMessageEvent.user_id` field.
- **Resolver propagation tests** (`tests/test_identity_resolver_propagation.py`) covering default-passthrough, custom-resolver, and explicit-override paths for `HandlerStateService`, `TemplateStateService`, `resolve_event_user_id`, and `publish_api_notification`.

### Changed
- **`@dispatch_message_event` decorator** and **`fire_api_event`** now route the event's `user_id` through `resolve_event_user_id`. When a resolver is registered on `app.state.identity_resolver`, outbound events carry the canonical id; explicit `user_id` on the request body still wins.
- **`publish_api_notification`** (Redis pub/sub) now keys the envelope by `event.user_id` (canonical, post-resolver) instead of `event.recipient`. The raw transport identifier is preserved inside the payload as `data.recipient` so consumers that need it still have it.
- **`get_handler_state_service` DI helper** now forwards the registered `IIdentityResolver` from `app.state` into the service, mirroring `get_template_state_service`.
- **`ICacheFactory` and `RedisCacheFactory` docstrings** updated to recommend scoping caches by the canonical id (`event.user_id`) rather than `event.recipient`, with a note explaining the values are equal under the default passthrough resolver.

### Fixed
- **`dispatch_api_message_event` was constructing `APIMessageEvent` without the now-required `user_id` field**, which would have raised at runtime under any caller. Now resolves and supplies it.

### Compatibility
- Fully backwards-compatible. Apps that do not register an `IIdentityResolver` see byte-identical behavior to 0.6.1: cache keys, pub/sub envelopes, and `APIMessageEvent.user_id` all default to the raw `recipient`. Every change is additive — no existing call site needs modification.

## [0.6.1] - 2026-05-02

Pluggable identity-resolution seam for template state caching. Wappa no longer hard-codes the assumption that the WhatsApp transport recipient (phone number) is the canonical id under which to scope per-user cache state. Host applications can now register an `IIdentityResolver` once at startup to map transport identifiers to whatever canonical user id they use internally (BSUID, account id, household id, etc.). Default behavior is unchanged — naive deployments keep using the recipient as the cache `user_id`.

### Added
- **`IIdentityResolver`** interface (`wappa.IIdentityResolver`) with `PassthroughIdentityResolver` default. Single seam for mapping transport recipients to canonical user ids.
- **`WappaBuilder.with_identity_resolver(resolver)`** and **`Wappa.set_identity_resolver(resolver)`** registration APIs. Resolver is exposed at `app.state.identity_resolver` for DI consumers.
- **`TemplateStateConfig.user_id`** — optional explicit canonical id on the HTTP template-send payload. When provided, bypasses the resolver entirely (use when the caller has already resolved identity upstream).
- **`user_id` kwarg on `TemplateStateService.set_template_state`** — additive escape hatch for in-process callers that already hold a canonical id.

### Changed
- **`TemplateStateService.set_template_state`** now resolves the cache `user_id` via the injected `IIdentityResolver` (default passthrough) before calling `cache_factory.create_state_cache(user_id=…)`. The cached state envelope now includes the resolved `user_id` alongside `recipient` for traceability.
- Removed an internal reflection block (`cache_factory.__class__.__name__.replace("CacheFactory","").lower()` + concrete `create_cache_factory` re-import) that bypassed the `ICacheFactory` contract. The service now uses the existing per-call `user_id` override on `ICacheFactory.create_state_cache(...)`, restoring strict DIP compliance.

### Compatibility
- Backwards-compatible. Apps that do not register a resolver see identical behavior to 0.6.0 (recipient used as cache `user_id`). The new `user_id` field on `TemplateStateConfig` and the new `user_id` kwarg on `set_template_state` are both optional.

## [0.6.0] - 2026-05-01

Marketing template transport split is now first-class: Wappa routes marketing templates through Meta's MM-LITE endpoint (`/marketing_messages`) while keeping utility/auth templates on the standard Cloud API endpoint (`/messages`). This release also hardens the template send contract by making template category explicit and required.

### Added
- **MM-LITE route support** in WhatsApp transport via `/{PHONE_NUMBER_ID}/marketing_messages`.
- **Template category enum** for send-template flows: `marketing`, `utility`, `authentication`.
- **`override` route control** for marketing templates (`override=false` forces Cloud `/messages`).
- **Regression tests** for category/override validation and endpoint route selection.
- **Custom webhook field handler registry** for Meta fields not modeled natively (e.g. `message_template_status_update`, `account_update`, `phone_number_quality_update`):
  - `FieldHandlerRegistry` with parser + handler registration and duplicate/collision guards.
  - `CustomWebhook` universal webhook type and dispatcher support.
  - Registry-aware webhook field validation path in WhatsApp processor.
  - Public registration APIs via `WappaBuilder.register_webhook_field(...)` and `Wappa.register_webhook_field(...)`.

### Changed
- **Template send routing policy**:
  - `template_type=marketing` defaults to MM-LITE (`/marketing_messages`).
  - `template_type=utility|authentication` always uses Cloud API (`/messages`).
  - Non-marketing + `override=true` is rejected with validation error.
- **Code-quality refactor** across messenger/template stack to reduce duplication and improve SOLID boundaries without changing behavior.
- **Webhook processor/dispatcher flow** now accepts and dispatches registered custom field payloads instead of rejecting unknown fields at schema level.

### Breaking
- **`template_type` is now mandatory** for template send operations (`send-text`, `send-media`, `send-location`) and internal `IMessenger` template methods.
- Existing callers that did not provide template type must now pass it explicitly.

## [0.5.1] - 2026-04-30

Hard cut on legacy env var support. v0.5.0 shipped alias resolution with deprecation warnings — this patch removes all of that boilerplate. The canonical names from v0.5.0 are now the only names accepted. If an old name is detected at startup the process exits immediately with a clear error listing every var that needs renaming. No silent drift, no compatibility shims.

### Changed
- **`settings.py`** — `_resolve_with_alias()` removed entirely. All env vars read directly via `os.getenv` using canonical names only.
- **`_check_legacy_vars()`** — new startup guard that raises `EnvironmentError` listing every stale var found, with the canonical rename for each. Fails fast before any framework state is initialised.
- `_validate_whatsapp_credentials()` now reports all missing vars in a single error instead of failing on the first one.

### Migration
Same renames as v0.5.0 — if you skipped that release, rename these in your `.env`:

```
ENVIRONMENT              → SYSTEM_ENVIRONMENT
LOG_LEVEL                → SYSTEM_LOG_LEVEL
LOG_DIR                  → SYSTEM_LOG_DIR
TIME_ZONE                → SYSTEM_TIME_ZONE
API_VERSION              → META_API_VERSION
BASE_URL                 → META_BASE_URL
WHATSAPP_WEBHOOK_VERIFY_TOKEN → WP_WEBHOOK_VERIFY_TOKEN
```

## [0.5.0] - 2026-04-30

**Breaking change** — env var naming policy. All framework-owned runtime vars now live under a `SYSTEM_*` prefix; the Meta Graph API version var moves to `META_API_VERSION`. WhatsApp transport vars are fully consolidated under `WP_*`. All old names are accepted as legacy aliases and emit a `DeprecationWarning` at startup, so existing deployments continue to work until you migrate.

### Changed
- **`SYSTEM_ENVIRONMENT`** is now canonical (was `ENVIRONMENT`).
- **`SYSTEM_LOG_LEVEL`** is now canonical (was `LOG_LEVEL`).
- **`SYSTEM_LOG_DIR`** is now canonical (was `LOG_DIR`).
- **`SYSTEM_TIME_ZONE`** is now canonical (was `TIME_ZONE`).
- **`META_API_VERSION`** is now canonical (was `API_VERSION`).
- **`META_BASE_URL`** is now canonical (was `BASE_URL`).
- **`WP_WEBHOOK_VERIFY_TOKEN`** is now canonical (was `WHATSAPP_WEBHOOK_VERIFY_TOKEN`) — consolidates the `WP_*` namespace for all WhatsApp transport credentials.
- **`settings.wp_webhook_verify_token`** — Python attribute renamed to match (`was whatsapp_webhook_verify_token`).
- `PORT`, `DATABASE_URL`, `REDIS_URL`, and all other `WP_*` / `REDIS_*` vars are unchanged.

### Added
- **`_resolve_with_alias(canonical, legacy, default)`** — internal helper in `wappa.core.config.settings` that resolves a canonical env var name first and falls back to a legacy alias with a one-time `DeprecationWarning`.
- **`.env.example`** (root) — new source-of-truth template with a policy block at the top explaining the five ownership namespaces (`PORT`/`DATABASE_URL`/`REDIS_URL` unprefixed; `SYSTEM_*`; `META_*`/`WP_*`; `OPENAI_*`/`ANTHROPIC_*`; app-specific prefix of your choice).
- All six CLI example `.env.example` templates updated to the canonical names.

### Migration

Rename these vars in your `.env` (old names continue to work but warn at startup):

```
# Old → New
ENVIRONMENT              → SYSTEM_ENVIRONMENT
LOG_LEVEL                → SYSTEM_LOG_LEVEL
LOG_DIR                  → SYSTEM_LOG_DIR
TIME_ZONE                → SYSTEM_TIME_ZONE
API_VERSION              → META_API_VERSION
BASE_URL                 → META_BASE_URL (rarely set; internal default is unchanged)
WHATSAPP_WEBHOOK_VERIFY_TOKEN → WP_WEBHOOK_VERIFY_TOKEN
```

If you reference `settings.whatsapp_webhook_verify_token` in your app code, rename it to `settings.wp_webhook_verify_token`.

## [0.4.0] - 2026-04-20

Messenger middleware pipeline. Replaces the inheritance-based wrapper stack (``SSEMessengerWrapper``, ``PubSubMessengerWrapper``) with a priority-ordered ``MessengerPipeline`` and ``MessengerMiddleware`` protocol. Cross-cutting concerns (cache, SSE lifecycle, pub/sub notifications, retry, metrics, tracing) are now each a ~40–60 LOC class registered through one public API. The ``WebhookController`` no longer hardcodes wrapper composition; plugins no longer communicate with it through ``app.state`` boolean flags; downstream apps that needed custom ordering (e.g. "cache write must finish before SSE publishes") no longer drill private attributes to achieve it. Fully backwards compatible — legacy wrappers remain as thin deprecation shims.

### Added
- **``wappa.core.messaging.pipeline``** — new public module exposing ``MessengerPipeline``, ``MessengerMiddleware`` (Protocol), ``SendInvocation``, ``SendNext``, and ``MiddlewareEntry``. The pipeline implements ``IMessenger`` once; adding a new ``IMessenger`` method now touches a single file instead of every wrapper.
- **``SendInvocation``** — frozen dataclass capturing ``method_name``, ``message_type``, ``recipient``, ``args``, ``kwargs``, and ``arguments`` (keyed by parameter name for uniform event emission). ``with_arguments(...)`` builds a rewritten copy for middleware that modify payloads.
- **``WappaBuilder.add_messenger_middleware(mw, priority=50)``** — register middleware around every outbound ``IMessenger`` call. Plugins and user code use the same API; the controller stays agnostic. Priority bands: ``PRIORITY_RELIABILITY=10``, ``PRIORITY_NOTIFICATIONS=30``, ``PRIORITY_CACHE=50``, ``PRIORITY_LIFECYCLE=70``, ``PRIORITY_OBSERVABILITY=90`` (exported as constants).
- **``SSELifecycleMiddleware``** — ``wappa/core/messaging/middleware/sse_lifecycle.py``. ~50 LOC. Replaces the 465-LOC ``SSEMessengerWrapper`` with the same ``flush → await → publish`` semantics and the same wire envelope.
- **``PubSubNotificationMiddleware``** — ``wappa/core/messaging/middleware/pubsub_notification.py``. Replaces ``PubSubMessengerWrapper``. App-scoped (constructed once); reads tenant + user identity from the active ``SSEEventContext`` instead of per-request construction.
- **``MessengerPipeline.raw_messenger`` and ``MessengerPipeline.middleware_chain``** — public introspection properties so tests and debugging no longer need underscore drilling.
- **Docs** — new [MessengerMiddleware.md](./wappa/core/plugins/README/MessengerMiddleware.md) covering the pipeline, priority bands, and how to write custom middleware. Architecture.md, SSEEventsPlugin.md, and RedisPubSubPlugin.md updated to describe the new surface.

### Changed
- **``WebhookController._create_request_handler``** — the hardcoded ``if app.state.pubsub_wrap_messenger / if app.state.sse_wrap_messenger`` branching is gone. It builds one ``MessengerPipeline`` from ``app.state.messenger_middleware`` regardless of which plugins are active.
- **``WappaContextFactory._create_messenger``** (non-webhook entry points: API, expiry) — same simplification; both call sites now go through the pipeline.
- **``SSEEventsPlugin``** — creates the ``SSEEventHub`` in ``configure()`` (sync, safe — only asyncio primitives) and registers ``SSELifecycleMiddleware`` via ``add_messenger_middleware`` at priority 70. No longer sets ``app.state.sse_wrap_messenger``.
- **``RedisPubSubPlugin``** — registers ``PubSubNotificationMiddleware`` via ``add_messenger_middleware`` at priority 30 during ``configure()``. No longer sets ``app.state.pubsub_wrap_messenger``.

### Deprecated
- **``SSEMessengerWrapper``** (``wappa.core.sse.messenger_wrapper``) — emits ``DeprecationWarning`` on construction. Functional equivalent lives in ``SSELifecycleMiddleware``. Removal planned for **v0.6.0**.
- **``PubSubMessengerWrapper``** (``wappa.core.pubsub.messenger_wrapper``) — same deprecation policy. Use ``PubSubNotificationMiddleware`` via ``RedisPubSubPlugin``.
- **``app.state.sse_wrap_messenger``** and **``app.state.pubsub_wrap_messenger``** — the framework no longer reads them. Will be removed alongside the deprecated wrappers in v0.6.0.

### Migration
No action required for apps that build through the plugin surface (``SSEEventsPlugin``, ``RedisPubSubPlugin``). The SSE wire envelope is identical to v0.3.7.

Apps that bypassed the plugin surface and constructed wrappers directly (rare but documented as a pattern for custom cache ordering) migrate with one line:

```python
# Before (drills private attributes on every upgrade)
raw = app_messenger._inner._inner
hub = app_messenger._event_hub
app_messenger = SSEMessengerWrapper(
    inner=CacheMessengerWrapper(inner=raw, ...),
    event_hub=hub,
)

# After
builder.add_messenger_middleware(
    CacheMessengerMiddleware(cache=...),
    priority=50,  # PRIORITY_CACHE — runs inside the SSE lifecycle band (70),
                  # so SSE publishes after the cache write completes
)
```

### Backlog
A future [Domain Event Bus](wappa/core/plugins/README/MessengerMiddleware.md#future-work) (``bus.subscribe(OutgoingMessageDispatched, handler)`` replacing middleware-as-subscribers) is documented but explicitly deferred — the current surface handles the observed workload; the bus will be promoted when ≥5 observers of the same event exist in production or when cross-event subscriber composition becomes necessary.

## [0.3.7] - 2026-04-20

Eager emission of ``incoming_message`` SSE events. v0.3.6 deferred the emission until ``post_process_message`` so metadata the app set during ``process_message`` could land on the envelope — correct for metadata, but it inverted the wire order: subscribers saw ``outgoing_bot_message`` before ``incoming_message``, which broke optimistic UI renderers that rely on arrival order. v0.3.7 flushes the staged payload at the first signal that identity + metadata is ready, without sacrificing enrichment.

### Added
- **``flush_incoming_sse()``** (``wappa.sse``) — explicit flush of any staged ``incoming_message`` payload. Idempotent: the first caller claims the pending payload and schedules the publish as a background task; subsequent callers are no-ops.
- **``SSEEventContext._pending_flush``** — per-request async callback the default handler registers at stage time so the flush is callable from anywhere that has the context.

### Changed
- **``update_metadata(**kwargs)``** now auto-flushes a staged ``incoming_message`` after merging. The first metadata update signals "identity + metadata ready" → the event emits immediately, before the handler sends its reply.
- **``update_identity(...)``** same auto-flush after writing identity fields.
- **``SSEMessengerWrapper._send_with_sse``** calls ``flush_incoming_sse()`` before running the outgoing operation — ordering guard that guarantees ``incoming_message`` precedes ``outgoing_bot_message`` even when the app never enriches metadata.
- **``SSEMessageHandler.post_process_message``** reduced to a safety-net call to ``flush_incoming_sse()`` for pipelines that never enrich and never send (pure logging handlers).

### Migration
None. Fully backwards-compatible with v0.3.6 apps — no signature changes, no removed exports. Apps using ``update_metadata`` / ``update_identity`` from inside their pipeline now see ``incoming_message`` fire right after that call instead of at the end, with the same envelope contents.

## [0.3.6] - 2026-04-20

Identity and domain-context propagation across every SSE event, end-to-end. Breaking cleanup of the v0.3.4 identity-threading approach: no more per-construction ``bsuid``/``phone_number``/``metadata`` arguments on wrappers or publishers; a single request-scoped ``SSEEventContext`` populated at each framework entry point drives every envelope that fires inside it. Fixes the v0.3.4/0.3.5 null-identity and missing-metadata bugs in ``outgoing_bot_message`` and ``incoming_message`` at the root.

### Added
- **``wappa.sse`` module** — public surface for app-side SSE context manipulation:
  - ``update_metadata(**kwargs)`` — merge domain fields (e.g. ``conversation_id``, ``chat_id``, ``run_id``) into the envelope of every SSE event emitted inside the current scope.
  - ``update_identity(user_id=None, bsuid=None, phone_number=None)`` — override identity fields after a cache/DB lookup promotes a wa_id-only request to a canonical BSUID.
  - ``get_context()`` — direct read access to the active ``SSEEventContext``.
  - ``sse_event_scope(...)`` — async context manager that installs a fresh ``SSEEventContext`` (used internally by framework entry points; exposed for standalone scripts and tests).
  - ``derive_identifiers(user_obj)`` — extract ``(bsuid, phone_number)`` from any ``UserBase``-shaped object.
  - ``classify_meta_identifier(value)`` — split a Meta identifier by shape into ``(bsuid, phone_number)`` using the canonical BSUID regex.
- **Deferred ``incoming_message`` emission** — ``SSEMessageHandler.log_incoming_message`` now stages the normalised payload on the active context instead of publishing immediately. The framework flushes it from ``post_process_message`` (after ``process_message`` returns), so metadata the app set during its pipeline lands on the envelope subscribers see.
- **Automatic context population at every entry point**:
  - ``WebhookController`` opens a scope before dispatch, derived from ``webhook.user`` for incoming messages and ``classify_meta_identifier`` for status/error webhooks.
  - ``APIEventDispatcher`` opens a scope around ``handle_api_message`` using ``event.user_id`` and ``event.recipient``.
  - ``ExpiryDispatcher`` opens a scope around every expiry handler task using the key's tenant and identifier.

### Changed (Breaking)
- ``publish_sse_event(event_hub, *, event_type, source, payload)`` — removed ``tenant_id``, ``user_id``, ``bsuid``, ``phone_number``, ``platform``, ``metadata`` arguments. All envelope identity + metadata is read from the active ``SSEEventContext``.
- ``SSEEventHub.publish(*, event_type, source, payload)`` — same removal; envelope built from the active context.
- ``SSEMessengerWrapper(inner, event_hub)`` — removed ``tenant``, ``user_id``, ``bsuid``, ``phone_number``, ``metadata`` constructor arguments and the ``update_metadata(**kwargs)`` instance method.
- ``SSEMessageHandler`` / ``SSEStatusHandler`` / ``SSEErrorHandler`` — removed ``metadata`` constructor argument and ``update_metadata(**kwargs)`` method from all three.
- ``SSEEventsPlugin(metadata=...)`` constructor argument and ``update_metadata(**kwargs)`` runtime fan-out — removed. Per-request metadata is now the only metadata, and it lives on the context.
- ``WappaContextFactory.create_context(..., bsuid=..., phone_number=...)`` — removed the identity kwargs. The SSE wrapper reads everything from context.
- ``publish_api_sse_event(event_hub, event)`` — removed the ``metadata`` argument; promotes ``event.user_id`` / ``event.recipient`` onto the active context before publishing.

### Migration
Apps that were constructing ``SSEMessengerWrapper`` manually (e.g. inside expiry or cron handlers that built their own messenger chain) must:

1. Drop the ``tenant=``, ``user_id=``, ``bsuid=``, ``phone_number=``, ``metadata=`` kwargs from the constructor — keep only ``inner=`` and ``event_hub=``.
2. Wrap the handler body in ``async with sse_event_scope(tenant_id=..., user_id=..., bsuid=..., phone_number=...):`` so the wrapper has identity to publish with. Standalone handlers outside the framework dispatchers need this; framework-dispatched handlers get it automatically.
3. Replace ``messenger.update_metadata(run_id=..., conversation_id=...)`` with ``wappa.sse.update_metadata(run_id=..., conversation_id=...)``.
4. Replace any ``SSEMessageHandler(metadata=...)`` / ``SSEStatusHandler(metadata=...)`` / ``SSEErrorHandler(metadata=...)`` / ``SSEEventsPlugin(metadata=...)`` constructor kwargs and their ``update_metadata(...)`` calls with ``wappa.sse.update_metadata(...)`` calls inside the pipeline (or with ``sse_event_scope(metadata={...})`` kwarg for request-initial values).

### Tests
- Added ``tests/test_sse_context_flow.py`` (8 cases): scope set/reset, ``update_metadata`` and ``update_identity`` on an active scope, no-op behaviour outside a scope, envelope identity propagation, default envelope when no scope is active, ``SSEMessengerWrapper`` publishing from context, deferred ``incoming_message`` picking up mid-pipeline metadata, and the empty-staged-payload safety case.

## [0.3.5] - 2026-04-20

Hotfix for `SSEMessageHandler` using the wrong attribute name on `UserBase`.

### Fixed
- `SSEMessageHandler.log_incoming_message()` was reading `user.wa_id` to populate `phone_number` in the SSE envelope. `UserBase` exposes `phone_number`, not `wa_id` (`wa_id` lives on the WhatsApp-specific `WhatsAppContact` subclass and `WhatsAppIncomingWebhookData`). The field is now read as `user.phone_number`, matching the universal interface contract.

## [0.3.4] - 2026-04-20

Patch release enriching SSE event envelopes with explicit `bsuid` and `phone_number` identity fields alongside the existing canonical `user_id`.

### Changed
- **SSE envelope gains `bsuid` and `phone_number` top-level fields** — every event published through `SSEEventHub.publish()` now carries both identity signals explicitly. `user_id` continues to hold the canonical identifier (BSUID when present, wa_id otherwise); `bsuid` and `phone_number` let consumers distinguish the two without pattern-matching the canonical value.
- `publish_sse_event()` and `SSEEventHub.publish()` / `_build_event()` accept the new optional `bsuid: str | None` and `phone_number: str | None` keyword arguments (default `None` — fully backwards-compatible).
- `SSEMessageHandler.log_incoming_message()` populates both fields from `webhook.user.bsuid` and `webhook.user.wa_id` for all `incoming_message` events. Empty strings are normalised to `None`.
- `SSEMessengerWrapper.__init__()` accepts `bsuid` and `phone_number` and threads them into every `outgoing_bot_message` event.
- `WappaContextFactory.create_context()` and `_create_messenger()` accept `bsuid` and `phone_number` and forward them to `SSEMessengerWrapper` when wrapping the outbound messenger.

## [0.3.3] - 2026-04-20

Patch release adding an optional `user_id` parameter to every outbound send endpoint and `StatusWebhook`, and flipping `UserBase.user_id` to prefer BSUID over wa_id across all webhook types.

### Added
- **`user_id` on all outbound endpoints** (`send-text`, `send-image`, `send-audio`, `send-document`, `send-video`, `send-sticker`, `send-buttons`, `send-list`, `send-cta`, `send-template`, etc.). Optional field — defaults to `recipient` when omitted, fully backwards-compatible. Added to `RecipientRequest` base schema so all 12+ send endpoints inherit it with zero per-endpoint changes.
- **`APIMessageEvent.user_id`** — required field (always populated by the decorator, defaulting to `recipient`). `APIEventDispatcher` now binds this value into `self.user_id` inside `process_api_message()` handlers, so state/cache lookups see the canonical domain id instead of the Meta transport value.
- **`StatusWebhook.user_id`** — new field on the inbound status model. Processor populates it with BSUID when present, phone (wa_id) as fallback. `WebhookController` adds a best-effort Redis scan (`find_by_field("phone_number", ...)`) to enrich `user_id` to BSUID when Meta sends only a wa_id and a matching user exists in the store.
- `fire_api_event()` helper gains an optional `user_id` parameter for callers that use the helper directly instead of the decorator.

### Changed
- **`UserBase.user_id` now prefers BSUID over wa_id** (reverting the preference flip from v0.3.2). BSUID is the stable, Meta-assigned long-term identifier; wa_id is the transport value. This aligns `IncomingMessageWebhook.user.user_id` and `SystemWebhook.user.user_id` with the BSUID-first contract established by `StatusWebhook.recipient_id`. Applications that want the raw wa_id should read `webhook.user.phone_number` or `webhook.whatsapp.wa_id` explicitly.
- `APIEventDispatcher._create_api_request_handler` uses `event.user_id` (not `event.recipient`) as the context `user_id` binding.
- Status webhook log now shows `webhook.user_id` instead of `webhook.recipient_id`.

### Tests
- Added `tests/test_user_id_flow.py` with 12 tests covering: `RecipientRequest.user_id` inheritance, `APIMessageEvent` field contract, `APIEventDispatcher` context binding (canonical vs. fallback), and `StatusWebhook.user_id` lifecycle (BSUID present, phone-only, enrichment override, no identifiers).
- Updated 3 tests in `test_whatsapp_processor_user_base.py` to reflect BSUID-first resolution.

## [0.3.2] - 2026-04-20

Patch release that flips the preferred identifier resolved by `IncomingMessageWebhook.user.user_id`.

### Changed
- **Breaking-ish preference flip**: `UserBase.user_id` now prefers the WhatsApp `wa_id` (exposed as `user.phone_number`) and only falls back to `bsuid` when `wa_id` is not present in the webhook. Previously BSUID was preferred whenever it was available. Meta tenants that don't yet have BSUID outbound messaging enabled can now use `webhook.user.user_id` directly for replies without workarounds. Applications that were relying on BSUID being the canonical `user_id` should switch to `webhook.user.bsuid` (raw field) or `webhook.whatsapp.bsuid`.
- Simplified the `init` example's `master_event.py` — the `wa_id or phone_number or user_id` fallback chain is no longer needed; `webhook.user.user_id` now resolves to the wa_id by default.

### Fixed
- `UserBase.user_id` no longer returns an empty string when both `phone_number` and `bsuid` are unset in constructed/edge-case payloads; the property now explicitly returns `""` as the final fallback (unchanged observable behavior, documented guarantee).

### Tests
- Updated `test_create_user_base_from_contacts_preserves_wa_id_when_bsuid_exists` and `test_create_universal_webhook_accepts_contact_without_profile` to assert the new resolution order (`user_id == wa_id` when both are present).
- Added `test_user_id_falls_back_to_bsuid_when_phone_number_missing` to lock in the BSUID fallback path.

## [0.3.1] - 2026-04-20

Patch release focused on stabilizing the BSUID rollout handling introduced in `0.3.0`.

### Fixed
- Prefer the WhatsApp numeric `wa_id` for the `init` example's reply path, instead of the BSUID-preferred `webhook.user.user_id`, so the example keeps working on tenants where BSUID outbound messaging is not yet enabled.
- Fixed `WhatsAppContactAdapter` and `WhatsAppWebhookProcessor` so `IncomingMessageWebhook.whatsapp.wa_id` and `IncomingMessageWebhook.user.phone_number` preserve the sender `wa_id` even when a BSUID is present.
- Relaxed WhatsApp webhook contact parsing so `contacts[].profile` is optional; Meta can omit `profile` in real production webhooks and Wappa now parses those payloads without failing the entire webhook.
- Improved outbound WhatsApp HTTP logging to capture the exact Meta error response body and a structured error summary before `raise_for_status()` discards the details.
- Masked Authorization headers in outbound request/error logs to avoid leaking full bearer tokens in debug output.

### Added
- Added regression coverage for WhatsApp client error logging, WA ID preservation when BSUID is present, and webhook parsing when `contacts[].profile` is omitted.

### Changed
- Removed `IncomingMessageWebhook.user.platform_user_id` from the universal user contract for this hotfix path and exposed WhatsApp-specific sender data under `IncomingMessageWebhook.whatsapp` instead.
- `IncomingMessageWebhook.user.user_id` now consistently resolves to the preferred stable identifier (BSUID first, then phone number), while `IncomingMessageWebhook.whatsapp.wa_id` is the explicit field for WhatsApp reply routing.

## [0.3.0] - 2026-04-20

Major architectural hardening release. ~3,500 lines of dead code and redundancy removed, two real runtime bugs fixed, enum duplication eliminated across the codebase, factory pattern completed for cross-platform message types, **and the recipient contract formalized to handle Meta's BSUID rollout transparently**.

### 🆔 Recipient Contract Formalization (Most Important Change for End Users)

**Context**: Meta introduced **BSUID** (Business-Scoped User ID) as an alternative recipient identifier alongside phone numbers in the WhatsApp Cloud API. Meta also changed the transport field name depending on identifier type — phone numbers go in `"to"`, BSUIDs go in `"recipient"`. Applications that hardcoded `"to": phone` were silently breaking when handed a BSUID.

**Wappa's response in v0.3.0**: the framework now owns the entire identifier-to-transport resolution so that application code stays identifier-agnostic.

- **Stable public contract**. Your code keeps calling `self.messenger.send_*(..., recipient=...)` exactly as before. Nothing in the bot layer needs to change to support BSUIDs.
- **Automatic transport routing**. Wappa inspects the identifier shape and routes it to the correct WhatsApp field:
  - Phone number (e.g. `+573001234567`) → emitted as `"to"` in the payload
  - BSUID (e.g. `CO.abc123`) → emitted as `"recipient"` in the payload
  - The old and new field names never leak out of the adapter.
- **Format validation at the boundary**. Phone numbers are sanitized (strip spaces/dashes/parens) then matched against `^\+?[1-9]\d{6,20}$`. BSUIDs must match `^[A-Z]{2}\.[A-Za-z0-9]{1,128}$` with the country prefix validated against the full ISO 3166-1 alpha-2 set. Invalid identifiers are rejected with `ValueError` before any HTTP call.
- **No automatic fallback**. If Meta rejects a BSUID for a message type that does not support BSUID recipients (e.g. authentication templates), Wappa returns an explicit `MessageResult.error_code = "BSUID_RECIPIENT_NOT_SUPPORTED"` (backed by Meta error code `131062`). The framework does **not** silently downgrade to a phone number, because only the application knows whether a phone number is available for that user and whether downgrading is legally / product-wise acceptable. If your application wants fallback, implement it in your event handler around the returned `MessageResult`.
- **New public types** under `wappa.schemas.core.recipient`:
  - `RecipientKind` enum (`PHONE_NUMBER`, `BSUID`)
  - `ResolvedRecipient` — the normalized identifier with its target transport field
  - `RecipientRequest` — shared Pydantic boundary model that adapter request models inherit from, so every inbound FastAPI route canonicalizes the `recipient` field the same way
  - `apply_recipient_to_payload(payload, recipient)` — mutator used by every outbound WA method
  - `resolve_recipient()`, `normalize_recipient_identifier()`, `looks_like_phone_number()`, `looks_like_bsuid()` — helpers for custom integrations

**If you are a Wappa user, this is the change that matters**. Everything else in this release is internal hardening; this section is why v0.3.0 exists as a coordinated release rather than a string of patches. You get BSUID support without touching a line of your bot code.

### 🐛 Bug Fixes (Real Issues Found)

- **`MediaType` enum shadowing in WhatsAppMessenger**: `whatsapp_messenger.py` imported `MediaType` from `media_models` at module level, then re-imported a **different** `MediaType` (from `template_models`, with only 3 members vs. the canonical 5) as a local import. This silently shadowed the canonical enum in a 400+ line section of the module. Fixed by renaming the template variant to `WhatsAppTemplateMediaType` and removing the local import.
- **Case-sensitive authentication detection**: `is_authentication_error()` checked `"Unauthorized"` with exact case, missing lowercase variants like `"unauthorized request"` emitted by some HTTP libraries. Fixed to compare case-insensitively.

### 🏗️ Architectural Changes

- **Factory pattern completed for cross-platform messages**: `WhatsAppMessenger` now accepts `WhatsAppMessageFactory` and `WhatsAppMediaFactory` via dependency injection. `send_text`, `mark_as_read`, and `_send_media` (powering `send_image`, `send_video`, `send_audio`, `send_document`, `send_sticker`) delegate payload construction to factories instead of building inline. Factories remain the single source of truth for text/media/read-status payloads. Interactive, template, and specialized messages continue to delegate through their platform-specific handlers — this is intentional since those concepts (WhatsApp buttons, WA-only templates, etc.) do not map cleanly across platforms like Telegram or Instagram.
- **Messenger constructor is backward-compatible**: `message_factory` and `media_factory` are optional kwargs; if omitted, default instances are created — so existing user code that constructs `WhatsAppMessenger(...)` directly keeps working.
- **Centralized BSUID error handling**: `ERROR_CODE_BSUID_NOT_SUPPORTED = 131062` and `BSUID_ERROR_TAG = "BSUID_RECIPIENT_NOT_SUPPORTED"` are now defined once in `wappa/messaging/whatsapp/utils/error_helpers.py`. The API layer's `ERROR_CODE_MAPPING` and the webhook layer's `is_bsuid_auth_error()` both import from this single source instead of hardcoding the values in three places.
- **`ContextLogger` accepted as logger parameter**: `handle_whatsapp_error()` now accepts `Logger | ContextLogger`, removing the need for `cast(Logger, self.logger)` gymnastics at call sites.

### 🧹 Dead Code Removed

- **`InteractiveType` enum shadow** (`wappa/messaging/whatsapp/models/interactive_models.py`): removed entirely — zero references to its members (`BUTTON`, `LIST`, `CTA_URL`) anywhere in the repo. The canonical cross-platform `InteractiveType` in `wappa.schemas.core.types` is unaffected.
- **`handle_messaging_result`** (`wappa/api/utils/error_helpers.py`): exported publicly but zero callers across the entire repo (tests, examples, docs included). Removed from the module and from `wappa.api.utils.__init__` exports.
- **`validate_coordinates` on `WhatsAppSpecializedHandler`**: orphaned — the API route has its own inline validation; the handler method was never invoked.
- **`get_template_info` on `WhatsAppTemplateHandler`**: returned hardcoded fake data (`status=APPROVED`, `category=MARKETING`); no callers; removed to avoid latent bugs.

### 🔄 Enum Deduplication

- **`wappa/webhooks/core/types.py` is now a re-export shim** of `wappa/schemas/core/types.py`. The two files were previously byte-for-byte identical (254 lines each). The 13+ existing imports from `wappa.webhooks.core.types` continue to work unchanged, but now they resolve to the canonical enum objects — so `wappa.webhooks.core.types.InteractiveType is wappa.schemas.core.types.InteractiveType` evaluates `True`.
- **`MediaType` in `template_models` renamed to `WhatsAppTemplateMediaType`**: the template-specific media enum (only IMAGE/VIDEO/DOCUMENT) now has a name that makes its WA-only scope obvious. The canonical `MediaType` with 5 members (AUDIO/DOCUMENT/IMAGE/STICKER/VIDEO) in `media_models` is unchanged.

### ✨ Simplifications (~3,500 lines removed)

Six specialized simplifier agents ran in parallel over the codebase, each focused on a bounded zone. Total net removal ~3,500 lines, broken down as:

- Messenger core: ~1,150 lines
- Persistence layer (cache factory, JSON/memory/Redis backends): ~620 lines
- Core event flow and webhook dispatcher: ~485 lines
- WhatsApp handlers (interactive, template, specialized): ~449 lines
- CLI and API entry surfaces: ~416 lines
- Models and schema boundaries: ~379 lines

Highlights:
- Multi-line docstrings stripped across the codebase; replaced with one-line comments only where WHY is non-obvious.
- `if/elif` chains replaced with Python 3.12 `match/case` statements where they reduced branching depth.
- Duplicated body-parameter validators in `TextTemplateMessage`, `MediaTemplateMessage`, `LocationTemplateMessage` extracted to a shared `_ensure_text_body_parameters()` helper.
- Duplicated latitude/longitude validators consolidated into `_validate_coordinate(value, label, limit)`.
- `RecipientRequest` shared boundary model introduced in `wappa/schemas/core/recipient.py` and reused by all adapter-facing request models.
- Dead `InteractiveType` shadow enum removed; `MediaType` shadow renamed for clarity.
- Redundant `_normalize_cache_type` helper inlined in `cache_factory.py`.
- `_NAMESPACES` tuple introduced in `MemoryStore` to eliminate 4-way duplication across `__init__`, cleanup, and namespace guards.

### ✅ Quality

- **Ruff F-checks**: 0 errors across `wappa/` package.
- **Test suite**: 16/16 pass.
- **New test coverage**: `tests/test_whatsapp_payload_factories.py` and `tests/test_recipient_resolution.py` lock in the recipient routing contract and factory behavior. `tests/test_cache_backends_contracts.py` covers cache-factory edge cases.

### 📋 Upgrade Notes

This is a **minor-version bump (0.2.x → 0.3.0)** rather than a patch because of the scope of internal restructuring. The public library surface (`from wappa import Wappa, WappaEventHandler, WappaBuilder`) is unchanged and backward compatible.

**Breaking changes** (narrow internal API only — most users will not be affected):
- `wappa.messaging.whatsapp.models.template_models.MediaType` → `WhatsAppTemplateMediaType`. If you imported the old name from this specific module (not from `wappa.messaging.whatsapp.models.media_models`), update the import.
- `wappa.api.utils.handle_messaging_result` removed. If you somehow depended on it, migrate to `raise_for_failed_result`.
- `wappa.messaging.whatsapp.models.interactive_models.InteractiveType` removed (was dead code). Use `wappa.schemas.core.types.InteractiveType` for cross-platform interactive type classification.

**Non-breaking enhancements**:
- `WhatsAppMessenger.__init__` accepts new optional `message_factory` and `media_factory` kwargs.
- `handle_whatsapp_error` accepts `Logger | ContextLogger`.

## [0.2.32] - 2026-04-14

### Added
- Added optional `metadata` dict support to `TextTemplateMetadata`, `MediaTemplateMetadata`, and `LocationTemplateMetadata`.
- Exposed template metadata models from `wappa.messaging.whatsapp.models` for downstream schema imports.
- Added an active `backlog/` workflow with documentation and a tracked template management/webhook backlog.
- Added typed `Templates Info` request and response schemas for template-by-id, template-by-name, template list, and namespace reads.
- Added a dedicated WABA-level template info service for Graph API management reads.

### Changed
- Split template API documentation into `WhatsApp - Send Templates` and `WhatsApp - Templates Info`.
- Backed template info reads with a dedicated WABA management URL builder instead of the phone-number send path.
- Normalized the Specialized tag to `WhatsApp - Specialized` for OpenAPI consistency.
- Removed the public placeholder registration for template management routes until the feature is ready.
- Bumped package version from `0.2.31` to `0.2.32` for the template schema and management-info release.

## [0.2.18] - 2026-03-06

### Changed
- Bumped package version from `0.2.17` to `0.2.18` for release publishing.
- Refreshed lock/build artifacts for the new release version.

## [0.2.0] - 2025-01-11

### Added
- **PostgresDatabasePlugin**: Production-ready async PostgreSQL plugin with 30x-community inspired patterns
  - Asyncpg-powered async engine for high-concurrency conversational apps
  - Connection pooling with configurable pool_size, max_overflow, and timeouts
  - Exponential backoff retry logic for transient database failures
  - Auto-table creation at startup with SQLModel support
  - Statement cache size configuration for Supabase pgBouncer compatibility
  - Comprehensive error handling and health checks

- **RedisPubSubPlugin**: Multi-tenant Redis PubSub messaging system
  - Self-subscribing pattern for bot-to-bot communication
  - Multi-tenant channel management with automatic subscription
  - Channel-based event broadcasting and listening
  - Graceful startup/shutdown with subscription cleanup
  - Example implementation with tenant isolation

- **AIState Pool and Cache System**: Multi-backend state management
  - Pool 4 implementation with Redis, JSON, and Memory backends
  - Conversation state tracking with TTL support
  - Cache factory pattern for easy backend switching

- **CLI Examples Showcase**: Two new production-ready examples
  - `db_redis_echo_example`: PostgreSQL + Redis two-tier storage with SOLID architecture
  - `redis_pubsub_example`: Multi-tenant PubSub with self-subscribing pattern
  - Both now visible in `wappa examples` command

### Changed
- **SOLID Architecture Refactoring**: db_redis_echo_example refactored from monolithic to clean architecture
  - Reduced master_event.py from 700 lines to 258 lines
  - Separated concerns into handlers/, models/, utils/ structure
  - Created comprehensive scaffolding guide documentation
  - Improved testability and maintainability

- **Configuration Management**: db_redis_echo_example now uses Settings class pattern
  - Replaced os.getenv with DBRedisSettings extending base Settings
  - Type-safe configuration with validation at startup
  - Consistent with Wappa's configuration patterns

### Fixed
- **WhatsApp Media Message Schemas**: Added missing `url` field to all media types
  - Fixed video, document, image, audio, and sticker message validation
  - Support for WhatsApp's new direct download URLs in webhook payload
  - Implemented missing abstract methods in WhatsAppVideoMessage

- **Message Persistence**: Enhanced structured data storage for special message types
  - Contact messages: Store full contact data in json_content JSONB field
  - Location messages: Store coordinates and location metadata
  - Interactive messages: Store button/list selections
  - Reaction messages: Store emoji and target message reference

### Documentation
- Created wappa-project-scaffolding-guide.md with SOLID best practices
- Created message-persistence-guide.md for database storage patterns
- Updated db_redis_echo_example README with architecture documentation
- Added comprehensive docstrings to PostgresDatabasePlugin

### Dependencies
- Added asyncpg>=0.31.0 for async PostgreSQL support

## [0.1.10] - Previous Release

Initial stable release with core WhatsApp webhook handling, messaging, and caching capabilities.

---

[0.2.18]: https://github.com/sashanclrp/wappa/compare/v0.2.0...v0.2.18
[0.2.0]: https://github.com/sashanclrp/wappa/compare/v0.1.10...v0.2.0
[0.1.10]: https://github.com/sashanclrp/wappa/releases/tag/v0.1.10
