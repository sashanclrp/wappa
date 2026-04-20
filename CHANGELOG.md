# Changelog

All notable changes to Wappa will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
