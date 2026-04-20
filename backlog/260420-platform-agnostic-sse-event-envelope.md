# Platform-Agnostic SSE Event Envelope & Context

## Context

The v0.3.6 SSE refactor landed a request-scoped `SSEEventContext` that every
publisher reads at emission time. It solves the identity-null bug that
shipped in v0.3.4/0.3.5 and removes all per-construction identity
plumbing. Good — but on the same pass it baked *WhatsApp's* identity model
into the envelope and the context, the same way `UserBase` did for
webhooks (see `260420-platform-agnostic-incoming-webhook-abstraction.md`).

Concretely, the SSE envelope produced by `SSEEventHub._build_event`
(`wappa/core/sse/event_hub.py:141-162`) hard-codes:

```json
{
  "tenant_id":    "...",
  "user_id":      "...",   // canonical, platform-agnostic — fine
  "bsuid":        "...",   // WhatsApp Business-Scoped User ID
  "phone_number": "...",   // WhatsApp wa_id / SMS phone
  "platform":     "whatsapp",
  ...
}
```

And the context that feeds it (`SSEEventContext`,
`wappa/core/sse/context.py:38-55`) declares the same two fields as
first-class slots. Apps are expected to hydrate them via
`wappa.sse.update_identity(bsuid=..., phone_number=...)`.

This is the exact same architectural mistake as the old `UserBase`:
two *universal*-named fields (`bsuid`, `phone_number`) that only
mean something for one platform. Telegram has `telegram_user_id` +
`username` + `chat_id`. Instagram has `igsid` + `ig_business_account_id`.
iMessage has an opaque handle. None of them have a BSUID; most don't
have a phone number. Subscribers (frontends) that want to correlate
by platform-native identity have no typed slot to read from — they'd
have to fish in `metadata`.

The helpers that populate these fields are equally opinionated:

- `classify_meta_identifier(value)` (`wappa/core/sse/context.py:88-103`)
  matches against Meta's BSUID regex (`^[A-Z]{2}\.[A-Za-z0-9]{1,128}$`).
  A Telegram ID (`"123456789"`) gets classified as `phone_number`
  because it's digits; a Telegram `@username` gets classified as a
  phone fallback because it doesn't match the BSUID regex. Neither is
  correct.
- `derive_identifiers(user_obj)` (`wappa/core/sse/context.py:106-117`)
  reads `.bsuid` and `.phone_number` attrs. That shape only exists on
  `UserBase` in its current WhatsApp-shaped form. For Telegram,
  Instagram, iMessage there is nothing to read.
- All three framework entry points
  (`WebhookController._derive_sse_identity`,
  `APIEventDispatcher.dispatch`, `ExpiryDispatcher._run_with_sse_scope`)
  call those helpers directly to populate the scope. Any non-WhatsApp
  processor will emit envelopes with `bsuid=null` and `phone_number=null`
  for every event — functionally identical to the v0.3.4 bug we just
  fixed, except now it's by design.

If we ship the second-platform adapter (Telegram/Instagram/iMessage)
without revisiting this, every SSE subscriber will need per-platform
special-casing to pull identity out of `metadata`, and the "universal"
SSE envelope will be universal in name only. This parallels the
webhook-interface bug — same instinct to add platform-specific fields
to a shared shape, same downstream cost.

## Scope

- Redefine `SSEEventContext` so the identity portion is a platform
  discriminator plus an opaque typed namespace per platform, mirroring
  the approach proposed for `IncomingMessageWebhook` in the sibling
  backlog. The only truly universal identity field on the envelope
  stays `user_id` (canonical, stable, platform-resolved).
- Redefine the SSE envelope produced by `_build_event` to reflect the
  same shape. Subscribers should be able to switch on `platform` and
  read a typed platform block, not a WhatsApp-flavored union.
- Move `classify_meta_identifier` and the Meta-specific BSUID regex
  (`_BSUID_PATTERN`) out of the shared SSE module. The shared module
  should not know what Meta is. Each platform processor owns its own
  identifier-shape classifier.
- Redefine `derive_identifiers(user_obj)` as a platform-aware API —
  either a method on the platform-specific user payload, or a
  dispatch-on-platform free function. Either way, it should not read
  generic `.bsuid` / `.phone_number` attrs off an unknown object.
- Adjust the three framework entry points so they populate the SSE
  scope from whatever *typed* per-platform identity source the webhook
  / event / expiry key gives them, without reaching through a
  WhatsApp-shaped intermediate.
