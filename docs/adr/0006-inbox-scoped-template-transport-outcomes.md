# ADR-0006: Inbox-scoped Template Transport and Conservative Outcomes

**Status:** Accepted  
**Date:** 2026-08-03  
**Extends:** ADR-0003, ADR-0004

## Context

Host Applications need Template transport without constructing Wappa's
credential, HTTP session, WhatsApp client, handler, Messenger, and middleware
pipeline implementation classes. The general `IMessenger` result also cannot
express the safety distinction between a proven rejection and a call whose
platform outcome is unknown.

Putting Host Application attribution, governance, idempotency, Conversation
lifecycle, or Reply State into Wappa would reverse the dependency. Treating
every exception as a definite failure would make unsafe automatic retries
possible after an irreversible platform call.

## Decision

Expose `OutboundRuntime` as a deep public factory and
`InboxTemplateTransport` as its Inbox-scoped Template capability. Wappa owns
credential resolution, active session acquisition, Messenger construction,
Messenger Pipeline composition, WhatsApp endpoint and payload rules, and safe
transport normalization.

The request is platform-facing and rejects unknown fields. It carries exactly
one typed Delivery Address: phone number or BSUID. Wappa serializes phone
numbers as Meta `to` and regular or parent BSUIDs as Meta `recipient`.
Usernames are response/webhook evidence, never outbound addresses. The request
contains no Host Application attribution, policy, state, or persistence
concepts.

Marketing Templates use `/marketing_messages` by category default. Utility and
authentication Templates use `/messages`. A named
`cloud_messages_fallback` policy may select `/messages` for marketing before
provider I/O; no rejection or ambiguous response triggers a cross-endpoint
retry. Authentication Templates reject BSUID Delivery Addresses.

The result has four outcomes:

1. `accepted`: platform acceptance plus a platform Message ID are proven.
2. `rejected`: Wappa has evidence that the call was not accepted.
3. `transport_unavailable`: no platform call could be started, including drain.
4. `indeterminate`: acceptance or rejection cannot be proven.

A success response without a platform Message ID is `indeterminate` because it
cannot support deterministic local commit and webhook correlation. Acceptance
never means delivered, read, replied, or committed by the Host Application.

Wappa's standalone Template HTTP routes adapt to this same capability and are
excluded unless a host explicitly enables them.

## Consequences

- Host Applications depend on shallow Wappa imports and cannot acquire internal
  transport components through this seam.
- Transport execution stays separate from Host Application durable settlement
  and lifecycle commit.
- An `indeterminate` result is never safe for automatic resend.
- Results identify the requested address, selected endpoint, routing reason,
  and returned phone, BSUID, parent-BSUID, or username evidence when present.
- Wappa can evolve client, handler, and pipeline composition without changing
  the Host Application contract.
- Template HTTP mutation is an explicit standalone capability, not an ambient
  route inherited by every embedding host.

## Alternatives Considered

1. **Keep Host Applications constructing `WhatsAppClient` and handlers.**
   Rejected because internal composition becomes an accidental public contract.
2. **Put governance and lifecycle fields in the Wappa request.** Rejected
   because Wappa does not own Host Application business policy.
3. **Return `success: bool` for every outcome.** Rejected because it collapses
   ambiguity into a retryable failure.
4. **Mount Template routes by default.** Rejected because an embedding host
   would expose an unintended mutation bypass.
