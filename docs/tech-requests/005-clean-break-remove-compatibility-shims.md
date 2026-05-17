---
id: 005
title: Clean Break Compatibility Removal
status: proposed
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

## Current Compatibility/Legacy Findings

Initial scan found these candidates for removal or rename:

| Location | Finding | Target |
|----------|---------|--------|
| `wappa/webhooks/core/types.py` | Re-export shim to `wappa.schemas.core.types` | Remove or move canonical types to one location. |
| `wappa/core/expiry/listener.py` | "Re-export backward compatibility functions" | Delete old functions/imports. |
| `wappa/core/expiry/app_context.py` | "Backward compatibility functions" | Delete old functions/imports. |
| `wappa/domain/interfaces/cache_interface.py` | Backwards-compatible generic cache interface | Delete if type-specific cache interfaces fully replace it. |
| `wappa/messaging/whatsapp/recipient_resolver.py` | Backward-compatible re-export of recipient utilities | Delete and update imports. |
| `wappa/core/sse/messenger_wrapper.py` | Legacy `SSEMessengerWrapper` deprecation shim | Delete and require messenger middleware. |
| `wappa/core/pubsub/messenger_wrapper.py` | Legacy `PubSubMessengerWrapper` deprecation shim | Delete and require messenger middleware. |
| `wappa/webhooks/whatsapp/status_models.py` | Status aliases for compatibility | Delete aliases and update imports. |
| `wappa/core/logging/logger.py` | `get_logger()` compatibility alias behavior | Decide whether this is public API or remove alias behavior. |
| `wappa/core/plugins/webhook_plugin.py` | Raw handler v1 backwards compat and `provider` parameter | Rename to External Webhook Source language; remove raw v1 mode if not canonical. |
| `wappa/core/config/settings.py` | Legacy env var detection | Decide whether this is migration help or compatibility behavior; remove if clean break requires it. |
| CLI examples | Multiple "compatibility" comments and old imports | Update examples to canonical APIs. |

## What To Build

This PRD proposes a future implementation change. Do not implement it while writing this PRD.

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

- [ ] No module is documented as a compatibility shim.
- [ ] No old import path remains for renamed canonical concepts.
- [ ] No messaging platform code uses `provider` as a code identifier.
- [ ] External webhook code uses `external_source` or a specific domain term.
- [ ] CLI examples compile/import with canonical APIs.
- [ ] Full test suite passes.

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
