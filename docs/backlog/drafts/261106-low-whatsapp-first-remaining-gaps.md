---
status: draft
origin: WhatsApp-first sweep (2026-11-06), findings F11, F13, F14
---

# WhatsApp-first: remaining contract gaps

The WhatsApp-first sweep found fourteen places where the neutral contract was narrower than the WhatsApp Cloud API. F1 to F10 and F12 are fixed (shared shapes follow WhatsApp, limits are the minimum across Platforms, Instagram emulates). Three remain, each needing a design pass.

| id | Gap | WhatsApp supports | Proposed fix | Instagram |
| --- | --- | --- | --- | --- |
| F11 | No reaction send (`docs/public-contract.md` known gap; detail in [261105-mid-send-reaction-core-method.md](./261105-mid-send-reaction-core-method.md)) | `reaction` with any emoji on a `message_id`; an empty emoji removes it | `send_reaction(message_id, emoji, target)` as a core `IMessenger` method | `sender_action` `react` / `unreact`; Instagram accepts only `love` (a heart) |
| F13 | Interactive types Wappa does not offer | `flow`, `voice_call`, `call_permission_request`, `catalog_message`, `product`, `product_list`, `address_message` | decide per type: Flows and calling belong to their own drafts ([Flows](./261105-mid-whatsapp-flows-prd.md), [calling](./261105-mid-whatsapp-calling-prd.md)); products to [commerce](./261105-mid-commerce-capability.md); `address_message` needs its own call | product template for products; flow and voice_call cannot be emulated (`UnsupportedOperationError`) |
| F14 | Result and Template detail Wappa drops | `message_status` on send (`accepted`, `held_for_quality_assessment`, `paused`); Template button parameters, header text parameters, document `filename`, reply `context` | a neutral `provider_status` on `MessageResult`; widen `ITemplateMessaging` with the missing Template parameters | n/a (Instagram has no Templates and no send status) |

## Open user decision (F11)

Instagram reactions only accept a heart. Either the Instagram adapter maps every emoji to `love` (meaning kept as "reacted", the exact emoji lost), or it rejects anything but a heart with `UnsupportedOperationError` before any call. The rule "presentation may be dropped, meaning never" fits both readings; the user has not chosen yet. Removal (empty emoji) maps to `unreact` either way.

Exit: each row either implemented on both Platforms with tests and contract docs, or moved to its own draft with a recorded decision.
