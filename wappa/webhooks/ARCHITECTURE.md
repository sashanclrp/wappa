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
- Register and look up per-platform, per-message-type schema classes.

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
├── core/
│   ├── schema_drift.py         # report_schema_drift, MetaSchemaDriftError (drift log + strict mode)
│   ├── base_webhook.py         # BaseWebhook, BaseContact, BaseWebhookMetadata, BaseWebhookError (ABCs)
│   ├── base_message.py         # BaseMessage ABC
│   ├── base_status.py          # Base status model
│   └── webhook_interfaces/
│       ├── base_components.py  # InboxBase, UserBase, BusinessContextBase, ForwardContextBase,
│       │                       # AdReferralBase, ConversationBase, ErrorDetailBase, SystemEventDetail
│       ├── universal_webhooks.py  # InboundMessageWebhook, CallWebhook, StatusWebhook,
│       │                          # ErrorWebhook, SystemWebhook, CustomWebhook, union
│       └── conversation_webhooks.py  # update, comment, mention, echo, history, connection lanes
│
├── instagram/
│   └── models.py               # Instagram envelope (messaging[] + changes[]) and typed message families
│
└── whatsapp/
    ├── base_models.py          # WhatsAppMetadata, WhatsAppContact, ContactProfile,
    │                           # MessageContext, AdReferral, Conversation, Pricing, MessageError
    ├── webhook_container.py    # WhatsAppWebhook (BaseWebhook impl), WebhookEntry,
    │                           # WebhookChange, WebhookValue, AccountWebhookValue,
    │                           # CustomWebhookValue, ACCOUNT_EVENT_FIELDS,
    │                           # WhatsAppContactAdapter, WhatsAppWebhookMetadata
    ├── status_models.py        # WhatsApp status update Pydantic models
    ├── call_events.py          # WhatsApp Calling connect/terminate/status models
    ├── coexistence_events.py   # History, SMB echo, and app-state sync models
    ├── system_events.py        # user_preferences and user_id_update event models
    ├── validators.py           # WhatsApp-specific field validators
    └── message_types/
        ├── text.py             # WhatsAppTextMessage
        ├── interactive.py      # WhatsAppInteractiveMessage (button_reply, list_reply)
        ├── image.py            # WhatsAppImageMessage
        ├── audio.py            # WhatsAppAudioMessage
        ├── video.py            # WhatsAppVideoMessage
        ├── document.py         # WhatsAppDocumentMessage
        ├── sticker.py          # WhatsAppStickerMessage
        ├── location.py         # WhatsAppLocationMessage
        ├── contact.py          # WhatsAppContactMessage
        ├── reaction.py         # WhatsAppReactionMessage
        ├── button.py           # WhatsAppButtonMessage (template quick-reply)
        ├── order.py            # WhatsAppOrderMessage
        ├── system.py           # WhatsAppSystemMessage (system message type within messages field)
        ├── lifecycle.py        # WhatsApp edit and revoke message types
        ├── unsupported.py      # WhatsAppUnsupportedMessage
        └── errors.py           # WhatsApp message-level error models
```

## Key Classes and Roles

| Class | Role |
|---|---|
| `BaseWebhook` | ABC that all platform webhook containers implement. Enforces `platform`, `webhook_type`, `source_id` (= `inbox_id`), and the inspection/extraction interface. |
| `WhatsAppWebhook` | Concrete `BaseWebhook` for Meta's `whatsapp_business_account` envelope. Owns routing between built-in and custom field paths via `WebhookChange._route_field`. |
| `WebhookChange` | Routes `change.field` to `WebhookValue` (strict) or `CustomWebhookValue` (permissive). Rejects unknown unregistered fields at Pydantic validation time. |
| `InboundMessageWebhook` | Canonical Universal Webhook Schema for user→business messages. Carries `InboxBase`, `UserBase`, and a `BaseMessage` subclass. |
| `CallWebhook` | Universal form for WhatsApp Calling events; dispatches to `WappaEventHandler.process_call()`. |
| `StatusWebhook` | Universal outbound model for delivery status events. `user_id` field is populated by the processors layer (BSUID > phone fallback). |

## Relationship to `wappa/schemas`

`wappa/schemas` is not an inbound schema owner. It keeps shared primitives used
across Wappa, currently `wappa/schemas/core/types.py` and `wappa/schemas/core/recipient.py`. (`wappa/core/types.py` is unrelated: it holds runtime enums such as `CacheType`.)

Inbound schemas belong here:

- Platform Schema: `wappa/webhooks/<platform>/...`
- Universal Webhook Schema / Universal Model: `wappa/webhooks/core/webhook_interfaces/`

Do not add inbound webhook models, WhatsApp payload schemas, or Universal Model
forms under `wappa/schemas`.

## Design Patterns

- **Abstract Base + Concrete Adapter**: `BaseWebhook` / `BaseContact` / `BaseWebhookMetadata`
  define the interface; `WhatsAppWebhook` / `WhatsAppContactAdapter` / `WhatsAppWebhookMetadata`
  implement it. New platforms add a new concrete triple without touching core.
- **Processor handler table**: each processor owns the map from a Platform message type to its schema class (WhatsApp's `_register_message_handlers` in `wappa/processors/whatsapp_processor.py`); there is no shared schema registry.
- **Strict / Permissive Split**: Built-in Meta fields validate against strict models;
  app-registered custom fields use `CustomWebhookValue` (extra fields allowed). The gate lives
  in `WebhookChange._route_field` using Pydantic's `ValidationInfo` context. There are two
  strict built-in shapes: phone-scoped fields (`messages`, `user_preferences`,
  `user_id_update`) use `WebhookValue`; Calling and Coexistence sync fields use
  field-specific typed value models; account-scoped coexistence fields (the
  `ACCOUNT_EVENT_FIELDS` set: `account_offboarded`, `account_reconnected`) carry a flat,
  WABA-scoped value with no `metadata`, so they use the strict `AccountWebhookValue` model
  instead. Built-in fields never fall through to the permissive path.
- **Meta input tolerant and reported, Wappa output strict**: Models that parse
  data from Meta (webhook payloads; Graph API responses) use `extra="allow"` so an
  additive Meta change cannot turn into a 400 and a dropped delivery. The
  webhook processors call `report_schema_drift` from `wappa/webhooks/core/schema_drift.py` after
  parsing; the log carries the model field path and never a value. Wrong types or
  formats in modelled fields remain validation errors. Wappa's own output
  contracts (Universal Webhooks, `SystemEventDetail`, domain models) stay
  `extra="forbid"`, so Hosts never see extras. Unrouteable payloads keep the
  400/503 table of ADR-0010.

## Data Flow

```
HTTP POST (raw JSON)
        │
        ▼
  wappa/api/ route handler
        │  model_validate(payload, context={"field_registry": ...})
        ▼
  WhatsAppWebhook          ← WebhookEntry → WebhookChange → typed built-in value | CustomWebhookValue
        │
        │  webhook.is_incoming_message / .is_status_update / .is_system_event / .is_custom_field
        ▼
  wappa/processors/ (WhatsApp processor)
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

