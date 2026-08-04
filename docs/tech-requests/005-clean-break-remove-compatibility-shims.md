---
id: 005
title: Clean Break Compatibility Removal
status: implemented
request_type: architecture-prd
model_fit:
  primary_100_percent:
    - GPT-5.5
    - GPT-5.4
    - GPT-5.3-Codex
  delegatable_with_review:
    - Claude Opus 4.6
    - Claude Sonnet 4.6
  not_recommended_for_autonomous_execution:
    - small/fast models without import graph and test repair ability
execution_note: >
  This PRD intentionally allows Host Applications to break. Do not preserve old
  names through aliases unless a later ADR explicitly reverses the clean-break decision.
---

# Tech Request: Clean Break Compatibility Removal

## Why This Matters

Wappa is intentionally moving to a clean, canonical framework language. Compatibility shims and old import paths keep obsolete concepts alive and make future platform work harder.

If host applications break, that is acceptable. They should adapt to the clean Wappa public contract.

## Canonical Language

| Term | Meaning |
|------|---------|
| **Clean Breaking Change** | Intentional removal or rename that forces Host Applications to adopt canonical Wappa language. |
| **External Webhook Source** | Non-messaging system that sends webhooks to Wappa. |
| **Payment Provider** | Payment-specific External Webhook Source such as MercadoPago, Stripe, or Wompi. |

`Compatibility Shim` is not accepted as Wappa architecture.

## Compatibility/Legacy Findings Resolved

The implementation audit resolved every candidate from the initial scan:

| Area | Resolution |
|------|------------|
| Inbound schemas and types | Removed duplicate import paths; `wappa.webhooks` is the sole inbound owner and `wappa.schemas` keeps shared primitives only. |
| Expiry runtime | Kept one explicit `AppContext`; removed old convenience/re-export functions. |
| Persistence contracts | Removed the generic cache interface and the unused repository-interface family; only type-specific cache contracts remain. |
| Recipient resolution | Removed the re-export module; canonical recipient primitives live under `wappa.schemas.core.recipient`. |
| SSE and PubSub | Removed wrapper classes; `MessengerPipeline` middleware is the only composition path. |
| Status models | Removed compatibility aliases; canonical WhatsApp status schemas remain. |
| Logging and settings | Removed obsolete accessors and legacy environment detection; retained only current public behavior. |
| External webhooks | `WebhookPlugin` uses `external_source` and the deep External Webhook Runtime only. |
| Templates and examples | Removed the compatibility-only Template status endpoint/model and stale example aliases/ignored parameters. |

## What To Build

This request has been implemented. The list below records the delivered scope.

1. Remove compatibility shims and old import paths.
2. Rename or delete compatibility-only APIs.
3. Update all internal imports and CLI examples.
4. Keep only canonical public APIs documented in `docs/public-contract.md`.
5. Replace messaging `provider` language with `platform`.
6. Replace external webhook `provider` language with `external_source` or a more specific term such as `payment_provider`.
7. Update release notes or migration docs only after the canonical code is clean; do not keep runtime aliases for migration comfort.

## What NOT To Build

- No deprecation window.
- No aliases for old names.
- No dual import paths.
- No "provider" language for messaging platforms.

## How

1. Build an import graph for the findings above.
2. Delete one compatibility seam at a time.
3. Update internal imports, examples, docs, and tests.
4. Run full tests after each seam removal.
5. Update `docs/public-contract.md` to list only surviving public APIs.

## Acceptance Criteria

- [x] No executable module is a compatibility shim.
- [x] No old import path remains for renamed canonical concepts.
- [x] No messaging platform code uses `provider` as a code identifier.
- [x] External webhook code uses `external_source` or a specific domain term.
- [x] CLI examples compile/import with canonical APIs.
- [x] Full test suite passes.

## Affected Files

- `wappa/webhooks/core/types.py`
- `wappa/core/expiry/listener.py`
- `wappa/core/expiry/app_context.py`
- `wappa/domain/interfaces/cache_interface.py`
- `wappa/messaging/whatsapp/recipient_resolver.py`
- `wappa/core/sse/messenger_wrapper.py`
- `wappa/core/pubsub/messenger_wrapper.py`
- `wappa/webhooks/whatsapp/status_models.py`
- `wappa/core/logging/logger.py`
- `wappa/core/plugins/webhook_plugin.py`
- `wappa/core/config/settings.py`
- `wappa/cli/examples/**`
- `docs/public-contract.md`
