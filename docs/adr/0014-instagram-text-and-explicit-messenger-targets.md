# ADR-0014: Instagram text through the existing Inbox-bound Messenger

## Status

Accepted (2026-11-03), from the Instagram integration design session.

## Context

The second real Platform exposes WhatsApp assumptions in sender identity,
credential records, message results, callback routing, and mandatory outbound
methods. Instagram's first deliverable is a text echo consumer, followed by
self-service account connection and Symphonai agent integration. The session
selected a clean target contract and separate Platform callbacks.

## Decision

- Keep `/webhook/inboxes/{platform}`: Instagram has its own callback; do not
  combine it with Messenger or WhatsApp under a new Platform identity.
- Use the existing explicit Inbox Directory authority for Instagram, with
  active/inactive encrypted record variants. The professional account is both
  Platform Account and Inbox; their native IDs match. There is no settings
  fallback, fabricated WABA, or registration from inbound messages.
- Implement the initial Instagram transport for Unified Login credentials and
  application-configured Graph API settings, defaulting to graph.facebook.com.
- Replace bare recipients on recipient-based IMessenger sends with immutable,
  Inbox-qualified DirectMessage targets. No string-or-target overload or old
  recipient keyword is accepted. WhatsApp HTTP adapters and independent
  Template transport map their native recipient contracts into these targets.
- Keep the public Messenger facade. Only identity/text are mandatory for the
  first adapter; optional methods raise UnsupportedOperationError. Expose
  supported_operations to distinguish adapter support from provider features.
- Native Instagram IDs remain separate from WA phone/BSUID evidence. Seen
  events retain their native message reference; API acceptance is not delivery.
  Business echoes and unimplemented messaging events use distinct system
  subtypes and never enter the incoming-text lane.

## Trade-off and consequences

A smaller family of public outbound interfaces would segregate dependencies,
but would expand assembly and host migration before the text slice establishes
which capability boundaries are useful. Keeping every operation abstract would
force the first adapter to copy unsupported stubs. Explicit optional-operation
defaults and capability discovery keep the facade usable without pretending
that Instagram implements WhatsApp's methods. The split threshold in
`docs/tech-requests/006-defer-messenger-split.md` remains relevant as subsequent
message families are implemented.

The target change intentionally breaks host callers and middleware request
payloads; shipped callers and tests migrate in the same change. The independent
Template transport and WhatsApp REST addressing contracts remain explicit
adapter inputs, not compatibility overloads on IMessenger. PrivateReply and
comment operations are deferred until the comment phase.

The historical MessageResult module still houses shared results; native
Instagram response evidence is separate from the WA response field. Neutral
module ownership is tracked as follow-up, not claimed complete here.

Live Meta receipt requires configured credentials, subscriptions, and account
access. Offline tests and a successful GET challenge do not establish a real
Instagram text exchange or completion of the onboarding milestone.
