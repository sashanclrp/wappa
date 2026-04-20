# Platform-Agnostic `IncomingMessageWebhook` Abstraction

## Context

Today the "universal" webhook layer in `wappa/webhooks/core/webhook_interfaces/`
is only universal in name. `IncomingMessageWebhook` and `UserBase` are still
opinionated toward WhatsApp's identity model:

- `UserBase` carries `phone_number`, `bsuid`, `username`, `country_code`,
  `identity_key_hash` — all fields borrowed directly from WhatsApp's
  `contacts[]` entry. `user.user_id` is a hardcoded resolution between
  `phone_number` and `bsuid` (see v0.3.2 change, `base_components.py:87-104`).
- `IncomingMessageWebhook.whatsapp` is a WhatsApp-only namespace
  (`WhatsAppIncomingWebhookData` with `wa_id`, `bsuid`, `username`,
  `country_code`). There is no symmetric namespace for other platforms.
- `TenantBase` exposes `business_phone_number_id` and `display_phone_number`
  at the top level, which have no meaning for Telegram bots, Instagram
  business accounts, or iMessage Business Chat agents.
- `PlatformType` enum exists (`wappa/schemas/core/types.py`) but is only
  switched on inside the WhatsApp processor; no other platform processor
  exists yet.

When Telegram / Instagram / iMessage adapters land they will need:
- Different user identifiers (Telegram `user_id` int + optional `username`;
  Instagram `igsid`; iMessage opaque handle).
- Different tenant identifiers (Telegram `bot_id` + `chat_id`;
  Instagram `ig_business_account_id`; iMessage `business_id`).
- Different transport semantics (Telegram has chats/groups — not 1:1 phone
  numbers; Instagram DMs are scoped to an IG business account; iMessage has
  no phone number at all).

If we keep piling platform-specific fields onto `UserBase`/`TenantBase`, the
"universal" contract collapses into "WhatsApp + a junk drawer". We need to
decide the boundary between *truly universal* fields and *per-platform*
extensions before we write the second adapter, because that is the moment
the design will be audited by real integration code rather than by intent.

## Scope

- Redefine `UserBase` and `TenantBase` to contain only platform-agnostic
  concepts: a stable identifier, a display name, a platform discriminator,
  and an opaque reference back to the raw per-platform payload.
- Introduce a per-platform extension slot on `IncomingMessageWebhook`,
  mirroring the existing `whatsapp: WhatsAppIncomingWebhookData | None`
  pattern, so each platform ships its native identity model in its own
  typed namespace (`telegram`, `instagram`, `imessage`, ...) instead of
  polluting the common base.
- Define a single canonical `user_id` resolution rule per platform, owned
  by the platform's processor, not by the universal `UserBase` property.
  Application code should be able to call `webhook.user.user_id` and get
  "the right identifier for this platform" without knowing which platform
  it is.
- Formalize the same treatment for `StatusWebhook.recipient_id` and
  `SystemWebhook.event_detail` — right now both have WhatsApp-shaped
  fields leaking through (BSUID, wa_id, parent_user_id).
- Document platform extension guidelines in `wappa/webhooks/core/README.md`
  (to be written as part of this work) so future adapters know exactly
  which fields are universal vs. which belong in their platform namespace.

## Out of Scope

- Writing the actual Telegram / Instagram / iMessage processors. This
  backlog is about the *contract*, not the adapters.
- Changing the public `messenger.send_*` API. Recipient resolution for
  outbound messages already lives behind `wappa.schemas.core.recipient`
  (see v0.3.0 changelog entry) and is orthogonal.
- Touching the WhatsApp webhook models themselves
  (`wappa/webhooks/whatsapp/**`). Those stay as-is; only the universal
  interface in `webhooks/core/webhook_interfaces/` is being refactored.
- Persistence-layer keying (`persistence/memory/handlers/*.py` use
  `user_id` as a string). This should continue to work transparently as
  long as `user.user_id` still returns a stable per-platform string.

## Implementation Notes

Proposed shape (subject to the open questions below):

