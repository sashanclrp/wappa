# Webhooks Context — Architecture

## Responsibilities

- Parse and validate raw HTTP payloads from messaging platforms into typed Pydantic models.
- Produce `UniversalWebhook` instances (`InboundMessageWebhook`, `StatusWebhook`,
  `ErrorWebhook`, `SystemWebhook`, `CustomWebhook`) for downstream dispatch.
- Validate the platform payload's inbox identifier against the URL `inbox_id` when
  the platform provides one.
- Own every inbound webhook Pydantic schema, including platform payload schemas
  and Universal Model forms.
- Gate unknown Meta `change.field` values against a runtime registry; reject unregistered fields.
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
├── factory.py                  # SchemaFactory singleton + MessageSchemaRegistry + WebhookSchemaRegistry
│
├── core/
│   ├── base_webhook.py         # BaseWebhook, BaseContact, BaseWebhookMetadata, BaseWebhookError (ABCs)
│   ├── base_message.py         # BaseMessage ABC
│   ├── base_status.py          # Base status model
│   ├── types.py                # Re-export shim → wappa.schemas.core.types (shared primitives)
│   └── webhook_interfaces/
│       ├── base_components.py  # InboxBase, UserBase, BusinessContextBase, ForwardContextBase,
│       │                       # AdReferralBase, ConversationBase, ErrorDetailBase, SystemEventDetail
│       └── universal_webhooks.py  # InboundMessageWebhook, StatusWebhook, ErrorWebhook,
│                                  # SystemWebhook, CustomWebhook, UniversalWebhook union
│
└── whatsapp/
    ├── base_models.py          # WhatsAppMetadata, WhatsAppContact, ContactProfile,
    │                           # MessageContext, AdReferral, Conversation, Pricing, MessageError
    ├── webhook_container.py    # WhatsAppWebhook (BaseWebhook impl), WebhookEntry,
    │                           # WebhookChange, WebhookValue, AccountWebhookValue,
    │                           # CustomWebhookValue, ACCOUNT_EVENT_FIELDS,
    │                           # WhatsAppContactAdapter, WhatsAppWebhookMetadata
    ├── status_models.py        # WhatsApp status update Pydantic models
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
| `StatusWebhook` | Universal outbound model for delivery status events. `user_id` field is populated by the processors layer (BSUID > phone fallback). |
| `SchemaFactory` | Singleton (`schema_factory`). Entry point for creating platform-specific containers (`create_webhook_instance`) and per-type messages (`create_message_instance`). Delegates universal webhook assembly to `wappa/processors/`. |
| `MessageSchemaRegistry` | Holds `{PlatformType: {MessageType: BaseMessage subclass}}`. Pre-loaded with all 14 WhatsApp message types at startup. |

## Relationship to `wappa/schemas`

`wappa/schemas` is not an inbound schema owner. It keeps shared primitives used
across Wappa, currently `core/types.py` and `core/recipient.py`.

Inbound schemas belong here:

- Platform Schema: `wappa/webhooks/<platform>/...`
- Universal Webhook Schema / Universal Model: `wappa/webhooks/core/webhook_interfaces/...`
- Webhook schema factory and registries: `wappa/webhooks/factory.py`

Do not add inbound webhook models, WhatsApp payload schemas, or Universal Model
forms under `wappa/schemas`.

## Design Patterns

- **Abstract Base + Concrete Adapter**: `BaseWebhook` / `BaseContact` / `BaseWebhookMetadata`
  define the interface; `WhatsAppWebhook` / `WhatsAppContactAdapter` / `WhatsAppWebhookMetadata`
  implement it. New platforms add a new concrete triple without touching core.
- **Registry + Factory**: `MessageSchemaRegistry` and `WebhookSchemaRegistry` decouple schema
  lookup from instantiation. `SchemaFactory` is the single entry point; callers never
  import message-type classes directly.
- **Strict / Permissive Split**: Built-in Meta fields validate against strict models;
  app-registered custom fields use `CustomWebhookValue` (extra fields allowed). The gate lives
  in `WebhookChange._route_field` using Pydantic's `ValidationInfo` context. There are two
  strict built-in shapes: phone-scoped fields (`messages`, `user_preferences`,
  `user_id_update`) use `WebhookValue`; account-scoped coexistence fields (the
  `ACCOUNT_EVENT_FIELDS` set: `account_offboarded`, `account_reconnected`) carry a flat,
  WABA-scoped value with no `metadata`, so they use the strict `AccountWebhookValue` model
  instead. Built-in fields never fall through to the permissive path.

## Data Flow

```
HTTP POST (raw JSON)
        │
        ▼
  wappa/api/ route handler
        │  model_validate(payload, context={"field_registry": ...})
        ▼
  WhatsAppWebhook          ← WebhookEntry → WebhookChange → WebhookValue | AccountWebhookValue | CustomWebhookValue
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
