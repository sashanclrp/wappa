# Changelog

All notable changes to Wappa will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
A future [Domain Event Bus](./backlog/260420-messenger-middleware-domain-event-bus.md) (``bus.subscribe(OutgoingMessageDispatched, handler)`` replacing middleware-as-subscribers) is documented but explicitly deferred — the current surface handles the observed workload; the bus will be promoted when ≥5 observers of the same event exist in production or when cross-event subscriber composition becomes necessary.

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
