# Platform Registry and the PlatformWebhooks seam

Status: Proposed, 2026-11-05. Draft for the architecture-hardening backlog (H-06, H-08, H-09, H-10, H-11, H-12).

## Context

ADR-0010 made the callback payload-routed and authenticated before parse, and ADR-0002 split routing (I/O) from translation (pure). Both decisions hold. What never got a name is the inbound seam itself: the runtime calls `processor_factory.get_processor(platform).create_universal_webhook` after one of two routers with the same signature, so the Platform is re-decided in five places (webhook controller allow-set and router ternary, processor factory if/elif, `WappaApp` field-registry wiring, core plugin labels, field registry `_builtin_fields`) against three disagreeing supported-Platform lists. The Messenger factory and the credential service repeat the pattern, for 9 sites across 6 shared files, and every else-branch treats an unlisted Platform as WhatsApp. Next to the live seam sits a dead parallel one (`wappa/webhooks/factory.py`, `PlatformDetector`, `WebhookFactory`, `ProcessorCapabilities`, `PLATFORM_CAPABILITIES`) that root `ARCHITECTURE.md` still lists as required steps for a new Platform. The controller's GET check accepts every `PlatformType`, so an uninstalled Platform answers a Meta challenge.

## Decision

1. `PlatformWebhooks` is a Protocol in `wappa/core/inbound/platform_webhooks.py` with four members: `platform`, `builtin_fields`, `async route(payload, resolver) -> tuple[RoutedWebhookDelivery, ...]` (may do credential I/O) and `async translate(payload, *, inbox_id) -> UniversalWebhook` (pure). `RoutedWebhookDelivery` and `PayloadRoutingError` live in the same module. Callback authentication stays in the controller (ADR-0010) and is not a protocol member while every Platform is a Meta callback; message-type tables stay private to each adapter.
2. `wappa/platforms.py` is the composition root. `PLATFORMS: Mapping[PlatformType, PlatformEntry]` is built once by `build_platforms(field_registry)`; `PlatformEntry` is a frozen dataclass holding the `PlatformWebhooks` adapter, the Messenger builder and a display name. It replaces `ProcessorFactory`. Platform-specific imports and branches are legitimate only here and in adapter folders.
3. `PLATFORMS.keys()` is the one installed-Platform set. The webhook controller (GET and POST), `/webhook/platforms`, the status route, the core plugin, `RoutePlatform` and `MessengerFactory` read it. A missing key fails loudly (HTTP 400, `ValueError`), never falls through to WhatsApp.
4. `PlatformType` is vocabulary, not installation. Members without an entry (Telegram, Teams) are reserved and serve as the uninstalled Platform in contract tests.
5. The credential-record union stays a static discriminated union; `RECORD_TYPES` beside it maps each Platform to its active and inactive classes so no service branches on Platform.
6. The field registry takes each adapter's `builtin_fields`; SSE identity is read from neutral evidence fields (`UserBase`, `CallWebhook`, `StatusWebhook`), never from a Platform check or identifier shape.
7. The dead parallel seam is deleted outright.

## Consequences

A third Platform touches its adapter folders, one `PlatformEntry`, one `PlatformType` member and one credential-record pair. `tests/test_third_platform_contract.py` proves this with a fake Platform defined only in the test, plus a guard test that fails on new Platform comparisons in shared code. `WappaBuilder.mount_whatsapp_callback` becomes `mount_webhook_callback`; `generate_whatsapp_*` URL wrappers and the `schemas.core.types` capability helpers are removed (clean cut, CHANGELOG). A non-Meta Platform will need `authenticate` added to the protocol at that time.

## Supersedes

None fully. Amends ADR-0010 (adapter registration; the "registered platform adapter" check becomes a registry lookup) and ADR-0002 (`create_universal_webhook` becomes `PlatformWebhooks.translate`). Banner both on acceptance.
