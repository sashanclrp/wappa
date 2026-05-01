# Platform-Agnostic Webhook Field Handler Registry

## Context

v0.5.x ships a typed registry that lets apps handle Meta webhook field values
the framework does not understand natively (`message_template_status_update`,
`account_update`, `phone_number_quality_update`, etc.). The registry was
designed for WhatsApp Business Platform webhooks and bakes that assumption
into several seams:

- `WappaBuilder.register_webhook_field(field_name, parser, handler)` takes a
  bare string `field_name` — no platform discriminator. Two platforms cannot
  register the same logical field name (e.g. both WhatsApp and Instagram
  surface `account_alerts` in their own shapes) without colliding.
- `FieldHandlerRegistry` is a flat `dict[str, FieldHandler]`. There is one
  registry per `Wappa` app, attached to the `WhatsAppWebhookProcessor`
  singleton in `Wappa._build_asgi_sync` (`wappa/core/wappa_app.py:213`).
  When a Telegram / Instagram processor lands, it has no clean way to opt
  into the same registry.
- `WhatsAppWebhookProcessor.set_field_registry()` and the registry-aware
  `model_validator` in `wappa/webhooks/whatsapp/webhook_container.py:159`
  are WhatsApp-shaped: they assume Meta's `entry[].changes[].field` envelope
  and a Pydantic context channel. Telegram's update model is flat
  (`update_id` + `message`/`callback_query`/...); Instagram piggybacks on
  Meta's webhook envelope but uses a different field vocabulary
  (`comments`, `mentions`, `messaging_postbacks`).
- `BUILTIN_WEBHOOK_FIELDS` lives in `wappa/core/events/field_registry.py`
  as a frozen set of WhatsApp field names. Each platform will have its own
  built-in set, and the registry currently has no concept of "which
  platform's built-ins do I gate against?".
- `CustomWebhook` carries `platform: PlatformType` correctly, but the
  parser and handler the registry stores have no notion of which platform
  they apply to. An app could register a parser intended for WhatsApp's
  `account_update` payload and unintentionally have it run against an
  Instagram payload of the same name.

If we keep this WhatsApp-centric shape and bolt platform handling on later,
the registry collapses into "WhatsApp + a junk drawer" the same way
`IncomingMessageWebhook` did before the universal-interface refactor (see
`backlog/260420-platform-agnostic-incoming-webhook-abstraction.md`). The
moment the second platform processor lands is the right moment to redesign
this — earlier is premature, later is a breaking change.

## Scope

Redesign the registry around a `(platform, field_name)` key so each adapter
declares its own built-ins and accepts its own custom registrations, while
keeping the single-app-level entrypoint that builders and `Wappa` expose
today.

In scope:

- `FieldHandlerRegistry` keyed by `(PlatformType, str)`, with platform-aware
  built-in sets and per-platform `fields()` queries.
- Builder API: `WappaBuilder.register_webhook_field(field_name, *, platform,
  parser, handler)` — `platform` defaults to `PlatformType.WHATSAPP` for
  back-compat while only WhatsApp ships, becomes required when a second
  adapter is added.
- An `IWebhookFieldHandler` (or similar) protocol that each platform's
  processor implements: it owns its built-in field set, its registry-aware
  parsing path, and its `_create_custom_webhook` translation. The current
  `WhatsAppWebhookProcessor.set_field_registry` shrinks to
  `set_field_registry(registry: FieldHandlerRegistry)` on a base class.
- A platform-agnostic way to thread the registry into Pydantic validation.
  Today we use `model_validate(payload, context={"field_registry": ...})`.
  Telegram doesn't need Pydantic context at all (its envelope has no `field`
  discriminator); Instagram does. The base contract should not assume
  Pydantic context.
- Update `BUILTIN_WEBHOOK_FIELDS` to be a per-platform attribute on each
  processor rather than a global frozen set.
- Documentation in `wappa/__init__.py` and the README explaining the
  platform-aware registration model.

Out of scope:

- Implementing the actual Telegram or Instagram processors. This ticket is
  purely about reshaping the registry so they can plug in without breaking
  WhatsApp consumers.
- Changing `CustomWebhook` itself — it already carries `platform` and is
  reusable as-is.
- Per-tenant registries. Today the registry is app-scoped (one set of
  handlers serves every tenant). Multi-tenant overrides are a separate
  question and explicitly deferred.

## Migration Path

1. Introduce the new `(platform, field_name)` key shape. Existing call sites
   without a platform default to `PlatformType.WHATSAPP`. No behavior change
   for current apps.
2. Move `BUILTIN_WEBHOOK_FIELDS` onto `WhatsAppWebhookProcessor` as a class
   attribute. Drop the import from `wappa.webhooks.whatsapp.webhook_container`
   and have the validator pull built-ins from the processor via context.
3. When the first non-WhatsApp processor lands (Telegram is the most likely
   candidate), make `platform` a required keyword on
   `register_webhook_field`. Bump the minor version, document the break.
4. Add a `platform` predicate test to the registry: a handler registered for
   `PlatformType.INSTAGRAM` must not run for a WhatsApp `CustomWebhook` even
   if the `field_name` matches.

## Open Questions

- Should the same callable be registerable for multiple platforms via a
  single call (e.g. `platforms=[WHATSAPP, INSTAGRAM]`) when the payload
  shape is genuinely shared (Meta's `account_update` is similar across
  WABA and IG accounts)? Probably yes, but ship the strict per-platform
  form first and add the convenience overload later.
- Where do platform-specific built-in sets live? Two viable options:
  (a) class attribute on each `*WebhookProcessor`; (b) a small
  `platform_metadata.py` module that maps `PlatformType → frozenset[str]`.
  (a) keeps the data next to the code that owns it; (b) is friendlier for
  introspection. Lean toward (a).

## Related

- `backlog/260420-platform-agnostic-incoming-webhook-abstraction.md` — same
  shape of refactor, applied to `UserBase`/`TenantBase`/`IncomingMessageWebhook`.
  These two should land in the same release window so the platform-agnostic
  story is coherent.
- `backlog/260420-platform-agnostic-sse-event-envelope.md` — adjacent
  generalization on the outbound side.
