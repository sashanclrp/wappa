# Meta WhatsApp Platform Compatibility Log

This file tracks upstream Meta changes that alter Wappa's WhatsApp contract.
`CHANGELOG.md` records Wappa releases; this file records why each Meta-driven
release exists, the payload shapes it covers, and what host applications must do.

## 2026-07-26: `user_actions` — marketing message interaction events

### Status

- Meta source: "Tracking click events", WhatsApp Marketing Messages API documentation (updated 2025-11-18).
- Trigger: production `WHATSAPP_WEBHOOK_CONTRACT_DRIFT error_type=extra_forbidden fields=entry.0.changes.0.user_actions` → `HTTP 400`. Ordinary messages kept parsing, but every `user_actions` delivery was rejected and retried by Meta.

### What Meta changed

Meta delivers a `user_actions` array when a user interacts with a marketing message — currently a click on the message body or its call-to-action. It arrives on the `messages` field, but the change `value` carries only `messaging_product`, `metadata`, and `user_actions`: no `messages`, no `contacts`.

```json
"user_actions": [
  {
    "action_type": "marketing_messages_link_click",
    "timestamp": "<time_of_click>",
    "marketing_messages_link_click_data": {
      "click_component": "cta",
      "product_id": "sku_id",
      "click_id": "click_id",
      "tracking_token": "example_token"
    }
  }
]
```

`action_type` and `timestamp` are required; the rest of `marketing_messages_link_click_data` is optional. Production payloads also carry action types Meta has not documented, with their own `<action_type>_data` objects (one observed variant nests a device descriptor such as `"agent": "(Android 15)"`), so the set of action types is open-ended.

### Wappa contract

- `WebhookValue.user_actions` is a typed `list[UserActionEntry]` and counts as webhook content, so a value carrying only user actions is valid.
- `UserActionEntry` is `action_type` + `timestamp` + the typed `marketing_messages_link_click_data`, with `extra="allow"`. This is deliberate: an undocumented action type must not become a sustained 400 that gets the webhook throttled or disabled. Strictness stays at `WebhookValue`, which still rejects unknown top-level keys as contract drift.
- Such a webhook routes as a system event: `SystemEventType.USER_ACTION`, with `SystemEventDetail.action_type` and `SystemEventDetail.user_action` (the entry serialized without field loss), timestamped from the action. It dispatches with `SystemWebhook.user is None` — the payload carries no user identity.
- When a `value` carries both `messages` and `user_actions`, the inbound-message path wins; the actions stay reachable via `WhatsAppWebhook.get_user_actions()`.

### Host application impact

No breaking change. Hosts that want click attribution handle `SystemEventType.USER_ACTION` in `process_system_webhook`; everyone else simply stops seeing 400s for these deliveries.

## 2026-07-21: BSUIDs, usernames, and optional phone numbers

### Status

- Meta source snapshot: `260721_meta_bsuid.md`, captured from Meta's Business
  Scoped User ID documentation on 2026-07-21.
- Wappa release: `0.22.0`.
- Trigger: production `HTTP 400` responses for
  `messages[].context.from_user_id` because `MessageContext` rejected the new
  field as `extra_forbidden`.

### What Meta changed

Meta separated a WhatsApp user's durable business-facing identity from their
phone number. A BSUID uses `CC.<identifier>`; businesses enrolled under a parent
BSUID account can also receive `CC.ENT.<identifier>`.

Phone fields such as `contacts[].wa_id`, `messages[].from`, and
`statuses[].recipient_id` can now disappear. The BSUID companions remain. User
profiles can carry `username`, and outbound requests addressed by BSUID use
`recipient` instead of `to`.

The change reaches more than ordinary text messages:

- reply contexts carry `from_user_id` and may carry `from_parent_user_id`;
- status payloads add contacts and recipient BSUID fields, including group
  participant variants;
- phone-number and BSUID change events now work without a visible phone number;
- contact-information requests add `request_contact_info`, `origin`, and `vcard`;
- Calls, group membership changes, business username events, history sync,
  WhatsApp Business app echoes, app-state sync, edits, and revokes follow the
  same optional-phone identity rules.

### Wappa contract for 0.22.0

