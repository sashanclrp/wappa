---
id: 004
title: Consolidate Webhook Schemas and Universal Models
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
    - small/fast models without repository-wide import analysis
execution_note: >
  This is a breaking source-of-truth cleanup. It must preserve Pydantic
  validation for every platform payload and every Universal Model form.
---

# Tech Request: Consolidate Webhook Schemas and Universal Models

## Why This Matters

Wappa has two competing inbound schema areas:

- `wappa/webhooks`
- `wappa/schemas`

The target architecture is not "schemas are bad." Wappa should have Pydantic schemas for every webhook. The issue is ownership and duplication.

Every Universal Model form must also be a Pydantic schema. Future Telegram, Instagram, and Teams payloads must each have platform-specific Pydantic schemas that translate into the same Universal Models. Today the WhatsApp-first universal shapes live in `wappa/webhooks`, while older schema modules still create ambiguity about source of truth.

## Canonical Language

| Term | Meaning |
|------|---------|
| **Webhook Schema** | A Pydantic model that validates a platform-specific webhook payload or a universal webhook shape. |
| **Universal Webhook Schema** | A Pydantic schema for one Universal Model form, such as `InboundMessageWebhook`, `StatusWebhook`, `ErrorWebhook`, `SystemWebhook`, or `CustomWebhook`. |
| **Universal Model** | Platform-agnostic Pydantic schema representation that leaves `wappa/webhooks` and enters dispatch. |
| **Platform Schema** | Platform-specific payload schema, such as WhatsApp or future Telegram webhook payloads. |
| **Shared Primitive Schema** | Cross-cutting schema used by outbound APIs, recipient normalization, enums, or shared request/response models. |

## What To Build

This PRD proposes a future implementation change. Do not implement it while writing this PRD.

1. Make the Webhooks context the canonical owner of inbound webhook schemas and Universal Models.
2. Keep Pydantic schemas for every webhook payload and every Universal Webhook Schema.
3. Decide which `wappa/schemas` modules are still legitimate shared primitives.
4. Move or delete duplicated inbound webhook models from `wappa/schemas`.
5. Update imports so inbound code depends on `wappa/webhooks`, not legacy schema paths.
6. Keep `PlatformType`, `MessageType`, and recipient primitives only where the final architecture says they belong.

## What NOT To Build

- No compatibility shims for old inbound model import paths.
- No dual source of truth for WhatsApp webhook payloads.
- No removal of Pydantic validation.
- No untyped Universal Model forms.
- No platform-specific leak into Universal Model naming.

## How

1. Inventory all modules under `wappa/schemas` and classify them:
   - inbound webhook schemas
   - outbound request/response schemas
   - shared primitives/enums
   - dead or duplicate modules
2. Move canonical inbound schemas under `wappa/webhooks`.
3. Delete old duplicate inbound schema paths.
4. Update all imports and examples.
5. Add tests proving WhatsApp payloads still parse into Universal Models.
6. Add a small future-platform test fixture showing how a non-WhatsApp payload can map into the same Universal Model shape.

## Acceptance Criteria

- [ ] `wappa/webhooks` owns all inbound webhook schemas and Universal Models.
- [ ] Each Universal Model form is a Pydantic schema.
- [ ] `wappa/schemas` contains only shared primitives or non-inbound request/response models.
- [ ] No inbound webhook model exists in two canonical locations.
- [ ] No compatibility import path remains for moved inbound models.
- [ ] WhatsApp webhook parsing tests still pass.
- [ ] Documentation explains how a future platform maps into Universal Models.

## Affected Files

- `wappa/webhooks/**`
- `wappa/schemas/**`
- `wappa/processors/**`
- `wappa/core/events/**`
- `wappa/core/sse/**`
- `wappa/core/pubsub/**`
- CLI examples importing inbound webhook models
- tests for user/message/status/system webhook parsing
