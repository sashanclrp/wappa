---
id: 006
title: Defer Messenger Seam Split
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
    - small/fast models that cannot evaluate interface blast radius
execution_note: >
  This PRD does not protect backwards compatibility at all costs. It says the
  current best design is to keep one public Messenger seam until real evidence
  justifies a clean breaking split.
---

# Tech Request: Defer Messenger Seam Split

## Why This Matters

`IMessenger` is wide, but it is currently Wappa's public outbound message interface for Host Applications. Splitting it into `TextMessenger`, `MediaMessenger`, `TemplateMessenger`, or similar seams would be a breaking public-contract change. Breaking changes are acceptable in this Wappa cleanup, but only when they buy real architectural depth.

The cleanest architectural choice today is to document why the seam stays whole and tighten internal WhatsApp modules only where it improves locality.

Telegram, Instagram, and WhatsApp are expected to have similar webhook/API categories. That does not yet prove the public seam should split.

## Canonical Language

| Term | Meaning |
|------|---------|
| **Messenger** | Wappa's outbound message interface for Host Applications. |
| **Message Family** | Internal grouping such as text, media, interactive, template, or specialized messages. |
| **Platform Adapter** | Platform-specific implementation of webhook parsing and outbound message delivery. |

## What To Build

This PRD proposes a future implementation decision. Do not split Messenger while writing this PRD.

1. Keep `Messenger` / `IMessenger` as the public outbound interface.
2. Document the decision not to split the public seam yet.
3. Allow internal platform adapters to keep handler composition by message family.
4. Tighten WhatsApp internal modules only if it improves clarity without changing the public Messenger contract.
5. Define the threshold that would justify a future split.
6. If that threshold is met later, split with a clean breaking change and no compatibility aliases.

## What NOT To Build

- No public `TextMessenger`, `MediaMessenger`, `TemplateMessenger`, or `InteractiveMessenger` yet.
- No public Messenger API break in this PRD unless another PRD proves the split is the best design.
- No speculative abstractions before a second real platform adapter creates pressure.

## Split Threshold

Revisit the Messenger split only when at least one of these becomes true:

- A second real platform adapter cannot implement `IMessenger` coherently.
- Tests repeatedly need smaller Messenger fakes because the wide interface creates concrete pain.
- Host Applications need to depend on a smaller outbound capability set for security or lifecycle reasons.
- Message families diverge enough that keeping one interface hides real invariants.

## Acceptance Criteria

- [ ] Messaging docs state that Messenger remains the public seam.
- [ ] Internal WhatsApp handler composition remains allowed.
- [ ] No new public Messenger sub-interfaces are introduced.
- [ ] Any implementation cleanup preserves current `IMessenger` behavior.
- [ ] Future split criteria are documented.
- [ ] Docs state that a future split, if justified, should be a clean breaking change.

## Affected Files

- `wappa/domain/interfaces/messaging_interface.py`
- `wappa/messaging/ARCHITECTURE.md`
- `wappa/messaging/CONTEXT.md`
- `wappa/messaging/whatsapp/messenger/whatsapp_messenger.py`
- `wappa/messaging/whatsapp/handlers/**`
- tests for Messenger behavior and factories
