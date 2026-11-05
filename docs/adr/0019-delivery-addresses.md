# Explicit targets carry every known Delivery Address; the Platform adapter chooses

Accepted, 2026-11-05. Amends [ADR-0014](0014-instagram-text-and-explicit-messenger-targets.md) (`DirectMessage` held one address) under [ADR-0016](0016-one-messenger-method-per-action.md) (one way to do one thing).

## Context

Since Wappa's first commit every send names its recipient; ADR-0014 wrapped the string in `DirectMessage(inbox_ref, recipient_id)`. On 2026-11-05 a WhatsApp reply addressed to the User's BSUID failed from a Meta test number with `131030 Recipient phone number not in allowed list`, although the same webhook also carried the User's phone (`contacts[].wa_id`) and that phone was on the allow-list. A one-address target cannot fall back, so every Host would have to code its own retry: the same logic, repeated per consumer.

We considered binding the recipient into the Messenger (a conversation-bound Messenger with an optional `target`). It was rejected:

- **Two ways to address a message** (bound or explicit) doubles the paths every test, middleware and rule must cover, against ADR-0016.
- **The Messenger is transport**: Platform, Inbox, credentials, middleware. Who receives a message is a per-execution decision. Operator sends, campaigns, reminders and an agent messaging a different User are normal uses of one transport with many targets, not exceptions.

The binding was never needed for the fallback: the information belongs on the target.

## Decision

1. **One way to address: an explicit target on every send.** `DirectMessage(inbox_ref, addresses=DeliveryAddresses)` replaces `DirectMessage(inbox_ref, recipient_id=str)`. The Messenger stays recipient-agnostic and knows only its Platform, Inbox and credentials.
2. **`DeliveryAddresses` states what is known, never the strategy.** `DeliveryAddresses.of(*addresses)` takes every known address of one User (unknowns skipped, at least one required). Webhooks build it for Hosts: `webhook.user.delivery_addresses()` returns WhatsApp's BSUID and phone, or Instagram's scoped ID. The Parent BSUID is identity evidence, not a fallback. Hosts that send outside a webhook (operators, campaigns, reminders) supply the addresses they have stored; Wappa does not store Users (ADR-0018).
3. **The Platform adapter orders and falls back; the generic pipeline does not.** The WhatsApp adapter sends to the phone first, then the BSUID, following Meta: "If the user's phone number is not present (the wa_id property is missing), you can use their BSUID", and `to` (phone) takes precedence when both are sent ([BSUIDs](https://developers.facebook.com/documentation/business-messaging/whatsapp/business-scoped-user-ids)). Instagram has one address per User and never falls back.
4. **Fall back only when Meta rejects the address itself.** The next address is tried only after a synchronous rejection that happens before any delivery: `131030` (test-number allow-list) and `131062` (this message type cannot go to a BSUID; Wappa tag `BSUID_RECIPIENT_NOT_SUPPORTED`). Window (`131047`), rate limit (`131056`), content (`131051`), undeliverable (`131026`), timeouts and 5xx are returned as-is: another address could not help or could deliver twice. When every address is rejected, Meta's last error is returned, as before.
5. **Authentication Templates go to phones only.** Meta: every message type works with BSUIDs "except for one-tap, zero-tap, and copy code authentication templates, which require user phone numbers". The adapter drops BSUIDs for them; with no phone known it fails locally with `BSUID_RECIPIENT_NOT_SUPPORTED`. Template routing policy and conservative outcomes (ADR-0006) are unchanged.
6. **Results show what happened.** `MessageResult.attempted_recipients` lists every address tried, in order, when the adapter fell back.
7. **Events are attributed to the destination.** The `bot_reply` Pub/Sub notification is keyed by the webhook User only when the target contains that User's address; a send to anyone else is keyed by the destination.

## Consequences

- Breaking: every `DirectMessage(..., recipient_id=x)` becomes `DirectMessage(..., addresses=DeliveryAddresses.of(x))`; replies inside webhooks should use `webhook.user.delivery_addresses()` to get the fallback. `DirectMessage.recipient_id` and `.address` remain read-only (first address). Shipped examples, routes and tests migrate in the same change; Symphonai migrates in Gate C.
- The fallback is a WhatsApp adapter rule. A future Platform with several addresses per User implements its own order behind the same target.
- The WhatsApp carousel now routes BSUIDs through `recipient` like every other send (it always used `to`).
- Unconfirmed in Meta's docs and recorded as live evidence only: the `131030` code (absent from Meta's current error list) and whether test-number allow-lists accept BSUIDs. Other address-rejection codes are added only after they are observed live.