- Update the public `wappa.sse` module (`wappa/sse.py`) so
  `update_identity(...)` either takes a typed per-platform payload or
  is replaced with something like `update_platform_identity(**fields)`
  that writes into the active platform namespace. Same deprecation
  treatment as the webhook redesign.
- Document the SSE envelope contract in `wappa/core/sse/README.md` (to
  be written) so future platform adapters know exactly which fields
  are universal and which belong in their namespace.

## Out of Scope

- Subscriber-side contracts (Meta-React hooks, wappa_miia frontend
  `sseConnection.ts`). Those will follow the new envelope shape
  automatically once it ships; their migration is an app concern.
- The `metadata` bag — that's genuinely app-level and stays exactly
  as it is today (a free-form dict apps enrich via
  `wappa.sse.update_metadata`).
- The `SSEEventHub.subscribe` filters (`tenant_id`, `user_id`,
  `event_types`). They stay as-is — both are universal by construction.
- Outgoing-messenger routing (`SSEMessengerWrapper.send_*`). It already
  reads everything from context; no changes needed beyond whatever the
  context shape becomes.
- The deferred-`incoming_message` flush mechanism
  (`SSEMessageHandler.log_incoming_message` → `post_process_message`).
  The flush pipeline is platform-agnostic; only the identity it picks
  up from context is opinionated, and that gets fixed by fixing the
  context.

## Implementation Notes

Proposed shape for the envelope (subject to the open questions below):

```json
{
  "event_id":     "...",
  "event_type":   "incoming_message",
  "timestamp":    "...",
  "tenant_id":    "...",
  "user_id":      "...",            // canonical, platform-resolved
  "platform":     "whatsapp",       // discriminator

  // Typed platform namespace — exactly one is populated.
  "whatsapp":   { "bsuid": "...", "phone_number": "...", "wa_id": "...", "username": null, "country_code": "US" },
  "telegram":   null,
  "instagram":  null,
  "imessage":   null,

  "source":   "webhook",
  "payload":  { ... },
  "metadata": { ... }
}
```

Proposed shape for the context:

```python
@dataclass
class SSEEventContext:
    tenant_id: str = "unknown"
    user_id: str = "unknown"
    platform: str = "whatsapp"

    # Exactly one is populated, matching `platform`.
    whatsapp:  WhatsAppSSEIdentity | None = None
    telegram:  TelegramSSEIdentity | None = None
    instagram: InstagramSSEIdentity | None = None
    imessage:  IMessageSSEIdentity | None = None

    metadata: dict[str, Any] = field(default_factory=dict)
    _pending_incoming: dict[str, Any] | None = None


class WhatsAppSSEIdentity(BaseModel):
    bsuid: str | None = None
    phone_number: str | None = None   # == wa_id
    username: str | None = None
    country_code: str | None = None


class TelegramSSEIdentity(BaseModel):
    telegram_user_id: int
    username: str | None = None
    chat_id: int | None = None
```

Per-platform identifier classifiers move to each platform processor:

- `wappa.webhooks.whatsapp.identity.classify_whatsapp_identifier(value) -> WhatsAppSSEIdentity`
  owns the BSUID regex.
- `wappa.webhooks.telegram.identity.classify_telegram_identifier(value) -> TelegramSSEIdentity`
  owns Telegram ID parsing.
- The shared SSE module stops knowing what Meta is.

Populating the scope at each entry point:

```python
# WebhookController
identity = platform_processor.derive_sse_identity(webhook)
async with sse_event_scope(
    tenant_id=..., user_id=..., platform=..., identity=identity
):
    ...

# APIEventDispatcher
identity = platform_processor.derive_sse_identity_from_event(event)
async with sse_event_scope(...):
    ...

# ExpiryDispatcher
identity = platform_processor.derive_sse_identity_from_key(event.identifier)
async with sse_event_scope(...):
    ...
```

The public `wappa.sse.update_identity` becomes platform-aware:

```python
# Today (v0.3.6):
update_identity(bsuid="US.canon", phone_number="15551234567")

# Proposed:
update_whatsapp_identity(bsuid="US.canon", phone_number="15551234567")
# or equivalently, a generic:
update_identity(WhatsAppSSEIdentity(bsuid="US.canon", phone_number="15551234567"))
```

Migration strategy (aligns with the sibling webhook-abstraction ticket):

- Keep `bsuid` and `phone_number` on the SSE envelope as deprecated
  top-level aliases that read from `whatsapp.bsuid` /
  `whatsapp.phone_number`, for one minor version.
