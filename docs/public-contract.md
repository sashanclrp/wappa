# Public Contract

This file tracks Wappa surfaces that host applications may import, call, configure, subscribe to, or depend on. That includes the import surface, webhook routes, event envelopes, cache namespace shape, and what `wappa init` and `wappa examples` generate (`wappa/cli/templates/`, `wappa/cli/examples/`): update templates and examples in the same change as the API they use.

A breaking change is a clean cut: no aliases, re-exports, or compatibility shims, and `CHANGELOG.md` lists every break.

## Instagram conversations contract

Implemented (unreleased); see the [migration guide](migration/instagram-conversation-contracts.md), the [capability matrix](backlog/in_progress/261103-instagram-conversations/references/capability-matrix.md) for per-capability offline/live status, and [ADR-0016](adr/0016-one-messenger-method-per-action.md) for the one-method-per-action rule. Publishing, analytics and moderation *policy* remain Host/extension responsibilities.

### Event lanes (`from wappa.webhooks import ...`)

A User's choice uses the same shape on every Platform (ADR-0016): an `InboundMessageWebhook` whose `get_interactive_selection()` returns the chosen `ReplyButton.id` / `ListRow.id`. There is no separate interaction lane.

| Native Instagram evidence | Universal Model | Hook |
| --- | --- | --- |
| text, image, audio, video, file, `share`/`ig_post`/`ig_reel`/`reel`/`story`, `story_mention`, story reply (`context.is_story_reply`) | `InboundMessageWebhook` | `process_message` |
| `message.quick_reply` | `InboundMessageWebhook` with `InstagramQuickReplyMessage` (selection) | `process_message` (once) |
| `postback` | `InboundMessageWebhook` with `InstagramButtonReplyMessage` (`interactive_type` `BUTTON_REPLY`, `is_button_reply`) | `process_message` |
| `message_edit` / `message.is_deleted` | `MessageUpdateWebhook` | `process_message_update` |
| `read` | `StatusWebhook(READ)` | `process_status` |
| echo (`is_echo`) of a message sent outside Wappa | `OutboundEchoWebhook` (echoes of Wappa's own sends are filtered, ADR-0018) | `process_outbound_echo` |
| standalone `referral` | `SystemWebhook(REFERRAL)` | `process_system_webhook` |
| `reaction` | `InboundMessageWebhook` with `InstagramReactionMessage` (`BaseReactionMessage`) | `process_message` |
| `is_unsupported`, unknown attachment/change field | `SystemWebhook(UNSUPPORTED_EVENT)` | `process_system_webhook` |
| `changes: comments` / `live_comments` | `IncomingCommentWebhook` | `process_comment` |
| `changes: mentions` | `MentionWebhook` | `process_mention` |
| registered extension field | `CustomWebhook` | registered handler |

Comment, mention and message-update lanes exist because only Instagram emits those events. New hooks are optional with no-op defaults and default INFO logs (references only, no comment text/payloads). Instagram media messages expose `url`/`urls` (CDN references, may expire), and `media_id` is that URL, not a WhatsApp Media ID. `IncomingCommentWebhook.parent_comment_ref is None` means *unknown*. `MentionWebhook` with `subject=media` has no Comment. Comment dispatch uses the author's scoped ID only as cache scope; it does not make the author DM-addressable.

### Messenger operations: one method per action (ADR-0016)

Every action that exists on more than one Platform has exactly one `IMessenger` method; each adapter maps it onto its native API and raises a clear error before any provider call when it cannot honour the call. Presentation the Platform cannot show may be dropped; meaning never is. Hosts check `messenger.supported_operations` once and never branch on Platform name. Instagram's `supported_operations`: `send_text`, `send_text:private_reply`, `send_image`, `send_audio`, `send_video`, `send_document`, `send_button_message`, `send_list_message`, `send_cta_message`, `send_carousel`, `mark_as_read`, `send_sticker`, `send_location`, `send_contact`. Others (today `send_location_request` and `send_contact_request`) raise `UnsupportedOperationError`.

| Operation | WhatsApp | Instagram (rejected before I/O when a limit fails) |
| --- | --- | --- |
| `send_text` | text message | DirectMessage or `PrivateReply(comment_ref=...)`; 1000 UTF-8 bytes; PrivateReply excludes `reply_to_message_id` |
| `send_image/audio/video/document` | media message (URL or Media ID) | https URL, an `IMediaLibrary.upload` attachment_id, or a local `Path` (uploaded first); image png/jpeg/gif ≤ 8 MB, audio aac/m4a/wav/mp4, video mp4/ogg/avi/mov/webm, file pdf ≤ 25 MB; a caption is sent as a follow-up text; `filename` and `transcript` are ignored |
| `send_sticker` | sticker: `.webp` only (512x512; 100 KB static, 500 KB animated) | sent as an image: `.png`/`.jpg`/`.jpeg`/`.gif` (8 MB) |
| `send_location(latitude, longitude, target, name=None, address=None)` | location message | text: name, address and a `📍` Google Maps link |
| `send_contact(contact, target)` | contacts message | text card (👤 name, organization, 📞 phones, ✉️ emails, 🔗 urls), validated with the WhatsApp `ContactCard` shape |
| `send_location_request` / `send_contact_request` | interactive request | `UnsupportedOperationError`: a text prompt cannot return the data; gate on `supported_operations` |
| `mark_as_read(message_id, target, *, typing=False)` | marks the message read; `typing` sends the typing indicator; `target` is checked against the Inbox | thread-level `mark_seen` on `target`'s thread, then `typing_on` if `typing` (only after seen is accepted); returns `MessageResult` |
| `send_button_message(buttons, target, body, header=None, footer=None, reply_to_message_id=None)` | interactive reply buttons | button template with postback buttons: text ≤ 640, 1–3 `ReplyButton`, title ≤ 20; text header and footer fold into the text (`"\n\n"`-joined); an image header (`ButtonHeader(image_url="https://...")`) becomes a one-element generic card (body = title ≤ 80, footer = subtitle ≤ 80); `ButtonHeader(image_media_id=...)` raises `UnsupportedOperationError` |
| `send_list_message(sections, target, body, button_text, header=None, footer=None)` | interactive list; text header only (an image `ButtonHeader` fails with `INVALID_HEADER_TYPE`) | quick replies: all rows flattened, ≤ 13, row title ≤ 20, row `id` = payload; section titles, row descriptions and `button_text` are dropped; a text header and the footer fold into the text; an image header raises `UnsupportedOperationError` |
| `send_cta_message(...)` | `cta_url` | button template with one `web_url` button; header/footer fold into the text |
| `send_carousel(cards, target, body)` | 2–10 cards; interactive media carousel; every card needs `image_url`; title + subtitle become the card body (≤ 160); buttons are one `UrlButton` or 1–2 `ReplyButton`s, same kind and count on every card | 2–10 cards; `body` is sent as a text message first, then a generic template (title/subtitle ≤ 80, ≤ 3 buttons) |

`send_sticker(sticker_source, target)` takes one source or a list of renditions of the same sticker (`MediaRenditions` = `str | Path | Sequence[str | Path]`, in `wappa.domain.media_renditions`). Each adapter sends the first rendition whose extension its Platform accepts: WhatsApp `.webp`; Instagram `.png`/`.jpg`/`.jpeg`/`.gif`. A single extension-less source (a Platform media ID) passes through. When nothing fits, `ValueError` is raised before any Platform call (HTTP route: 400). Wappa never converts media. Serve both Platforms with `send_sticker(["sticker.webp", "sticker.png"], target)`.

For a single card, use `send_button_message` with an image header. Media storage and inbound media reads are the `IMediaLibrary` capability, and WhatsApp Templates the `ITemplateMessaging` capability (below). `send_location_request` and `send_contact_request` are core contract methods that only WhatsApp implements today.

Known gap: `send_reaction(message_id, emoji, target)` is a missing core method (WhatsApp, Instagram and Telegram all support reactions); no Platform sends reactions yet. Inbound reactions on both Platforms arrive in `process_message` as `BaseReactionMessage`. See `docs/backlog/drafts/261105-mid-send-reaction-core-method.md`.

Interactive values `ReplyButton(id, title)`, `UrlButton`, `CardButton = ReplyButton | UrlButton`, `MessageCard(title, subtitle, image_url, default_url, buttons)`, `ButtonHeader`, `ListSection(title, rows)` and `ListRow(id, title, description=None)`, and results (`MessageResult`, `CommentResult`, `ControlResult`, `OperationOutcome`, `message_outcome`) are exported from `wappa.messaging`. The interactive values are defined in the neutral `wappa.domain.interactive`, the results in `wappa.domain.results`; no WhatsApp module defines or re-exports them. `ButtonHeader` is the one header of `send_button_message` and `send_list_message`: exactly one of `text`, `image_url` or `image_media_id` (a media ID from the Inbox's own Platform). Video and document headers are not neutral and are not offered. Platform limits (WhatsApp: header text ≤ 60, section and row title ≤ 24, ≤ 10 sections and rows; Instagram: see the table) are checked by each adapter, not by the neutral values; `ListSection` only requires at least one row and unique row IDs. `MessageResult.platform` is required, and `platform_response` is its single native-evidence field (the WhatsApp adapter stores the Cloud API response body there; it is excluded from serialization). Outcomes are `accepted`/`rejected`/`indeterminate`; indeterminate sends and mutations are never retried.

### Focused capabilities (separate responsibilities and Platform-only exceptions)

Responsibilities other than sending conversation messages, and actions with no reasonable mapping on other Platforms, are capabilities, not contract methods. `messenger.capability(kind)` returns an Inbox-bound implementation or `None`; `require_capability(kind)` raises `UnsupportedOperationError`. `kind` is the capability class (`IMediaLibrary`, `ITemplateMessaging`, `ICommentControls`, `IConversationContentReader`, `IAttachmentMediaReader`).

`IMediaLibrary` (WhatsApp and Instagram; exported from `wappa.messaging` with `MediaFamily` and `UploadResult`) offers `upload(path, family: MediaFamily) -> UploadResult` (`success`, `media_id`, `outcome`, `error_code`) and `download(media_id) -> ReadResult[MediaBytes]`. WhatsApp uploads to the Media API and downloads by Media ID; Instagram uploads to `/{ig}/message_attachments` with `is_reusable` (the `media_id` is an attachment_id) and downloads by a credential-free Meta CDN fetch of the attachment URL. Send an uploaded file with `send_image(result.media_id, target)` (or video/audio/document) on the same Inbox. For inbound media, pass `webhook.message.media_id` to `download` unchanged on both Platforms. `ITemplateMessaging` (WhatsApp) offers `send_text_template`, `send_media_template` and `send_location_template` with the earlier signatures. Through a `MessengerPipeline` it still runs message middleware under those method names; `OutboundRuntime` / `InboxTemplateTransport` resolve it internally. `ICommentControls` offers `reply_comment(comment_ref, text)` → `CommentResult`, plus `hide_comment`, `unhide_comment`, `delete_comment` and `set_comments_enabled`. Private replies to a commenter use `send_text(text, target=PrivateReply(comment_ref=...))`. Instagram's reader also offers `get_mentioned_post` / `get_mentioned_comment`. Reads return `ReadResult` (`found`, `not_found`, `access_denied`, `rejected`, `unavailable`); comment pages are `ContentPage` with `next_cursor` (≤ 50). Prefer `IMediaLibrary.download` over `IAttachmentMediaReader`; the reader never sends credentials, only fetches https Meta CDN hosts (`fbsbx.com`, `fbcdn.net`, `cdninstagram.com`), and bounds redirects (3), time and size (25 MB default).

### Credential access, outbound runtime, extensions, connection

- `wappa.domain.inbox.InboxCredentialAccess.from_app(app).resolve(inbox_ref)` →
  `TrustedInboxCredential` (current token/version, Graph version/base; masked
  repr). Directory errors propagate typed. Host authorizes first.
- `OutboundRuntime.from_app(app).messenger(inbox_ref)` → Inbox-bound
  Messenger with app middleware for Host-initiated sends.
- `register_webhook_field(..., platform=PlatformType.INSTAGRAM)` on `Wappa`
  and `WappaBuilder`; Instagram built-in fields are reserved.
- `wappa.connections` (ADR-0017): the `IInboxConnector` contract (`begin` →
  `AuthorizationRequest`, `complete` → `ConnectionGrant` with `DiscoveredInbox`
  + `InboxReadiness`, `activate` → `ActivationResult` with the encrypted
  record, `disconnect(inbox_ref, account_ref, token)`), implemented by
  `InstagramConnector` and `WhatsAppConnector` on `MetaLoginConfig`; plus
  `IConnectionIntentStore`/`InMemoryConnectionIntentStore`,
  `InstagramSubscriptions`, `parse_signed_request` and the
  `InboxConnectionError` hierarchy.

## Instagram text adapter and explicit send targets

Instagram uses the existing GET/POST `/webhook/inboxes/instagram` callback,
separate from `/webhook/inboxes/whatsapp`. Both use the same application Meta
trust configuration, including the existing `WP_WEBHOOK_VERIFY_TOKEN` name.
There is no signature bypass. GET verification needs no Inbox registration.
POST admission requires registered active credentials in explicit mode; unknown
or inactive Inboxes return 400, directory/integrity outages return 503, invalid
signatures return 401, and malformed or mismatched payloads return 400.

InstagramActiveInboxCredentialRecord and InstagramInactiveInboxCredentialRecord
are available from `wappa.domain.inbox`. They use `platform=instagram`, with
`inbox_id` and `platform_account_id` both identifying the professional account.
The active record's encrypted token is a Unified Login Business Integration
System User Access Token. The same source, refresh, rotation, deactivation, and
envelope-binding rules apply as for WhatsApp. Wappa requires no `IG_*`
environment variables; a consumer obtains credentials during its connection
flow and supplies records through IInboxDirectorySource. The controlled echo
example uses its own local settings to bootstrap a record.

The first lanes are:

- User plain text → InboundMessageWebhook → process_message.
- `read.mid` seen evidence → StatusWebhook READ → process_status.
- Echo of a message sent outside Wappa → OutboundEchoWebhook → process_outbound_echo (Wappa's own sends are filtered, ADR-0018).
- Other valid messaging events → SystemWebhook UNSUPPORTED_EVENT, with native
  evidence in event_detail.platform_event; no automatic reply or invented text.

The full lane table is in "Instagram conversations contract" above. An ErrorWebhook is not
invented from an outbound HTTP error. UserBase.platform_user_id carries IGSID
and is mutually exclusive with WA phone/BSUID evidence. StatusWebhook exposes
recipient_platform_id; recipient_id selects it when present. InboxBase permits
display_address=None when the callback supplies no display address.

All recipient-based IMessenger methods now take `target: DirectMessage`:

```python
from wappa.messaging import DirectMessage

result = await self.messenger.send_text(
    text=webhook.get_message_text(),
    target=DirectMessage(
        inbox_ref=self.inbox_ref,
        addresses=webhook.user.delivery_addresses(),
    ),
)
```

`DirectMessage(inbox_ref, addresses=DeliveryAddresses)` carries every known
Delivery Address of one User (ADR-0019). `user.delivery_addresses()` builds it
from a webhook (WhatsApp BSUID + phone, Instagram scoped ID); outside webhooks
use `DeliveryAddresses.of(*known)`. The target is the only way to address a
send; the Messenger never holds a recipient. The WhatsApp adapter sends to the
phone first, then the BSUID, and moves on only when Meta rejects the address
itself (`131030`, `131062`); authentication Templates go to phones only.
`MessageResult.attempted_recipients` lists the addresses tried after a
fallback. `DirectMessage.recipient_id` / `.address` read the first address.

DirectMessage is immutable, rejects extra fields/blank recipients, and includes
InboxRef. Cross-Inbox targets fail before middleware/provider I/O. Bare strings
and the `recipient` keyword no longer work on IMessenger; there is no compatibility
wrapper. This applies to WhatsApp sends too. Read actions retain their separate
message-ID contract. `send_text` additionally accepts PrivateReply; adapters
whose Platform has no comment-addressed replies (WhatsApp) reject it at send.
WhatsApp REST request models and independent typed Template transport retain
their recipient inputs and explicitly translate them inside their adapters.

SendInvocation stores target rather than a recipient field, and its serialized
request has a structured target object. Its derived recipient property exposes
the native address to middleware. `supported_operations` is the implemented
adapter operation set (Instagram's full set is listed above). Other
operations raise UnsupportedOperationError, also exported from wappa.messaging.

Instagram text accepts up to 1000 UTF-8 bytes and an optional reply_to_message_id.
Preview suppression is unsupported. MessageResult sets platform=instagram,
retains native recipient/message IDs, and leaves WA phone/BSUID evidence empty.
Its excluded platform_response carries native response evidence. Success means
API acceptance. Timeout/disconnect, 5xx, and a 2xx response lacking a Message ID
are INDETERMINATE; callers must not automatically resend. No retry or provider
error-body logging is added. Results remain in the historical WA basic-model
module in this first slice; neutral module extraction remains follow-up.

See [ADR-0014](adr/0014-instagram-text-and-explicit-messenger-targets.md) and the
[Instagram setup walkthrough](backlog/in_progress/261103-instagram-conversations/references/setup.md).

## Inbox Execution Context (`X-Wappa-Inbox-ID`)

Wappa's messaging HTTP API is mounted at `/api/{platform}` (`whatsapp` or `instagram`; [ADR-0021](adr/0021-platform-messaging-http-api.md)). It has no Meta payload to route from, so an authorized caller selects the Inbox with the Platform in the path plus `X-Wappa-Inbox-ID: <inbox_id>` (`phone_number_id` for WhatsApp, the Instagram professional account ID for Instagram). **The header selects runtime scope and proves only that Wappa knows an active Inbox. It is not a credential and grants no permission.** Host authentication and authorization (for example `AuthPlugin`) decide whether the caller may operate that Inbox, and they run before Inbox resolution.

Resolution happens once per request through `get_inbox_execution_context` (`from wappa.api.dependencies import ...`): Host auth → read the header → combine with the path's Platform → legacy default when the header is absent (only for the default Inbox's own Platform) → resolve the active record through the credential resolver → build the required capabilities → share the `InboxExecutionContext` with every dependency in the route. The context exposes `inbox_ref`, `inbox_id`, `account_ref`, `platform_account_id`, and `routing_mode`; it never exposes the decrypted token.

| Operation family | Inbox required |
| --- | ---: |
| Send text; mark read or typing | yes |
| Send image, video, audio, document, sticker | yes |
| Send buttons, list, CTA | yes |
| Send contact, location, location request | yes |
| Send text-, media-, or location-header Template | yes |
| Upload, inspect, download, or delete media | yes (download resolves the media object with the selected token first) |
| Get Template by ID/name, list Templates, get namespace | yes (WABA comes from the record; no caller-supplied WABA) |
| Inbox-specific WhatsApp health (`/api/whatsapp/health`) | yes |
| State Handler set, get, delete | yes |
| Validate contact or coordinates | no |
| Text, media, interactive, Template limits | no |
| Root health, docs, OpenAPI | no |

Platform behaviour of the same routes:

- Send routes call the Inbox's own Messenger through `OutboundRuntime` (with app Messenger middleware), so `/api/instagram/messages/send-text` and `/api/whatsapp/messages/send-text` are the same call. `POST /interactive/send-carousel` maps to `send_carousel`.
- Send bodies (`DeliveryRequest`) take `recipient` plus optional `addresses` (the User's other known addresses; WhatsApp falls back between phone and BSUID, ADR-0019). `mark-as-read` requires `recipient` (the User who sent the message) on every Platform. `send-buttons` takes `header` as a `ButtonHeader` object (`{"text": ...}`, `{"image_url": ...}` or `{"image_media_id": ...}`); `send-list` keeps a plain-text `header`.
- Every Platform gap answers **501** `"<platform> does not provide <capability>"`. Capability routes gate on what the Inbox's Messenger provides (`requires_capability(kind)`): comments and post reads (`ICommentControls`, `IConversationContentReader`), history (`IConversationHistoryReader`), media upload (`IMediaLibrary`; WhatsApp keeps its Media API handler). Routes with no capability interface yet (Templates, Template info, media info/download/delete, limits, validators, `/health`) are WhatsApp-only.
- Capability routes: `POST /comments/{id}/reply|hide|unhide`, `DELETE /comments/{id}`, `POST /posts/{media_id}/comments-enabled` (group `comment_controls`), `GET /posts/{media_id}`, `/posts/{media_id}/comments`, `/comments/{id}`, `/comments/{id}/replies`, `/conversations/{user_id}/messages` (always mounted), `POST /messages/send-private-reply` (outbound transport).
- A Host route that depends on `get_inbox_execution_context` must declare a `{platform}` path parameter.
- An action the Platform cannot perform (`UnsupportedOperationError`, e.g. `send-location-request` on Instagram) answers **501**; a local rule violation (`ValueError`, e.g. a non-WebP WhatsApp sticker) answers **400**.
- An unknown `{platform}` answers 404 before any directory lookup.

Local-only routes ignore a supplied header entirely: they do not validate it, bind it, or read the directory, so an unknown header or an unavailable directory cannot make them fail.

| Condition | Status |
| --- | ---: |
| Inbox-dependent route, no header, no legacy default | 400 |
| Header format invalid (checked before any directory call) | 400 |
| Healthy directory confirms unknown or inactive Inbox | 404 |
| Directory, source, cache, or decrypt unavailable | 503 |
| Host authentication or authorization failure | the Auth plugin's status |
| Local-only route with any header | normal local response |

In legacy mode the header may repeat the configured `WP_PHONE_ID`; any other value answers 404. No Inbox context leaks between sequential requests on one worker.

The former demonstration routes `/interactive/send-complex-buttons` and `/interactive/send-menu-list` are not part of the HTTP contract; their code lives in the full example.

## Dispatch Context, `db`, and `db_read`

Webhook, API-message, cron, and External Webhook Source paths bind isolated handler clones. Messaging paths bind Inbox and User context through `DispatchContextBuilder` (`from wappa.core.dispatch import ...`). Inbox-independent external events bind database factories without inventing an Inbox.

- `db` is the Primary Session Factory: writes and primary-consistent reads.
- `db_read` is the Read-Intent Session Factory: eventual consistency; may use a replica or the current fallback behaviour.
- Both stay optional `SessionFactory | None`. Wappa never installs a fake session. `WappaEventHandler.require_database()` turns `None` into one direct `RuntimeError`.
- Wappa supplies sessions only. It adds no Inbox predicates, Owner authorization, row-level security, or Host repository invariants. A Host that writes and must read its write uses `db`, preferably in one transaction.
- v0.27 does **not** claim database-enforced read-only `db_read`, replica cooldown, or configurable primary fallback; that is separate PostgreSQL plugin work.

## Inbox-aware identity resolution

Host applications may register `IIdentityResolver` through `WappaBuilder.with_identity_resolver(resolver)` or `Wappa.set_identity_resolver(resolver)`. Its public contract is `resolve(recipient, *, inbox_id) -> str`.

`inbox_id` is required for every resolution. A resolver must scope its lookup by both the transport recipient and the Inbox, so the same recipient can resolve to different canonical Users in different Inboxes. `PassthroughIdentityResolver` accepts the same contract and returns the recipient unchanged.

Wappa passes the active Inbox to identity resolution from the Inbox-scoped cache factory or the current outbound API context. API event construction fails when the runtime has no Inbox context; it does not create an event with an `"unknown"` Inbox.

## Universal Webhooks

Host applications import inbound webhook schemas and Universal Models from
`wappa.webhooks`.

The canonical and only Meta WhatsApp callback is `GET + POST /webhook/inboxes/whatsapp`. GET answers Meta's challenge with `MetaApplicationConfig.whatsapp_webhook_verify_token` and reads nothing else. POST is authenticated before it is parsed:

1. Wappa reads the exact body bytes once and requires `X-Hub-Signature-256: sha256=<hex HMAC-SHA256>` computed with `META_APP_SECRET`. A missing, malformed, or mismatched signature answers the same generic `401` before any JSON decoding, directory read, payload logging, or work scheduling. `MetaCallbackAuthenticator(app_secret).sign(body)` (`from wappa.core.inbound import ...`) produces the header for tests and local tools.
2. Only then is JSON decoded; a non-object root is `400`.
3. Each `entry[].changes[]` is routed: `value.metadata.phone_number_id` (or a flat `value.phone_number_id`) becomes `InboxRef.whatsapp(...)`, whose active record must belong to `PlatformAccountRef.whatsapp(entry[].id)` — a mismatch rejects the whole callback with `400`. A change without a phone number fans out to every validated active member of that WABA, sorted and duplicate-free. `entry[].id` is never an Inbox; a flat `value.waba_id` must match it.
4. Every Dispatch Context in the batch is built before any delivery is scheduled. A failure at item N schedules none of items 1..N-1.

| Condition | Status |
| --- | ---: |
| `{platform}` is not an installed Platform (GET or POST; `telegram`, `teams`, unknown names) | 400 |
| Missing, malformed, or invalid Meta POST signature | 401 |
| Invalid GET verify token | 403 |
| Malformed JSON or non-object root | 400 |
| Invalid Inbox identifier format in the authenticated payload | 400 |
| Confirmed unknown or inactive payload Inbox | 400 |
| Inbox and WABA membership mismatch | 400 |
| Confirmed WABA with no active Inboxes | 400 |
| Other structurally unroutable authenticated payload | 400 |
| Authenticated, routable payload with unmodelled fields or an unmodelled webhook field | 200 (processed, or `SystemWebhook(UNSUPPORTED_EVENT)`) plus a `META_SCHEMA_DRIFT` log |
| Directory, cache, source, decrypt, or runtime dependency unavailable | 503 |
| Unexpected Wappa defect | 500 |

The removed `/webhook/inboxes/{inbox_id}/whatsapp` and `/webhook/messenger/{platform}/verify` routes return 404. There is no alias, redirect, flag, or deprecation route.

### Callback cutover and rollback

Deploy the version that answers `/webhook/inboxes/whatsapp` with `META_APP_SECRET`, change the Meta callback URL, complete GET verification, then send one real message to every active Inbox. Rollback needs both the previous package and the previous callback URL; reverting one alone stops delivery.

### Delivery semantics

Wappa delivers Platform events **at least once**. It does not deduplicate them, and it does not guarantee ordering across the deliveries derived from a single HTTP request.

One Platform event can reach a handler more than once through three independent multipliers:

1. Meta retries a callback it considers unacknowledged or failed.
2. Batch splitting turns one HTTP request into one delivery per entry/change pair.
3. WABA fan-out turns one account-scoped change into one delivery per active Inbox under that Platform Account.

The third multiplier is the one that changes host obligations. A WABA carrying `N` active Inboxes multiplies every account-level change by `N`, so an account-event handler that mutates shared, Inbox-independent state — a WABA-level counter, a shared billing record, an operator notification — performs that work `N` times per change.

Wappa guarantees that each delivery carries exactly one Platform change, is scoped to exactly one Inbox whose active record and WABA membership were proven, and is emitted in a deterministic Inbox order, so replaying the same payload behaves identically.

Host applications must make account-scoped handlers idempotent, key side effects on a Platform-supplied identifier rather than on arrival, and never assume one handler invocation equals one Platform event. Wappa does not supply a delivery fingerprint; deduplication is the host's responsibility.

Public inbound imports include:

- `from wappa.webhooks import InboundMessageWebhook`
- `from wappa.webhooks import CallWebhook`
- `from wappa.webhooks.core.webhook_interfaces import InboundMessageWebhook`
- `from wappa.webhooks import StatusWebhook`
- `from wappa.webhooks import ErrorWebhook`
- `from wappa.webhooks import SystemWebhook`
- `from wappa.webhooks import CustomWebhook`
- `from wappa.webhooks import UniversalWebhook`
- `from wappa.webhooks.whatsapp import WhatsAppWebhook`
- `from wappa.webhooks.whatsapp.*` platform payload schemas

WhatsApp built-in payload schemas are strict (`extra="forbid"`).
Click-to-WhatsApp referrals accept an omitted `ctwa_clid`, as Meta does not send that field for WhatsApp Status ad placements. The universal `AdReferralBase` retains those referrals with `click_id=None`.
`system` messages (`user_changed_user_id`) accept Meta's observed `system.previous_user_id` — the BSUID before the change — and surface it on `SystemEventDetail.previous_user_id`/`current_user_id`, the same fields the `user_id_update` field path populates.
A `contacts[].profile.name` delivered blank or whitespace-only normalizes to `None` (the already-supported absent-name shape) instead of failing the delivery; real names pass through untouched.
Status `pricing` accepts Meta's `subtype` as an open string (`paid_exempt` is documented, `free_tier` is observed in production but undocumented) and surfaces it in `WhatsAppMessageStatus.get_delivery_info()` and, when the status carries a `conversation`, on `ConversationBase.pricing_subtype`; other unknown `pricing` keys are still rejected.
`MessageContext.from_bsuid` maps Meta's `context.from_user_id` reply identifier.
Incoming WhatsApp models also retain optional portfolio-parent identifiers,
group identifiers, username-only contacts, and call-permission replies. Status
Universal Models expose portfolio and parent BSUIDs plus group participant
identity when Meta sends them.
For incoming group messages, `conversation_id` is the Meta `group_id` and
`conversation_type` is `group`; `sender_id` remains the participant's BSUID or
phone fallback. Group status `user_id` resolves from the participant identity,
not the group ID.
One event, one lane, on every Platform (ADR-0016), all typed:

| Event | Universal Model / hook | WhatsApp source | Instagram source |
| --- | --- | --- | --- |
| Edit / delete of an earlier message | `MessageUpdateWebhook` → `process_message_update` (typed replacement in `message`) | `edit`, `revoke` | `message_edit`, unsend |
| Reaction | `InboundMessageWebhook` with `BaseReactionMessage` (`target_message_id`, `emoji`, `is_removal`) | `reaction` | `message_reactions` |
| Entry point | `InboundMessageWebhook.entry_referral: EntryReferral` (`EntryPointKind`); standalone Instagram referral → `SystemWebhook(REFERRAL)` with `event_detail.entry_referral` | Click-to-WhatsApp `referral`  | ad / ig.me `referral` |
| Business message sent outside Wappa | `OutboundEchoWebhook` → `process_outbound_echo` (Wappa's own sends filtered out) | Coexistence `smb_message_echoes` | `message_echoes` |
| History backfill | `HistorySyncWebhook` → `process_history_sync` (push) or `IConversationHistoryReader.read_history` (pull), both `HistoryThread` | Coexistence `history` | Conversations API |
| Inbox connection | `InboxConnectionWebhook` → `process_inbox_connection` | `account_offboarded`, `account_reconnected` | `POST /webhook/inboxes/instagram/deauthorize` |

The Instagram deauthorize callback fires only for grants made through Instagram Login. Unified Login (Facebook Login for Business) issues business-owned `SYSTEM_USER` tokens that never expire, and Meta sends no per-user deauthorize for them; revoke those through the business portfolio's system user or the Host's connector (deactivate the record, then `IInboxConnector.disconnect`).

`OutboundEchoWebhook` carries only messages sent outside Wappa; the filter is fixed (ADR-0018). WhatsApp Coexistence needs none. Instagram echoes carry no sender-app evidence, so Wappa drops an echo whose `message_id` is in its `ISentMessageRegistry` (IDs of messages it sent, one key per send: 10-minute TTL, cut to a 2-minute grace when its echo is claimed; Table Cache `<inbox>:df:wappa_sent_messages:pkid:<message_id>`; shared across workers only on Redis). `origin=UNKNOWN` means the registry could not answer and the echo was delivered rather than lost. Hosts store what arrives. `SystemEventDetail` payloads are typed: `contact_sync: ContactSync` (Coexistence `smb_app_state_sync`), `group_update: GroupUpdate`, `user_action: UserAction`, `entry_referral: EntryReferral`. `platform_event` is set only for `UNSUPPORTED_EVENT`. The `SystemEventType` members `SMB_MESSAGE_ECHO`, `HISTORY_SYNC`, `ACCOUNT_OFFBOARDED` and `ACCOUNT_RECONNECTED` are no longer emitted, and `coexistence_payload` is removed.
A WhatsApp `change.field` that Wappa does not model and the Host did not register with `register_webhook_field` is answered `200` and reaches `process_system_webhook` as `SystemWebhook(UNSUPPORTED_EVENT)` with `event_detail.platform_event = {"field", "value"}`, the same as Instagram. It was HTTP 400 before 0.34.

Unmodelled properties inside a modelled Meta payload (for example a new `pricing.subtype`) are accepted, the event is processed, and Wappa logs `META_SCHEMA_DRIFT platform=<p> field=<Model.field>` once per field per process, without the value. Alert on that signature and model the field when it appears. The `WHATSAPP_WEBHOOK_CONTRACT_DRIFT` critical log no longer exists. Set `WAPPA_STRICT_META_SCHEMA=1` in test suites to raise `MetaSchemaDriftError` on drift instead. Wrong types or formats in modelled fields are still errors, and Hosts never see the extra properties.

`InboundMessageWebhook` is the only public inbound-message Universal Model name. Wappa does not provide a compatibility alias for previous inbound-message model names.

`CallWebhook` dispatches WhatsApp Calling connect, terminate, and status events
to `WappaEventHandler.process_call(webhook)`. The default hook is a no-op because
hosts may deliberately ignore calling events.

The old inbound schema paths under `wappa.schemas.whatsapp`,
`wappa.schemas.factory`, and `wappa.schemas.core.base_*` are intentionally
removed. No compatibility import path is provided.

`wappa.schemas` remains public only for shared primitives such as:

- `wappa.schemas.core.types.PlatformType`
- `wappa.schemas.core.types.MessageType`
- `wappa.schemas.core.recipient.RecipientRequest`
- `wappa.schemas.core.recipient.apply_recipient_to_payload`

`wappa.schemas.core.types` holds vocabulary only (`PlatformType`, `MessageType` and sibling enums). It has no per-Platform capability table: `PLATFORM_CAPABILITIES` and its helpers were removed in 0.34. Which Platforms are installed is decided by the Platform Registry, `PLATFORMS` (`from wappa.platforms import ...`, a read-only `Mapping[PlatformType, PlatformEntry]`), not by `PlatformType`; `TELEGRAM` and `TEAMS` are reserved members with no entry. Every surface that takes a Platform reads it: `GET`/`POST /webhook/inboxes/{platform}` answer `400` for an uninstalled Platform (before 0.34 GET answered the challenge for any `PlatformType`), `/webhook/platforms` and `/webhook/inboxes/{platform}/status` list its keys as `installed_platforms`, `/api/{platform}` accepts only its keys, and `MessengerFactory` raises `ValueError` for any other Platform.

`PlatformEntry` is a frozen dataclass: `webhooks: PlatformWebhooks`, `build_messenger(credentials, deps) -> IMessenger`, `display_name`. `PlatformWebhooks` (`from wappa.core.inbound import ...`) is the inbound Platform protocol: `platform`, `builtin_fields: frozenset[str]`, `async route(payload, resolver) -> tuple[RoutedWebhookDelivery, ...]` (may do credential I/O) and `async translate(payload, *, inbox_id) -> UniversalWebhook` (pure). `build_platforms(field_registry)` builds the table; `WappaBuilder.build()` calls it once with the app's `FieldHandlerRegistry` and stores it on `app.state.platforms`, and `BUILTIN_FIELDS` holds each Platform's reserved webhook field names. `WhatsAppWebhookProcessor` and `InstagramWebhookProcessor` take the registry in their constructor (`None` means no Host extension fields); `ProcessorFactory`, `processor_factory` and `BaseWebhookProcessor` were removed in 0.34.

Webhook processors are translation-only adapters. They return Universal Models and do not mutate ContextVars, construct messengers, construct cache factories, open DB sessions, clone handlers, or dispatch events. Those responsibilities belong to the Inbound Runtime and its Dispatch Context.

## External Webhook Sources

Host applications may register non-messaging webhooks through `WebhookPlugin`
and an `IWebhookProcessor`. External Webhook Sources include payment systems,
CRMs, operational tools, and other systems that are not messaging Platforms.

Public imports include:

- `from wappa import ExternalEvent`
- `from wappa import IWebhookProcessor`
- `from wappa import IExternalWebhookContextResolver`
- `from wappa import ResolvedExternalWebhookContext`
- `from wappa import HMACSignatureVerifier`
- `from wappa import ExternalEventRegistry`, `from wappa import DispatchReport`
- `from wappa.core.plugins import WebhookPlugin`

An `IWebhookProcessor` must provide:

- `get_source_name() -> str`
- `parse_event(request, webhook_id: str | None) -> ExternalEvent`

The default callback is ID-less:

- `POST {prefix}`
- `GET {prefix}/status`

`include_webhook_id=True` changes only the callback to
`POST {prefix}/{webhook_id}`. Each plugin chooses its route form independently.
Webhook ID is opaque transport routing data. It never identifies, selects, or
authorizes an Inbox.

`ExternalEvent` contains `source`, `event_type`, optional `webhook_id`, payload,
metadata, timestamp, and excluded raw data. It contains no Inbox or User fields.
Wappa assigns the route Webhook ID after parsing, so a processor cannot replace
route identity through its returned event.

Admission runs before the HTTP acknowledgment:

- snapshot the exact body;
- call the processor, which authenticates and parses the request;
- verify that the event source matches the plugin source;
- run the optional Host context resolver;
- bind a handler with database-only or Inbox-scoped capabilities;
- schedule handler dispatch through `BackgroundWorkTracker`.

An `IExternalWebhookContextResolver` receives `(request, event, db, db_read)`
after processor authentication. It returns
`ResolvedExternalWebhookContext(inbox_ref, user_id=None)` or `None`. `None` means
deliberate Inbox-independent dispatch. The handler receives database factories,
when configured, while Inbox, User, Messenger, and Cache Factory remain `None`.
An Inbox resolution provides Messenger; adding a User also provides the
user-scoped Cache Factory.

Resolvers may use authenticated event payload, headers, database state, or
trusted `request.state` prepared by FastAPI dependencies or middleware. Request
state prepared before authentication is only candidate evidence unless that
middleware authenticates the request itself.

Processors and resolvers may raise `HTTPException` for an expected response.
Wappa maps validation failures to 400 and unexpected admission failures to 500.
An unknown or contradictory resolved Inbox is 400; an unavailable directory or
unusable credential is 503.
Failed admission schedules no work. Successful admission returns
`{"status": "accepted"}` and schedules the Host handler. Background handler
failures are logged and reported internally as `dispatch_failure`; they cannot
change an acknowledgment already sent.

Wappa does not provide an external webhook retry policy, dead-letter store,
delivery ledger, or duplicate suppression. Hosts that need payment-grade
reliability own idempotency and durable processing.

### Webhook Signature Verification

`HMACSignatureVerifier` verifies signed External Webhook Source requests. It is
used inside a processor's `parse_event()`; Wappa never calls it for you, because
only the processor knows which secret and header a source uses.

```python
from wappa import HMACSignatureVerifier

verifier = HMACSignatureVerifier(
    secret=settings.stripe_webhook_secret,
    header="Stripe-Signature",
    algorithm="sha256",   # any hashlib algorithm
    prefix="",            # e.g. "sha256=" for GitHub-style headers
    encoding="hex",       # or "base64"
)

verifier.verify(raw_body, request.headers)  # -> bool
verifier.verify_signature(raw_body, signature_string)  # -> bool
verifier.sign(raw_body)  # -> str
```

`verify()` returns `False` — it does not raise — for a missing header, a wrong
prefix, an undecodable signature, or a digest mismatch. Header lookup is
case-insensitive. Hex casing and base64 padding variants do not affect the
verdict. Misconfiguration (empty secret, unknown algorithm or encoding) raises
`ValueError` at construction. Providers that sign something other than the raw
body build that string themselves and pass it as the payload.

### External Event Registry

`ExternalEventRegistry` routes `ExternalEvent` instances to async handlers by
`(source, event_type)`. It is transport-free and Host Application-driven: Wappa
does not install it into the External Webhook Runtime.

```python
registry = ExternalEventRegistry()

@registry.on("mercadopago", "payment.approved")
async def credit_wallet(event: ExternalEvent) -> None: ...

class MyHandler(WappaEventHandler):
    async def process_external_event(self, event):
        report = await registry.dispatch(event)
```

- `register(source, event_type, handler)` / `on(source, event_type="*")`
- `handlers_for(source, event_type) -> list[handler]`
- `dispatch(event) -> DispatchReport(matched, succeeded, errors, failed)`

Matching runs in three tiers, most specific first, and within a tier in
registration order: exact (`payment.approved`), prefix (`payment.*`, matching
any depth below it), then any (`*`). A handler matched by several tiers runs
once per event. Handlers must be async; sync callables are rejected at
registration.

Dispatch is best-effort per handler: a raising handler is logged and the
remaining handlers still run. `DispatchReport.errors` carries
`(handler_name, exception)` for callers that need to react.

## Server-Sent Events

`publish_sse_event()` is the public best-effort SSE publisher. Host
applications may publish built-in event types or custom event types registered
with `register_sse_event_type(event_type)`.

Built-in event types are:

- `incoming_message`
- `outgoing_api_message`
- `outgoing_bot_message`
- `status_change`
- `webhook_error`

Unknown event types are rejected by `publish_sse_event()`: the function returns
`0`, logs a warning, and does not deliver an envelope. Hub publish failures are
also best-effort: the function logs and returns `0`.

`SSEHub` is Wappa's public structural hub contract. `SSEEventsPlugin()` creates
the in-memory `SSEEventHub` by default. A Host may inject one compatible hub or
one factory (supplying both is a configuration error); routes, handlers,
Messenger lifecycle middleware, shutdown, and health use that same instance.

```python
from wappa.core.plugins import SSEEventsPlugin

plugin = SSEEventsPlugin(
    event_hub_factory=lambda queue_size: BrokeredSSEHub(queue_size=queue_size)
)
```

`await hub.publish(...)` creates an `SSEEventEnvelope` and returns
`SSEPublishResult(envelope, delivery)`. A broker adapter receives remote work
through `hub.deliver_envelope(envelope)`: that operation does local fan-out,
preserves `event_id`, and never publishes externally. `publish_sse_event()`
remains the public best-effort wrapper for validated Wappa event types and
returns the local delivery count.

`SSEHub.snapshot_metrics()` returns typed `SSEHubMetrics`; `/api/sse/status`
and plugin health serialize the same snapshot. Counters include active and
filtered subscriptions, published and locally delivered events, dropped events,
overflow closures, and shutdown closures. They are process-local and not a
durable ledger.

`SSEHub.close_reason(item)` is a required member of the contract (since 0.33.0). The SSE route calls it on every queued item; a non-`None` reason (`backpressure_gap`, `shutdown`, or a custom hub's own reason) ends the stream. A custom hub owns its close-signal representation and must recognize it here; a decorator delegates to its local hub. A hub without `close_reason` no longer satisfies `SSEHub`, and `SSEEventsPlugin` rejects it with `TypeError`.

SSE is non-durable. The default hub closes a Subscription on its first full
queue with a private `backpressure_gap` control rather than silently dropping
an event and keeping the stream open. The browser reconnects and the Host
reconciles durable state; Wappa provides neither replay nor reconciliation.

SSE Event Envelopes preserve the active SSE identity scope:

- `inbox_id`
- `user_id`
- `bsuid`
- `phone_number`
- `platform`
- `metadata`

Inbound webhook scopes read `bsuid` and `phone_number` from the evidence fields the adapter filled (`UserBase.bsuid`/`phone_number`, `CallWebhook.bsuid`/`phone_number`, `StatusWebhook.recipient_bsuid`/`recipient_phone_id`), never from the Platform or an identifier's shape; Instagram events carry `None` for both. `sse_event_scope(...)` requires `platform` (no `"whatsapp"` default since 0.34).

An SSE Inbox filter must also supply `platform`; Wappa rejects an unqualified
native Inbox filter. PubSub channel namespaces are derived from `InboxRef` for
the same reason.

## Rate Limiting

Wappa provides local per-process route-level rate limiting through:

- `RateLimitProfile(name, limit, window_seconds, key_by="client_ip")`
- `RateLimitPlugin(profiles=[...])`
- `rate_limit(profile_name)`

Supported `key_by` values are:

- `client_ip`
- `inbox_id`
- `inbox_id_and_client_ip`

`RateLimitPlugin` stores an in-memory limiter on
`app.state.wappa_rate_limiter` during startup. Routes opt in explicitly with
FastAPI dependencies, for example:

```python
from fastapi import Depends
from wappa.core.plugins import rate_limit

@router.post(
    "/webhook/inboxes/whatsapp",
    dependencies=[Depends(rate_limit("webhook"))],
)
async def webhook():
    ...
```

Inbox-aware limits read `X-Wappa-Inbox-ID` or an established Inbox Execution
Context; a URL segment is never an Inbox routing authority. Payload-routed
callbacks should use `client_ip` at HTTP admission or a Host policy after
authentication and parsing.

When the limit is exceeded, Wappa raises HTTP 429 with a `Retry-After` header.
An unknown profile or missing `RateLimitPlugin` is a configuration error, not
fail-open behavior. Wappa does not provide Redis-backed or distributed rate
limiting in this contract.

## Request Correlation

`RequestIdMiddleware` is installed by `WappaCorePlugin` as Wappa's outermost
middleware, so every application built through `Wappa` or a builder that adds
the core plugin gets correlation IDs with no extra configuration.

Behavior:

- Reads the inbound `X-Request-ID` header when it is non-empty, printable, and
  at most 128 characters; otherwise generates a UUID4 hex value.
- Publishes the ID to `request.state.request_id` and to the request-scoped
  logging context for the duration of the request.
- Echoes the ID on the response under the same header.
- Adds `request_id` to `WappaJSONFormatter` records while a request scope is
  active, and omits the field outside one (background work, expiry handlers,
  cron jobs).
- Clears the context once the response is produced, including when the handler
  raises.

Configuration is per-instance, for hosts that install it themselves:

- `RequestIdMiddleware(app, header_name="X-Request-ID", trust_inbound=True)`
- `trust_inbound=False` always generates a fresh ID, for untrusted edges.

Public imports:

- `from wappa.api.middleware import RequestIdMiddleware, DEFAULT_REQUEST_ID_HEADER`
- `from wappa.core.logging import get_current_request_id, set_request_context`

`set_request_context(inbox_id=None, user_id=None, request_id=None)` remains the
way to populate context outside HTTP (background work, tests).

## Resilience

`wappa.resilience` provides transport-neutral retry helpers for transient
integration failures. They are reusable by transport adapters, webhook
processors, credential stores, and external platform clients.

```python
from wappa.resilience import RetryPolicy, retry_transient_http

@retry_transient_http(policy=RetryPolicy(attempts=5))
async def fetch_profile(client, url):
    response = await client.get(url)
    response.raise_for_status()
    return response.json()
```

Public surface:

- `RetryPolicy(attempts=3, initial_delay=0.2, max_delay=5.0, multiplier=2.0, jitter=0.25)`
  and `DEFAULT_RETRY_POLICY`
- `retry_async(policy=..., retry_on=predicate, operation=None)`
- `retry_transient_http(policy=..., operation=None)`
- `retry_transient_db(policy=..., operation=None)`
- `is_transient_http_error(error)`, `is_transient_db_error(error)`
- `TRANSIENT_HTTP_STATUS_CODES`, `TRANSIENT_DB_ERROR_TYPES`,
  `TRANSIENT_DB_ERROR_PATTERNS`

Classification contract:

- HTTP transient: timeouts, connect/read/write failures, remote protocol
  errors, pool timeouts, DNS and TLS failures, and responses with status
  `408`, `425`, `429`, `500`, `502`, `503`, `504`. Status retries require the
  wrapped function to raise `httpx.HTTPStatusError` (e.g. via
  `response.raise_for_status()`).
- HTTP non-transient: every other 4xx, and non-HTTP exceptions such as a
  payload `ValueError`.
- Database transient: connection refused/reset, dropped server connections,
  DNS failures, and OS-level socket errors.
- Database non-transient: SQLAlchemy pool checkout timeouts (the pool is
  already drained), integrity violations, and query errors.

`asyncio.CancelledError` is never retried. The final attempt's exception
propagates unchanged, so callers keep the original error and traceback. Only
async callables are supported. Retries are per-process and in-memory; Wappa
does not provide a distributed retry or circuit-breaker contract.

## Messenger

`IMessenger` is Wappa's public outbound message interface. Host applications use it to send text, media, interactive and specialized messages through an Inbox; WhatsApp Templates go through the `ITemplateMessaging` capability (`messenger.require_capability(ITemplateMessaging)`).

**Stable surface:**

- `from wappa.domain.interfaces import IMessenger`
- All `send_*` methods and `mark_as_read` on the interface, one method per action across Platforms (ADR-0016)
- `capability(kind)` / `require_capability(kind)` for `IMediaLibrary`, `ITemplateMessaging` and the Instagram-only capabilities
- `MessageResult` as the uniform return type

`MessageResult.recipient_phone` is nullable normalized phone evidence. Factories
and direct model construction return `None` for a phone that exactly matches the
complete numeric suffix of a valid BSUID, Parent BSUID, or BSUID-valued resolved
`recipient` on the same result. Comparison tolerates outer whitespace and an
optional leading `+` on the phone. Alphanumeric suffixes, invalid identifiers,
and phones without corroborating BSUID evidence do not establish an echo;
distinct phone values are preserved verbatim.

The canonical recipient, BSUID fields, username, Inbox, Message ID, and send
outcome are preserved. `ResponseContact.wa_id` and the Cloud API body in
`platform_response` remain raw provider evidence. `TemplateTransportResult.returned_phone_number` projects
the sanitized phone and remains nullable; an accepted Template with a Message ID
remains `accepted` when its phone becomes unknown. This adds no discovery call,
address rewrite, or retry. Host Applications still own durable identity policy.

`IMessenger.send_contact_request(body, target, reply_to_message_id=None)` is the contact-information request. WhatsApp implements it with Meta's `request_contact_info` interactive payload; Instagram raises `UnsupportedOperationError`, so Hosts gate on `supported_operations`.

**Design commitment:**

- The interface stays as a single seam until the split threshold documented in `wappa/messaging/ARCHITECTURE.md` is met.
- If a split is justified in the future, it will be a clean breaking change with no compatibility aliases.
- Internal handler composition (per message family) is not part of the public contract.
- WhatsApp payload construction (`wappa.messaging.whatsapp.payload_builders`) is adapter-private. `WhatsAppMessenger` builds its own payload builders; it takes no factory arguments.

## Inbox-scoped Template transport

Host Applications that send Templates use the shallow `wappa.messaging`
contract instead of constructing Wappa clients, handlers, factories, sessions,
or Messenger Pipelines:

- `OutboundRuntime.from_app(app).templates(inbox_id)`
- `InboxTemplateTransport.send(request)`
- `TextTemplateTransportRequest`, `MediaTemplateTransportRequest`,
  `LocationTemplateTransportRequest`
- `TemplateTransportMediaHeader`, `TemplateTransportLocationHeader`,
  `TemplateTransportRouting`, `TemplateTransportParameter`, `TemplateCategory`,
  `TemplateMediaType`, `TemplateAuthenticationMethod`
- `PhoneNumberTemplateRecipient`, `BsuidTemplateRecipient`, `TemplateAddressKind`
- `TemplateRoutingPolicy`, `TemplateEndpoint`, `TemplateRoutingReason`
- `TemplateTransportOutcome`, `TemplateTransportResult`

Requests reject unknown fields and contain only platform-facing values. Agent,
Campaign, authority, attribution, Conversation, Reply State, state-cache,
persistence, and arbitrary Host metadata do not cross this boundary.

Every request contains exactly one discriminated Delivery Address. Phone
numbers are normalized and sent in Meta's `to` field. Regular and parent
BSUIDs are normalized and sent in Meta's `recipient` field. Usernames are not
accepted as outbound addresses.

Authentication Templates require `authentication_method` — `copy_code`,
`one_tap`, or `zero_tap` — and that method changes the outgoing request. Wappa
emits the OTP button component Meta requires beside the body:

```json
"components": [
  {"type": "body", "parameters": [{"type": "text", "text": "ABC234"}]},
  {"type": "button", "sub_type": "url", "index": "0",
   "parameters": [{"type": "text", "text": "ABC234"}]}
]
```

The button's URL ends in `&code=otp{{1}}`, so its parameter is a real
placeholder, not a duplicate to optimise away: the body is what the person
reads and the button is what "Copy code" writes to their clipboard. Wappa fills
both from the request's single body parameter, so the two values cannot drift.
`index` is serialised as a string, and `authentication_button_index` expresses a
button that is not first.

Meta rewrites an `OTP` button to a `URL` button at template creation, so all
three methods send the same component; they differ only in how the recipient's
device consumes the code. The one-tap handshake and `supported_apps` metadata
belong to template creation and to the Host Application's mobile app, not to
this send.

An Authentication Template request is rejected locally when it names a BSUID
address, carries a media or location header, carries anything other than
exactly one body parameter, or binds that parameter by name — each is a shape
Meta will not deliver. `request_digest` covers the code, so a resend with a
fresh PIN is never collapsed into a replay of the previous one.

The approved template is the only authority on which method it uses, so
`TemplateInfo.authentication_method` and `TemplateButton.authentication_method`
resolve it from a template read back through Wappa. Meta rewrites the `OTP`
button to `type: "URL"` and commonly returns `otp_type: null` beside it, leaving
the method readable only in the generated button URL
(`.../otp/code/?otp_type=COPY_CODE&...`); both properties read the flat field
first and fall back to that URL. An unmarked button resolves to `None` rather
than to a guess.

Category-default routing sends marketing Templates to `/marketing_messages`
and utility/authentication Templates to `/messages`. The only fallback is the
explicit `cloud_messages_fallback` policy for marketing. Wappa never retries a
rejection or ambiguous call through the other endpoint. Results report the
selected endpoint and routing reason.

Outcomes mean exactly:

- `accepted`: the platform accepted the call and returned a Message ID;
- `rejected`: a request or platform response proves the send was not accepted;
- `transport_unavailable`: Wappa could not start a platform call, including drain;
- `indeterminate`: Wappa cannot prove whether the platform accepted the call.

Acceptance does not claim delivery, read, reply, or Host Application commit.
Callers must not automatically resend an `indeterminate` result.

Wappa's standalone Template HTTP adapter is disabled by default. A standalone
host opts in with `Wappa(include_template_transport_api=True)`. Embedding hosts
receive no raw Template mutation routes unless they make that choice.

## HTTP route composition

Wappa's WhatsApp surface is grouped by **what an unauthenticated caller could
do**, not by which module a route lives in. See
[ADR-0007](adr/0007-embedded-outbound-route-control.md) and
[ADR-0009](adr/0009-route-capability-groups.md).

| Capability | `standalone` (default) | `embedded` |
| --- | --- | --- |
| Ordinary + interactive outbound sends | mounted | **omitted** |
| Template outbound sends | omitted | omitted |
| `DELETE /media/{id}` (destroys a platform asset) | mounted | **omitted** |
| `POST /media/upload` (creates a platform asset) | mounted | mounted |
| `/state-handlers/*` (any recipient's cached state) | mounted | **omitted** |
| Media download / info / limits | mounted | mounted |
| Health, limits, validation, Template info | mounted | mounted |
| `wappa.messaging` services | available | available |

```python
Wappa(route_profile="embedded")            # the whole group, one argument
Wappa(route_profile="embedded", include_media_upload_api=False)   # and close upload
```

Individual capabilities are also settable on their own and always win over the
profile: `include_outbound_transport_api`, `include_template_transport_api`,
`include_media_management_api`, `include_media_upload_api`,
`include_state_handler_api`. Each defaults to `None`, meaning "take it from the
profile".

**Ejecting sends implies the embedded profile.** Passing
`include_outbound_transport_api=False` without naming a profile also omits
media management and the state-handler API, because a host that owns its send
boundary owns the rest of the mutation surface too.

Under `embedded`, the only mounted route that reaches the platform or rewrites
stored state is `POST /media/upload`; one flag closes it. The
`/specialized/validate-*` routes are `POST` because they take a body, but they
perform no I/O and change nothing.

Route composition never gates sending. `IMessenger`, `OutboundRuntime`, and
`InboxTemplateTransport` behave identically under every profile; what a profile
removes is the *unauthenticated HTTP path* to them.

`create_messaging_router(profile=..., include_*=...)` is the underlying
composition function for hosts assembling routers directly; it mounts at
`/api/{platform}`.

**Upgrade note.** Standalone applications need no action. Hosts already passing
`include_outbound_transport_api=False` get the wider gating automatically and
should confirm they did not depend on Wappa serving `/state-handlers/*` or
`DELETE /media/{id}` over an unauthenticated route.

## Outbound payload classification

`classify_outbound_payload(payload)` names the transport family of any
validated Wappa outbound schema. It is pure, has no I/O, and reads nothing but
the payload's own shape.

- `OutboundClassification(family, subkind)` with `family` in `text`, `media`,
  `interactive`, `location`, `contact`, `template`, `read_receipt`
- `subkind` names the variant where a family has several: `image` / `video` /
  `audio` / `document` / `sticker`, `button` / `list` / `cta` /
  `location_request`, and `text_header` / `media_header` / `location_header`
- `is_template` — whether the payload is a Template envelope
- `message_type` — the label Wappa reports in outbound API events. Media and
  interactive sends report their variant (`"image"`, `"button"`); every
  Template reports `"template"`, because which header it carries does not
  change what kind of send it was.
- `UnsupportedOutboundPayloadError` for anything that is not an outbound send
  schema, including a base class that names no concrete transport

All three Template envelope variants classify as one `template` family and keep
their header as a subkind. A Host Application subclass of a concrete schema
classifies as the schema it extends.

**Classification is transport shape, not product authority.** A payload is a
Template because it is a Template envelope — never because of who is sending
it, which Conversation or Campaign it belongs to, or what metadata rides along.
Whether a given send is *permitted* is a Host Application question, and this
function is deliberately unable to answer it.

## Canonical Import Paths (SDK Surface)

Host applications should prefer these shallow imports over deep internal paths.
Internal module paths (`wappa.core.*`, `wappa.persistence.redis.redis_handler.*`) are implementation details and may change without notice.

### Top-level (`from wappa import ...`)

- `Wappa`, `WappaBuilder`, `WappaPlugin`, `WappaEventHandler`
- `ExternalEvent`, `CronEvent`, `ExpiryPlugin`, `expiry_registry`
- `IIdentityResolver`, `PassthroughIdentityResolver`, `IWebhookProcessor`
- `IExternalWebhookContextResolver`, `ResolvedExternalWebhookContext`
- `HMACSignatureVerifier`, `ExternalEventRegistry`, `DispatchReport`
- `CustomWebhook`, `WappaContext`
- `InboxRef`, `PlatformAccountRef`, `InboxRoutingMode`, `IInboxDirectorySource`, `InboxCredentialService`, `MetaApplicationConfig`

### SSE (`from wappa.sse import ...`)

- `publish_sse_event`, `publish_api_sse_event`
- `sse_event_scope`, `get_sse_context`, `classify_meta_identifier`
- `update_identity`, `update_metadata`, `flush_incoming_sse`, `derive_identifiers`
- `SSEHub`, `SSEEventHub`, `SSESubscription`, `SSEEventEnvelope`,
  `SSEDeliveryResult`, `SSEPublishResult`, `SSEHubMetrics`, `SSEEventType`,
  `register_sse_event_type`

### Messaging (`from wappa.messaging import ...`)

- `IMessenger`
- `MessengerMiddleware`, `MessengerPipeline`, `SendInvocation`, `SendNext`, `PRIORITY_CACHE`
- `classify_outbound_payload`, `OutboundClassification`, `OutboundTransportFamily`,
  `OutboundTransportSubkind`, `UnsupportedOutboundPayloadError`
- `OutboundRuntime`, `InboxTemplateTransport`
- `TextTemplateTransportRequest`, `MediaTemplateTransportRequest`, `LocationTemplateTransportRequest`
- `TemplateTransportMediaHeader`, `TemplateTransportLocationHeader`, `TemplateTransportRouting`
- `TemplateTransportParameter`, `TemplateCategory`, `TemplateMediaType`, `TemplateAuthenticationMethod`
- `PhoneNumberTemplateRecipient`, `BsuidTemplateRecipient`, `TemplateAddressKind`
- `TemplateRoutingPolicy`, `TemplateEndpoint`, `TemplateRoutingReason`
- `TemplateTransportOutcome`, `TemplateTransportResult`

`WhatsAppClient`, `WhatsAppMessenger`, their handlers, `MessengerFactory`, and
session lifecycle classes are implementation details. Host Applications do not
construct or import them.

### Persistence (`from wappa.persistence import ...`)

- `create_cache_factory`, `get_cache_factory`, `ICacheFactory`
- `SYSTEM_SCOPE`, `create_system_table_cache`, `validate_context_id`
- `TypedTableCache`, `VersionedTableCache`, `ITableCache`, `build_table_name`
- `TableRowTransition`, `TableTransitionResult`, `TypedRowTransition`
- `RedisCacheFactory`, `RedisClient`, `redis_ops`
- `IUserCache`, `IStateCache`, `IExpiryCache`, `ITableCache`

`TypedTableCache[T]` is a convenience wrapper over an existing `ITableCache`:

- `TypedTableCache(cache, table_name, model, default_ttl=None)`
- `get(pkid) -> T | None`
- `upsert(pkid, data, ttl=None) -> bool`
- `delete(pkid) -> int`
- `exists(pkid) -> bool`
- `update_field(pkid, field, value, ttl=None) -> bool`
- `create_if_absent(pkid, data, ttl=None) -> TypedRowTransition[T]`
- `replace_if(pkid, data, expected, ttl=None) -> TypedRowTransition[T]`

- `renew_ttl(pkid, ttl=None) -> bool`

Inbox scoping still comes from the `ICacheFactory` / `ITableCache` that creates
the underlying table cache.

#### Table Cache Scope (`context_id`)

Table Cache is the one cache family whose namespace is a general `context_id`:
the reserved System Scope (`SYSTEM_SCOPE == "__system__"`), a Host-defined
business scope (for example an Owner identifier), or an Inbox namespace
(`InboxRef.cache_namespace`). The scopes are siblings: nothing falls back or
cascades between them. `ICacheFactory.create_table_cache(context_id=None)`
defaults to the factory's Inbox namespace; `create_system_table_cache(cache_type)`
builds a System-Scope table on the configured backend. `RedisTable`,
`MemoryTable`, and `JSONTable` take `context_id` positionally or by keyword.
This is a naming change only: `context_id="123"` builds exactly the key that
`inbox_id="123"` built before, and no Redis data migration is needed. The old
`inbox_id=` / `inbox=` keywords raise `TypeError` at construction; there is no
alias. User, State, AI State, Expiry, PubSub, and SSE caches remain
Inbox-scoped and keep `inbox_id`.

#### Atomic row transitions

`create_if_absent` and `replace_if` each perform their condition and their
write as one backend operation. Redis does it in a single server-side script;
the memory and JSON backends do it under the lock that guards the namespace or
the cache file. No backend reads, decides, and writes as separate steps, so a
transition cannot be lost to an interleaved writer. The same two operations
exist on `ITableCache` (untyped rows) and on `VersionedTableCache[T]`.

`TableRowTransition` names the one thing a call proves:

- `created` — this call created the row; no other caller had it
- `replaced` — this call replaced the row, and `expected` still held
- `already_exists` — another caller created it first
- `condition_not_met` — the row exists but no longer matches `expected`
- `missing` — there is no row to replace

`written` is `True` for exactly `created` and `replaced`. On the two refusals
that have something to report, `row` carries the state the backend actually
holds — the winning row, or the row that moved on — so a caller does not need a
follow-up read whose answer could already be stale. `TypedTableCache` validates
that row against the configured model, exactly like every other read.

`expected` maps field names to scalar values; every listed field must be
present and equal. Values are compared through one canonical encoding, so
`Status.PENDING` and `"pending"` match the same stored row on every backend.
Containers are rejected: their encoded form depends on ordering, which no
backend guarantees. An empty `expected` is rejected — that is `upsert`.

A refused transition writes nothing and leaves the row's TTL untouched. A
successful one applies the call's `ttl`, or the wrapper's `default_ttl`, or the
backend default, in that order. Replacement is a whole-row write on every
backend: fields the new row omits are gone, not merged.

Wappa does not interpret the fields a caller conditions on. Status names,
revision counters, and owner identifiers are Host Application concepts; this
contract only guarantees that the comparison and the write cannot be separated.

#### Stored value round trip

Read a row through a Pydantic model and it round-trips losslessly on every
backend — that is what `TypedTableCache[T]` and the `models=` parameter are
for, and it is the supported path.

Untyped dict reads are best-effort. On Redis a top-level boolean is stored as
`"1"`/`"0"`, which an integer `1` and the string `"1"` also spell, so an
untyped read of any of the three returns `True`. This is a deliberate
compatibility contract, not a defect — Host Applications read these fields
directly from outside Wappa. [ADR-0008](adr/0008-redis-hash-boolean-encoding.md)
records the decision, the mitigation, and one hard rule: **never store `"1"` or
`"0"` as a string value**, because a `str` field will then reject the `True` it
reads back.

#### Enumeration and identifier safety

Bulk operations (`delete_table`, `list_pkids`, `get_all`, `find_by_field`,
`delete_all_by_pkid`, `list_handlers`, `delete_by_handler_prefix`,
`delete_all_by_identifier`) match the identifiers you gave them literally.
An `inbox_id`, `cache_space`, table name, `pkid`, `user_id`, handler name, or
trigger identifier containing `*`, `?`, `[`, `]`, or `\` is matched as those
characters, not as pattern syntax. `:` is still folded to `_` inside a segment,
as it always was.

`IExpiryCache` has no `delete_all_for_user()`. A trigger key carries an action
and an identifier, never a user, so the interface cannot know which triggers a
user caused. Callers that use the user id as the trigger identifier say so:
`delete_all_by_identifier(user_id)`. The identically named methods on
`IStateCache` and `IAIStateCache` remain — their keys really are user-scoped.

`cache_space` is an optional host-owned namespace segment folded into the table
name as `"{cache_space}:{table_name}"`. Wappa never assigns one; omitting it
leaves key shapes unchanged. `build_table_name(table_name, cache_space=None)` is
the public composition helper. Both segments must be non-empty and must not
contain `:` or `@`.

`VersionedTableCache[T]` adds bump-to-invalidate semantics on top of the same
`ITableCache`:

- `VersionedTableCache(cache, table_name, model, default_ttl, cache_space=None)`
- the same row API as `TypedTableCache` (`get`, `upsert`, `delete`, `exists`,
  `update_field`, `renew_ttl`)
- `current_version() -> int` (starts at `1`)
- `bump_version() -> int` — invalidates every row in one operation
- `current_table_name() -> str` — e.g. `"crm:agents@v2"`

Rows live under a generation-suffixed table, so a bump makes every row
unreachable without enumerating keys, and is immediately visible to other
processes sharing the backend. Generations are per logical table and per cache
space: bumping one table does not affect its neighbours. `default_ttl` is
required and must be positive — orphaned generations are reclaimed only by TTL.
The generation counter is stored with its own longer TTL, refreshed on each
bump, so it always outlives the rows a bump orphans. Each operation reads the
counter first, costing one extra cache read.

### Webhooks (`from wappa.webhooks import ...`)

- `InboundMessageWebhook`, `StatusWebhook`, `ErrorWebhook`, `SystemWebhook`, `CustomWebhook`
- `CallWebhook`
- `BaseMessage`, `InboxBase`, `SystemEventDetail`
- `WhatsAppWebhook`, `WhatsAppMetadata`, `PlatformType`, `SystemEventType`

`SystemEventType` members: `NUMBER_CHANGE`, `USER_ID_CHANGE`, `MARKETING_PREFERENCE`,
and the account-scoped coexistence events `ACCOUNT_OFFBOARDED`, `ACCOUNT_RECONNECTED`.
Account-scoped events populate `SystemEventDetail.waba_id` (and `phone_number_id` /
`reason` where applicable) and dispatch with `SystemWebhook.user is None` — they target a
Platform Account (WABA), not a User. Consumers handle them in `process_system_webhook`.

`USER_ACTION` covers Meta's `user_actions` payload — user interaction events such as marketing message link clicks, delivered on the `messages` field with no `messages` and no `contacts`. It populates `SystemEventDetail.action_type` (Meta's action name, e.g. `marketing_messages_link_click`) and `SystemEventDetail.user_action` (the full action entry serialized, including any action-specific `<action_type>_data` object). Like account-scoped events it dispatches with `SystemWebhook.user is None` — the payload carries no user identity. Action entries validate permissively: an `action_type` Wappa has not seen keeps its extra keys and still dispatches, rather than failing the delivery. Unknown keys elsewhere in the change `value` remain strict contract drift.

### Domain Interfaces (`from wappa.domain.interfaces import ...`)

- `IMessenger`, `IMediaHandler`, `ICacheFactory`
- `IExpiryCache`, `IStateCache`, `ITableCache`, `IUserCache`
- `IIdentityResolver`, `PassthroughIdentityResolver`

### Inbox identity and directory (`from wappa.domain.inbox import ...`)

- `InboxRef`, `PlatformAccountRef`, `InboxRoutingMode`
- `IInboxDirectorySource`, `InboxCredentialService`, `InboxDirectory`
- `RECORD_TYPES` (`wappa.domain.inbox.credentials`): each Platform's `(active, inactive)` record classes; `InboxCredentialService` picks record classes from it and rejects a Platform without an entry with `ValueError`. `wappa.domain.inbox.services.WHATSAPP_ACCESS_TOKEN_FIELD` was removed in 0.34; the envelope binding field name stays `access_token`, so stored records decrypt unchanged
- `EncryptedSecretEnvelope`, `InboxCredentialRecord`, `InboxCredentialStatus`, `WhatsAppActiveInboxCredentialRecord`, `WhatsAppInactiveInboxCredentialRecord`, `PlatformAccountActiveIndexRecord`, `PlatformAccountEmptyIndexRecord`, `parse_inbox_credential_record`, `dump_record_for_storage`
- `InboxDirectoryError`, `InboxConfigurationError`, `InboxNotFoundError`, `InboxMembershipError`, `InboxDirectoryUnavailableError`, `InboxCredentialIntegrityError`, `InboxMutationConflictError`
- `MetaApplicationConfig` (`from wappa import ...` or `wappa.core.config.meta_application`), `CredentialCodec` / `SecretBinding` (`from wappa.core.security import ...`), `InboxDirectoryTable` (`wappa.persistence.inbox_directory`)
- `INBOX_ID_HEADER`, `InboxExecutionContext`, `get_inbox_execution_context` (`from wappa.api.dependencies import ...`); `SIGNATURE_HEADER`, `MetaCallbackAuthenticator`, `PlatformWebhooks`, `PayloadRoutingError`, `route_whatsapp_payload`, `RoutedWebhookDelivery` (`from wappa.core.inbound import ...`; `RoutedWebhookDelivery` and `PayloadRoutingError` live in `wappa.core.inbound.platform_webhooks`, no longer in `wappa.core.inbound.webhook_routing`); `PLATFORMS`, `PlatformEntry`, `build_platforms`, `BUILTIN_FIELDS` (`from wappa.platforms import ...`)

### API (`from wappa.api import ...`)

- `TemplateStateService`
- `convert_body_parameters`, `raise_for_failed_result`, `require_inbox_context`
- `dispatch_message_event`, `fire_api_event`, `resolve_event_user_id(recipient, explicit_user_id, fastapi_request, *, inbox_id)`

### Schemas (`from wappa.schemas import ...`)

- `looks_like_bsuid`

### Core Logging (`from wappa.core.logging import ...`)

- `get_logger`, `get_app_logger`, `setup_app_logging`
- `get_current_inbox_context`, `get_current_user_context`, `get_current_request_id`
- `set_request_context`, `clear_request_context`, `get_context_info`
- Log files: Wappa writes `wappa_YYYYMMDD.log` in `SYSTEM_LOG_DIR`, rolling over at midnight, with secrets redacted at write time. In DEV, the same folder also holds `current.log`, a symlink to the active file, and `dev.pid`, which has `key=value` lines for `serving_pid`, `parent_pid`, `parent_role`, `stop_pid`, `port`, `port_source`, `started_at` and `log_file`. `dev.pid` is removed on clean shutdown. Read logs through `current.log`, and never rewrite a live log in place.
- Payload capture: `SYSTEM_CAPTURE_PAYLOADS=true` with `SYSTEM_ENVIRONMENT=DEV` writes each authenticated webhook body, redacted, to `<SYSTEM_LOG_DIR>/payloads/<platform>/<kind>-<timestamp>.json`. Off by default. Under any other environment the flag is ignored, with a warning.

### Resilience (`from wappa.resilience import ...`)

- `RetryPolicy`, `DEFAULT_RETRY_POLICY`
- `retry_async`, `retry_transient_http`, `retry_transient_db`
- `is_transient_http_error`, `is_transient_db_error`
- `TRANSIENT_HTTP_STATUS_CODES`, `TRANSIENT_DB_ERROR_TYPES`, `TRANSIENT_DB_ERROR_PATTERNS`

### Middleware (`from wappa.api.middleware import ...`)

- `RequestIdMiddleware`, `DEFAULT_REQUEST_ID_HEADER`

### Core Expiry (`from wappa.core.expiry import ...`)

- `expiry_registry`, `run_expiry_listener`
- `get_app_context`, `AppContext`
- `create_expiry_messenger(inbox_ref)`, `create_expiry_cache_factory(inbox_ref, user_id)`, `parse_inbox_ref_from_expired_key`

### Migration Notes (v0.27.0)

See [`docs/migration/v0.27.0-multi-inbox.md`](migration/v0.27.0-multi-inbox.md) for the ordered legacy and explicit Host paths, the breaking public imports, the key rotation runbook, and the callback cutover.

### Migration Notes (v0.13.0)

- `from wappa.core.expiry.listener import get_fastapi_app` is removed. Use `from wappa.core.expiry import get_app_context` then `get_app_context().get_app()`.
- Deep paths under `wappa.schemas.whatsapp`, `wappa.schemas.factory`, and `wappa.schemas.core.base_*` are removed. Use `wappa.webhooks` instead.
