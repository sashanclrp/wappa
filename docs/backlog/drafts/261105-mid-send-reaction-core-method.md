---
status: draft
origin: ADR-0016 contract map (2026-11-05)
---

# `send_reaction` as a core Messenger method

WhatsApp, Instagram and Telegram all let a business react to a User's message with an emoji, so by [ADR-0016](../../adr/0016-one-messenger-method-per-action.md) this is one core `IMessenger` method, not a Platform capability.

## Gap today

- No Platform adapter can send a reaction.
- Inbound Instagram reactions (`message_reactions` field) are translated to `SystemWebhook(UNSUPPORTED_EVENT)` and dropped. WhatsApp inbound reactions should be checked for the same shape.

## Proposed contract

`send_reaction(message_id: str, emoji: str, target: DirectMessage) -> MessageResult`, with an empty `emoji` meaning "remove my reaction" where the Platform supports it.

| Platform | Outbound | Inbound |
| --- | --- | --- |
| WhatsApp | `type: reaction` with `message_id` and `emoji` | `messages[].reaction` |
| Instagram | `sender_action: react` / `unreact` with `payload.message_id` and `reaction` (Meta allows a fixed reaction set) | `message_reactions` field |
| Telegram | `setMessageReaction` | `message_reaction` update |

Inbound reactions should become one Universal shape on every Platform (an update to an earlier message, like `MessageUpdateWebhook`), not a per-Platform lane.

## Open questions

- Instagram's reaction vocabulary is narrower than WhatsApp's emoji set: map, or reject unsupported emoji before I/O?
- Should inbound reactions extend `MessageUpdateWebhook` (`update_kind = reacted`) or be their own Universal type?

## Exit criteria

- One method on `IMessenger`, implemented by WhatsApp and Instagram, with tests and live evidence.
- Inbound reactions from both Platforms arrive in one Universal shape.
