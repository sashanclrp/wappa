# Webhooks Context — Architecture

## Responsibilities

- Parse and validate raw HTTP payloads from messaging platforms into typed Pydantic models.
- Produce `UniversalWebhook` instances (`InboundMessageWebhook`, `CallWebhook`,
  `StatusWebhook`, `ErrorWebhook`, `SystemWebhook`, `CustomWebhook`, the shared `MessageUpdateWebhook`, `OutboundEchoWebhook`, `HistorySyncWebhook`, `InboxConnectionWebhook`, and the Instagram-only `IncomingCommentWebhook`, `MentionWebhook`) for downstream dispatch.
- Validate provider schemas after the API boundary has split a batch and derived
  its Inbox from the payload.
- Own every inbound webhook Pydantic schema, including platform payload schemas
  and Universal Model forms.
- Gate unknown Meta `change.field` values against a runtime registry; a field that is neither built in nor registered becomes `SystemWebhook(UNSUPPORTED_EVENT)` (HTTP 200), never a 400.
- Tolerate and report Meta schema drift: models that parse Meta input use `extra="allow"`, and `wappa/webhooks/core/schema_drift.py` (`report_schema_drift`) logs `META_SCHEMA_DRIFT platform=<p> field=<Model.field>` once per field per process, never the value. `WAPPA_STRICT_META_SCHEMA=1` raises `MetaSchemaDriftError` instead (set by Wappa's tests).
- Expose platform-agnostic inspection (`is_incoming_message`, `is_status_update`, etc.)
  through the `BaseWebhook` interface.
- Supply each Platform's inbound adapter: the `PlatformWebhooks` protocol (`wappa/core/inbound/platform_webhooks.py`) with `platform`, `builtin_fields`, `route` (may do credential I/O) and `translate` (pure), implemented by `WhatsAppWebhookProcessor` and `InstagramWebhookProcessor` and installed through `wappa/platforms/` (`PLATFORMS`).

## Explicit Boundaries — What This Context Does NOT Own

- Dispatching `UniversalWebhook` events to handlers (owned by the Inbound Runtime
  and `wappa/core/events/`).
- Sending outbound messages (owned by `wappa/messaging/`).
- Cache scoping, session state, or persistence (owned by `wappa/persistence/`).
- HTTP route handling (owned by `wappa/api/`).
- Runtime orchestration, ContextVars, Messenger construction, Cache Factory construction,
  DB session injection, SSE scope, and handler cloning (owned by the Inbound Runtime).
- Shared enums and outbound recipient normalization. `PlatformType`,
  `MessageType`, `WebhookType`, and related enum helpers live in
  `wappa/schemas/core/types.py`; recipient normalization lives in
  `wappa/schemas/core/recipient.py`.

## Module Structure

```
wappa/webhooks/
├── __init__.py                   # Public re-exports (universal webhooks, message types)
├── core/                         # Neutral inbound contract: no Platform knowledge
│   ├── base_webhook.py           # BaseWebhook ABC
│   ├── base_message/             # BaseMessage, one module per family (core, text, interactive, media, contact_location, reaction)
│   ├── base_status.py            # BaseMessageStatus
│   ├── schema_drift.py           # Tolerant-reader drift reporting
│   └── webhook_interfaces/
│       ├── base_components/      # identity, context, errors, system_event_detail
│       ├── universal_webhooks/   # inbound, call, status, error, system, custom, union
│       └── conversation_webhooks.py  # Comments, mentions, echoes, history, connection
├── instagram/                    # The per-Platform scaffold (wappa-develop: references/scaffolding.md)
│   ├── __init__.py               # Public facade
│   ├── fields.py                 # Built-in fields, messaging keys, change fields
│   ├── routing.py                # route_instagram_payload: resolves every entry's Inbox
│   ├── models/                   # Pure wire models: common, messaging, comments, webhook
│   ├── message_types/            # BaseMessage subclasses: _base, _attachment, context, one module per type, registry
│   └── processor/                # InstagramWebhookProcessor: adapter, _base, context, one lane per module (messages, echo, changes, comments, mentions)
└── whatsapp/                     # The same scaffold
    ├── __init__.py               # Public facade
    ├── fields.py                 # BUILTIN_WEBHOOK_FIELDS and the event-field sets
    ├── routing.py                # route_whatsapp_payload: resolves every entry's Inbox
    ├── models/                   # Pure wire models: base, status + status_reports, calls, coexistence, system, values, change, entry, metadata, contact_adapter, webhook
    ├── message_types/            # BaseMessage subclasses: _base (WhatsAppMessageBase), context, one module per type
    └── processor/                # WhatsAppWebhookProcessor: adapter, _base, message_factory, messages, message_updates, history, calls, statuses, errors, custom, context
        └── system/               # System lane by family: dispatch, parts, preferences, identity, number_changes, user_actions, groups, account_events
```

## Key Classes and Roles

| Class | Role |
|---|---|
| `BaseWebhook` | ABC the WhatsApp container (`WhatsAppWebhook`) implements: `platform`, `webhook_type`, `source_id` (= `inbox_id`), and the inspection/extraction interface its processor reads. Not a Platform requirement: `InstagramWebhook` is a plain envelope model. |
| `WhatsAppWebhook` | Concrete `BaseWebhook` for Meta's `whatsapp_business_account` envelope. Owns routing between built-in and custom field paths via `WebhookChange._route_field`. |
| `WebhookChange` | Routes `change.field` to `WebhookValue` (strict) or `CustomWebhookValue` (permissive). Rejects unknown unregistered fields at Pydantic validation time. |
| `InboundMessageWebhook` | Canonical Universal Webhook Schema for user→business messages. Carries `InboxBase`, `UserBase`, and a `BaseMessage` subclass. |
| `CallWebhook` | Universal form for WhatsApp Calling events; dispatches to `WappaEventHandler.process_call()`. |
| `StatusWebhook` | Universal outbound model for delivery status events. `user_id` field is populated by the processors layer (BSUID > phone fallback). |

## Relationship to `wappa/schemas`

`wappa/schemas` is not an inbound schema owner. It keeps shared primitives used
across Wappa, currently `wappa/schemas/core/types.py` and `wappa/schemas/core/recipient.py`, and the neutral outbound send request models in `wappa/schemas/requests/`. (`wappa/core/types.py` is unrelated: it holds runtime enums such as `CacheType`.)

Inbound schemas belong here:

- Platform Schema: `wappa/webhooks/<platform>/...`
- Universal Webhook Schema / Universal Model: `wappa/webhooks/core/webhook_interfaces/`

Do not add inbound webhook models, WhatsApp payload schemas, or Universal Model
forms under `wappa/schemas`.

## Design Patterns

- **Abstract Base + Concrete Adapter**: `BaseWebhook` / `BaseContact` / `BaseWebhookMetadata`
  define the interface; `WhatsAppWebhook` / `WhatsAppContactAdapter` / `WhatsAppWebhookMetadata`
  implement it. New platforms add a new concrete triple without touching core.
- **Processor handler table**: each processor owns the map from a Platform message type to its schema class (WhatsApp's `_register_message_handlers` in `wappa/webhooks/whatsapp/processor/`); there is no shared schema registry.
- **Strict / Permissive Split**: Built-in Meta fields validate against strict models;
  app-registered custom fields use `CustomWebhookValue` (extra fields allowed). The gate lives
  in `WebhookChange._route_field` using Pydantic's `ValidationInfo` context. There are two
  strict built-in shapes: phone-scoped fields (`messages`, `user_preferences`,
  `user_id_update`) use `WebhookValue`; Calling and Coexistence sync fields use
  field-specific typed value models; account-scoped coexistence fields (the
  `ACCOUNT_EVENT_FIELDS` set: `account_offboarded`, `account_reconnected`) carry a flat,
  WABA-scoped value with no `metadata`, so they use the strict `AccountWebhookValue` model
  instead. Built-in fields never fall through to the permissive path.
- **Inactive Inboxes**: routing refuses them, except `INACTIVE_INBOX_FIELDS` (`account_reconnected`),
  which routes to a known inactive Inbox with `credentials=None` and no Messenger (ADR-0032).
- **Meta input tolerant and reported, Wappa output strict**: Models that parse
  data from Meta (webhook payloads; Graph API responses) use `extra="allow"` so an
  additive Meta change cannot turn into a 400 and a dropped delivery. The
  webhook processors call `report_schema_drift` from `wappa/webhooks/core/schema_drift.py` after
  parsing; the log carries the model field path and never a value. Wrong types or
  formats in modelled fields remain validation errors. Wappa's own output
  contracts (Universal Webhooks, `SystemEventDetail`, domain models) stay
  `extra="forbid"`, so Hosts never see extras. Unrouteable payloads keep the
  400/503 table of ADR-0023.

## Data Flow

```
HTTP POST (raw JSON)
        │
        ▼
  wappa/api/ controller: PLATFORMS[platform] (400 if not installed), signature check
        │  entry.webhooks.route(payload, resolver)  → RoutedWebhookDelivery per unit
        ▼
  Inbound Runtime: entry.webhooks.translate(delivery.payload, inbox_id=...)
        │
        ▼
  WhatsAppWebhook          ← WebhookEntry → WebhookChange → typed built-in value | CustomWebhookValue
        │
        │  webhook.is_incoming_message / .is_status_update / .is_system_event / .is_custom_field
        ▼
  wappa/webhooks/whatsapp/processor/ (WhatsApp processor, holding the app's FieldHandlerRegistry)
        │  Purely translates platform payload into Universal Model
        ▼
  UniversalWebhook  (InboundMessageWebhook | StatusWebhook | ErrorWebhook | SystemWebhook | CustomWebhook)
        │
        ▼
  Inbound Runtime builds Dispatch Context
        │
        ▼
  wappa/core/events/ dispatcher  →  host application handlers
```

## Instagram messaging intake

`wappa/webhooks/instagram/models/` owns the Instagram envelope and typed message families, and `wappa/webhooks/instagram/routing.py` its batch admission. `wappa/webhooks/instagram/processor/` is pure translation (its docstring holds the lane table): text, media, shares, story mentions, quick replies and postbacks become `InboundMessageWebhook` (one selection shape with WhatsApp button/list replies, ADR-0025); reactions and unreacts become `InboundMessageWebhook` carrying an `InstagramReactionMessage` (`MessageType.REACTION`, a `BaseReactionMessage` from `wappa/webhooks/core/base_message/`), the same inbound shape as WhatsApp reactions; deletions and edits become `MessageUpdateWebhook`; `read` becomes `StatusWebhook(READ)`; echoes become `OutboundEchoWebhook` (ADR-0023); standalone referrals become `SystemWebhook(REFERRAL)`; unknown events become `SystemWebhook(UNSUPPORTED_EVENT)`; comments and mentions get their own lanes. Inbound media `media_id` is the CDN attachment URL; Hosts read it through `IMediaLibrary.download` unchanged. Sending a reaction is still a missing core Messenger method (deprioritized by the user on 2026-11-06).

UserBase carries `platform_user_id` for a Platform that identifies Users by its own ID; it cannot be mixed with address evidence (`phone_number`, `bsuid`, `parent_bsuid`, WhatsApp-shaped names per ADR-0028). InboxBase permits an absent display address rather than inventing a phone. StatusWebhook carries `recipient_platform_id`; it never stores an IGSID in phone or BSUID fields. Runtime SSE identity is read from these evidence fields (`UserBase.bsuid`/`phone_number`, `CallWebhook.bsuid`/`phone_number`, `StatusWebhook.recipient_bsuid`/`recipient_phone_id`), never from a Platform check or an identifier's shape, so Instagram events carry `None` for both. All provider parsing happens after signature verification, and processors perform no I/O.

## Adding a message family or event lane

A message family is a new `MessageType` inside `InboundMessageWebhook`; an event lane is a new Universal Webhook with its own handler hook. Most additions are a family: user choices, reactions and edits all reuse existing lanes. Walk the chain in order and verify each hop before the next.

1. Shared base and enum: an abstract base in `wappa/webhooks/core/base_message/` (as `BaseReactionMessage`) and a member of `MessageType` in `wappa/schemas/core/types.py`.
2. Each Platform's model: WhatsApp under `wappa/webhooks/whatsapp/message_types/`; Instagram under `wappa/webhooks/instagram/message_types/`.
3. The processor lane table: WhatsApp's private handler table (`_message_type_handlers`, built in `WhatsAppWebhookProcessor.__init__`) in `wappa/webhooks/whatsapp/processor/`; Instagram's docstring table and its event branches in `wappa/webhooks/instagram/processor/`. Processors stay pure.
4. A new lane only: the Universal Webhook in `wappa/webhooks/core/webhook_interfaces/conversation_webhooks.py` (or `wappa/webhooks/core/webhook_interfaces/universal_webhooks/`), added to the `UniversalWebhook` union and exported from `wappa/webhooks/core/webhook_interfaces/__init__.py` and `wappa/webhooks/__init__.py`.
5. A new lane only: a `match` case in `WappaEventDispatcher.dispatch_universal_webhook` (`wappa/core/events/event_dispatcher.py`, plus its `_WEBHOOK_EMOJI` entry), a `handle_*` / `process_*` hook pair on `WappaEventHandler` in `wappa/core/events/event_handler/` (optional, no-op default), and the User the handler is scoped to in `_resolve_handler_user_id` (`wappa/core/inbound/runtime.py`).
6. Tests (`tests/test_instagram_conversations.py`, `tests/test_unified_event_lanes.py`, `tests/test_webhook_schema_ownership.py`, or the WhatsApp contract test for that family) and `docs/public-contract.md` ("Event lanes", "Universal Webhooks"), then `CHANGELOG.md`.