```python
class UserBase(BaseModel):
    """Platform-agnostic user identity. Platform-specific identifiers
    live in IncomingMessageWebhook.<platform>."""

    platform_user_id: str        # the canonical stable ID for this platform
    platform: PlatformType       # discriminator
    display_name: str | None     # best-effort human-readable name
    # no phone_number, no bsuid, no username here


class TenantBase(BaseModel):
    platform_tenant_id: str      # stable business/tenant ID for this platform
    platform: PlatformType
    display_name: str | None     # what the business calls itself on this platform


class IncomingMessageWebhook(BaseModel):
    tenant: TenantBase
    user: UserBase
    message: BaseMessage
    platform: PlatformType

    # Platform-specific typed namespaces — exactly one is populated.
    whatsapp: WhatsAppIncomingWebhookData | None = None
    telegram: TelegramIncomingWebhookData | None = None
    instagram: InstagramIncomingWebhookData | None = None
    imessage: IMessageIncomingWebhookData | None = None
```

Per-platform `*IncomingWebhookData` models own the fields that today
live on `UserBase` / `TenantBase`:
- `WhatsAppIncomingWebhookData` → `wa_id`, `bsuid`, `username`,
  `country_code`, `identity_key_hash`, `display_phone_number`,
  `business_phone_number_id`.
- `TelegramIncomingWebhookData` → `telegram_user_id`, `username`,
  `chat_id`, `chat_type`, `bot_id`, `language_code`.
- etc.

Processors are responsible for:
1. Populating their platform-specific namespace with the raw identity.
2. Computing `UserBase.platform_user_id` from that namespace using a
   single documented rule per platform (e.g. WhatsApp: `wa_id` preferred,
   `bsuid` fallback — the v0.3.2 behavior).
3. Setting `TenantBase.platform_tenant_id` the same way.

Migration strategy:
- Keep the WhatsApp-shaped fields on `UserBase`/`TenantBase` as
  `@property` shims that read from `self.whatsapp` for one minor
  version, marked deprecated, so existing bots don't break on upgrade.
- Ship the new contract behind an opt-in flag (`Wappa(strict_universal=True)`)
  for one minor, then flip the default, then remove the shims in the next
  minor after that. Target: 0.4.0 opt-in → 0.5.0 default → 0.6.0 removed.

## Open Questions

- **One model with optional per-platform slots, or a Pydantic discriminated
  union?** The current `whatsapp: X | None` pattern is ergonomic (you can
  always dot-access `webhook.whatsapp?.bsuid`), but it allows invalid
  states like `platform=TELEGRAM` with `whatsapp` populated. A discriminated
  union is safer but more verbose for user code.
- **Should `PlatformType` carry the platform data on the *webhook* or on
  `UserBase`/`TenantBase`?** Today both carry it redundantly. Probably
  just the webhook level, since user+tenant always travel together with a
  webhook.
- **Does iMessage Business Chat actually fit this model?** Need to verify
  their webhook payload structure before committing to the universal
  shape — iMessage is the most likely outlier.
- **What happens to `recipient_phone_id` / `recipient_bsuid` on
  `StatusWebhook`?** Same treatment (collapse into `recipient_id` +
  per-platform namespace), or is status so tightly coupled to per-platform
  delivery semantics that it should just be a union of per-platform
  status webhooks?
- **Back-compat for the SSE / pubsub layer**: `core/sse/handlers.py` and
  `core/pubsub/handlers.py` read `webhook.user.user_id` directly. As long
  as the property stays, they are fine — but worth confirming no one is
  reaching into `webhook.user.phone_number` as a "trust me it's there"
  identity hack.

## Exit Criteria

- [ ] `UserBase` and `TenantBase` contain no WhatsApp-specific fields.
- [ ] At least one non-WhatsApp platform namespace (real or stub, e.g.
      `TelegramIncomingWebhookData`) is defined and exercised by a test,
      to prove the extension point works.
- [ ] `webhook.user.user_id` returns the correct stable identifier for
      the active platform, with the resolution rule documented per
      platform in `webhooks/core/README.md`.
- [ ] Existing WhatsApp integration tests in `tests/` pass unchanged —
      meaning application-level reads of `webhook.user.user_id`,
      `webhook.message.*`, and `webhook.whatsapp.*` still work.
- [ ] Deprecation shims (or the opt-in flag) cover the removed fields so
      0.3.x bots upgrade to 0.4.0 without code changes.
- [ ] CHANGELOG entry explains the new contract and the migration path.