`wappa/webhooks/instagram/models.py` owns the Instagram envelope and typed message families. `wappa/processors/instagram_processor.py` is pure translation (its docstring holds the lane table): text, media, shares, story mentions, quick replies and postbacks become `InboundMessageWebhook` (one selection shape with WhatsApp button/list replies, ADR-0016); reactions and unreacts become `InboundMessageWebhook` carrying an `InstagramReactionMessage` (`MessageType.REACTION`, a `BaseReactionMessage` from `wappa/webhooks/core/base_message.py`), the same inbound shape as WhatsApp reactions; deletions and edits become `MessageUpdateWebhook`; `read` becomes `StatusWebhook(READ)`; echoes become `OutboundEchoWebhook` (ADR-0018); standalone referrals become `SystemWebhook(REFERRAL)`; unknown events become `SystemWebhook(UNSUPPORTED_EVENT)`; comments and mentions get their own lanes. Inbound media `media_id` is the CDN attachment URL; Hosts read it through `IMediaLibrary.download` unchanged. Sending a reaction is still a missing core Messenger method ([backlog draft](../../docs/backlog/drafts/261105-mid-send-reaction-core-method.md)).

UserBase carries `platform_user_id` for native non-WhatsApp identity; it cannot be mixed with WA phone/BSUID evidence. InboxBase permits an absent display address rather than inventing a phone. StatusWebhook carries `recipient_platform_id`; it never stores an IGSID in phone or BSUID fields. Runtime SSE identity skips WA identifier-shape classification for Instagram. All provider parsing happens after signature verification, and processors perform no I/O.

## Adding a message family or event lane

A message family is a new `MessageType` inside `InboundMessageWebhook`; an event lane is a new Universal Webhook with its own handler hook. Most additions are a family: user choices, reactions and edits all reuse existing lanes. Walk the chain in order and verify each hop before the next.

1. Shared base and enum: an abstract base in `wappa/webhooks/core/base_message.py` (as `BaseReactionMessage`) and a member of `MessageType` in `wappa/schemas/core/types.py`.
2. Each Platform's model: WhatsApp under `wappa/webhooks/whatsapp/message_types/`; Instagram in `wappa/webhooks/instagram/models.py`.
3. The processor lane table: WhatsApp's handler table (`_register_message_handlers` and `_SUPPORTED_MESSAGE_TYPES`) in `wappa/processors/whatsapp_processor.py`; Instagram's docstring table and its event branches in `wappa/processors/instagram_processor.py`. Processors stay pure.
4. A new lane only: the Universal Webhook in `wappa/webhooks/core/webhook_interfaces/conversation_webhooks.py` (or `wappa/webhooks/core/webhook_interfaces/universal_webhooks.py`), added to the `UniversalWebhook` union and exported from `wappa/webhooks/core/webhook_interfaces/__init__.py` and `wappa/webhooks/__init__.py`.
5. A new lane only: a `match` case in `WappaEventDispatcher.dispatch_universal_webhook` (`wappa/core/events/event_dispatcher.py`, plus its `_WEBHOOK_EMOJI` entry), a `handle_*` / `process_*` hook pair on `WappaEventHandler` in `wappa/core/events/event_handler.py` (optional, no-op default), and the User the handler is scoped to in `_resolve_handler_user_id` (`wappa/core/inbound/runtime.py`).
6. Tests (`tests/test_instagram_conversations.py`, `tests/test_adr0016_unified_lanes.py`, `tests/test_webhook_schema_ownership.py`, or the WhatsApp contract test for that family) and `docs/public-contract.md` ("Event lanes", "Universal Webhooks"), then `CHANGELOG.md`.