Wappa keeps strict validation for built-in Meta payloads. Known fields get typed
models; unknown fields still fail with `HTTP 400`. An `extra_forbidden` failure
now emits a critical log event with this stable signature:

```text
WHATSAPP_WEBHOOK_CONTRACT_DRIFT error_type=extra_forbidden fields=<paths>
```

Production log aggregation must page the platform owner on that signature. The
event includes field paths and excludes payload values.

This includes account-level Coexistence values; Wappa no longer drops unknown
keys from those events.

Inbound message schemas accept the documented identity companions across every
message type Wappa handles, including `edit` and `revoke`. `UserBase.user_id`,
message `sender_id`, and
status `recipient_id` prefer the portfolio BSUID; phone numbers remain available
as optional attributes. Parent BSUIDs stay separate because their cross-portfolio
scope differs from an ordinary BSUID.

Outbound recipient routing follows Meta's request contract:

| Identifier | Meta request field |
|---|---|
| Phone number | `to` |
| BSUID or parent BSUID | `recipient` |

`WhatsAppMessenger.send_contact_request()` sends the new interactive
`request_contact_info` message. Incoming contact messages retain `origin` and
`vcard`, including the Meta shape that omits the nested contact name.

The following Meta webhook fields are native, typed Wappa contracts in 0.22.0:

- `messages`, including ordinary, system, `edit`, and `revoke` message types;
- `user_preferences` and `user_id_update`;
- `business_username_updates` and `group_participants_update`;
- `calls`, including connect, terminate, and call-status variants;
- `history`, `smb_message_echoes`, and `smb_app_state_sync`;
- `account_offboarded` and `account_reconnected`.

Coexistence history, echo, and app-state events dispatch through
`SystemWebhook`. Their validated Meta value is available in
`event_detail.coexistence_payload`; identity fields are not flattened or
discarded. Calling events dispatch through `CallWebhook` and
`WappaEventHandler.process_call()`.

### Host-application work

Wappa parses and transports identity. It doesn't own a host's contact table or
chat deduplication rules.

A host integrating 0.22.0 must store the BSUID while both phone and BSUID are
present. Future BSUID-only webhooks must resolve to that same user record. Keep
the phone number nullable, display `profile.name` or `username` before showing a
raw BSUID, and send through the canonical Wappa recipient value so the WhatsApp
adapter can choose `to` or `recipient`.

Parent BSUIDs need their own column or typed identity record. Don't merge a
portfolio BSUID and a parent BSUID as if they had the same scope.

### Meta restrictions that still apply

- One-tap, zero-tap, and copy-code authentication templates require a phone
  number. Meta can return error `131062` when a message type can't target a
  BSUID.
- A BSUID belongs to a business portfolio. Sending it through an Inbox owned by
  another portfolio fails at Meta.
- Failed status webhooks can omit both `contacts` and `recipient_user_id` when
  the original request targeted a phone number.
- Wappa doesn't persist Meta's contact book. Disabling that contact book can
  remove phone-number enrichment from later webhooks.

### API families outside Wappa's current runtime surface

The same Meta document also describes management endpoints for contact books,
username reservation, business username changes, Groups administration, Block
Users, and Calling, plus the separate Marketing Messages API. Wappa is a
messaging runtime and does not claim client methods for those administrative
endpoints. This boundary does not apply to their webhooks: every webhook shape
changed by the source document has a native contract above.

Analytics and billing contain no changes in the source document. SIP signaling
bodies are exchanged between Meta and a calling infrastructure endpoint; they
are not WhatsApp Business Account webhook payloads handled by Wappa.

### Verification matrix

Release verification must include these payloads:

- username user with BSUID and no phone;
- both phone and BSUID present;
- parent BSUID present on message, contact, reply context, and status;
- delivered/read status addressed by BSUID with no `recipient_id`;
- group participant status identifiers;
- `user_changed_user_id`, `user_preferences`, and `user_id_update`;
- business username, group participant, and Calling events;
- history, SMB echo, app-state sync, edit, and revoke payloads;
- contact request send plus the returned `origin`/`vcard` contact message;
- one unknown built-in field proving the critical drift event still fires.

### Source

- [Meta: Business-scoped user IDs](https://developers.facebook.com/documentation/business-messaging/whatsapp/business-scoped-user-ids/)