- Keep `wappa.sse.update_identity(bsuid=..., phone_number=...)` with
  the same delegation, one minor version.
- Ship the new typed identity slots behind the same opt-in flag as
  the webhook contract (`Wappa(strict_universal=True)`), target
  0.4.0 opt-in → 0.5.0 default → 0.6.0 removed.
- Ship both redesigns in the same release train — subscribers and
  app code are written against both surfaces at once, and the
  per-platform classifier lives in one place (the platform processor)
  instead of two.

## Open Questions

- **Flat-discriminator vs. typed union on the envelope?** Current
  `whatsapp: X | None, telegram: Y | None, ...` pattern matches the
  sibling backlog's proposal for `IncomingMessageWebhook`, and keeps
  subscriber JSON simple. A discriminated union (`identity: { kind:
  "whatsapp", bsuid: ..., phone_number: ... }`) is better-typed but
  harder to consume in a JS frontend.
- **Does `user_id` stay as a top-level canonical field, or collapse
  into the platform namespace?** Leaning toward keeping it top-level
  because it's the subscribe-filter key (`SSEEventHub._matches` uses
  `subscriber.user_id != tenant_id`) and must remain a single string
  regardless of platform. But the *resolution rule* becomes
  per-platform, owned by the processor.
- **Should the SSE module depend on the webhook module (for the
  per-platform identity types), or should the identity types live in
  a shared `wappa.identity` package that both depend on?** The latter
  avoids a circular-feeling coupling but introduces a third
  abstraction layer. The former is simpler if we're OK with SSE being
  logically downstream of webhooks.
- **What about `APIMessageEvent` identity?** Today
  `publish_api_sse_event` calls `classify_meta_identifier` on
  `event.recipient` and `event.user_id`
  (`wappa/core/sse/handlers.py:110-116`). Same opinion leak — needs
  the same treatment via the platform processor.
- **Expiry dispatcher doesn't know the platform.** The key format is
  `{tenant}:EXPTRIGGER:{action}:{identifier}` (parser.py:121-136). It
  has no platform discriminator. Either we add one to the key format,
  or expiry handlers accept a degraded SSE scope (`platform` set to
  `"unknown"`, identity namespace empty) and the app fills in the
  platform-specific identity via `update_*_identity(...)` once they
  load cache state. The latter is less invasive but means
  `outgoing_bot_message` events emitted from expiry start with no
  platform identity in the envelope.
- **`SSESubscription` filters**: subscribers filter by `tenant_id` and
  `user_id`. Should they be able to filter by platform too? Today they
  can't, and subscribers that only care about WhatsApp events in a
  mixed-platform deployment would have to post-filter client-side.

## Exit Criteria

- [ ] `SSEEventContext` contains no WhatsApp-specific identity fields
      at the top level; identity lives in platform-specific
      namespaces.
- [ ] `SSEEventHub._build_event` produces an envelope with a
      discriminator (`platform`) and exactly one populated
      per-platform identity block.
- [ ] At least one non-WhatsApp platform identity block (real or stub,
      e.g. `TelegramSSEIdentity`) is defined and exercised by a test
      in `tests/test_sse_context_flow.py`.
- [ ] `classify_meta_identifier` and `_BSUID_PATTERN` are gone from
      `wappa/core/sse/context.py`. Per-platform classifiers live in
      their respective processor packages.
- [ ] `derive_identifiers` is either gone or re-typed as
      platform-specific.
- [ ] `wappa.sse.update_identity(...)` is either platform-discriminated
      or split into per-platform helpers, with a deprecation shim for
      the 0.3.6 signature.
- [ ] `wappa/core/sse/README.md` documents the envelope contract,
      which fields are universal, and how new platforms plug in their
      identity namespace.
- [ ] Existing v0.3.6 SSE tests (`tests/test_sse_context_flow.py`,
      all 8 cases) pass unchanged when running against the deprecation
      shim.
- [ ] Ships in the same release as the sibling
      `platform-agnostic-incoming-webhook-abstraction` ticket, or at
      least is blocked on it so the two redesigns don't diverge.

## Depends On / Relates To

- `backlog/260420-platform-agnostic-incoming-webhook-abstraction.md`
  — the webhook-interface redesign. This SSE ticket should ship in
  the same release train so subscribers see both surfaces change at
  once and per-platform identity logic lives in one place.
- `CHANGELOG.md` v0.3.6 — this backlog exists because that release
  encoded the WhatsApp-opinionated shape into the contract and needs
  to be undone before the second platform ships.
