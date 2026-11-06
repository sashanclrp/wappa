# Instagram conversation contract migration

Status: implemented in the working tree (unreleased). The DirectMessage
migration plus PrivateReply, public comment replies, new event lanes, Comment
Controls, content reads, trusted credential access, Instagram extension fields
and Unified Login primitives are shipped as code with offline tests; live
certification per capability is tracked in the series
[capability matrix](../backlog/in_progress/261103-instagram-conversations/references/capability-matrix.md).
Upgrading from 0.33? Start with the [0.33 → 0.34 checklist](v0.34.0-from-0.33.md). See the [PRD](../backlog/in_progress/261103-instagram-conversations/references/scope.md).

## Recipient-based Messenger calls

Before:

```python
await messenger.send_text(recipient=user_address, text="Hello")
```

Now:

```python
from wappa.messaging import DeliveryAddresses, DirectMessage

await messenger.send_text(
    target=DirectMessage(inbox_ref=inbox_ref, addresses=DeliveryAddresses.of(user_address)),
    text="Hello",
)
```

Use the trusted bound Inbox Reference and native Delivery Address, not a host
database User ID or username. Instagram uses its scoped address; WhatsApp
retains phone/BSUID address normalization. Targets are immutable and reject extra
fields; the adapter rejects a target for another Inbox before provider I/O.

The target migration applies to recipient-based Messenger text, image, audio,
video, document, sticker, interactive, contact, location, location-request and
WhatsApp Template sends, including any recipient-based specialized methods.
Consult each current signature; message-ID-only operations are not recipient
sends. This does not make these operations implemented for Instagram.

Update custom IMessenger implementations, wrappers, middleware, mocks, examples,
background sends and serialized send-event consumers. `SendInvocation` carries
the structured target; a derived recipient address is not an old calling
overload. Capability discovery is `supported_operations`; unsupported methods
raise `UnsupportedOperationError`. No `recipient=` alias, string target overload,
or silent Platform fallback is retained. Independently typed WhatsApp REST and
Template-transport requests remain documented adapter boundaries.

## Private and public comment replies

```python
from wappa.messaging import DeliveryAddresses, DirectMessage, ICommentControls, PrivateReply

# Ordinary DM versus comment-triggered private reply (text only, Instagram only).
await messenger.send_text("Hello", target=DirectMessage(inbox_ref=ref, addresses=DeliveryAddresses.of(igsid)))
await messenger.send_text("Hello", target=PrivateReply(comment_ref=webhook.comment_ref))

# Explicitly public reply through the comment capability; returns CommentResult (a Comment ID, never a DM ID).
controls = messenger.require_capability(ICommentControls)
result = await controls.reply_comment(webhook.comment_ref, "Thanks!")
```

`send_text` now accepts `MessageTarget = DirectMessage | PrivateReply`. Every other send rejects `PrivateReply` with `UnsupportedOperationError`, and WhatsApp rejects it too. `PrivateReply` cannot combine with `reply_to_message_id`. Middleware: `SendInvocation.target` is the union; `SendInvocation.recipient` is `target.address` (`comment:<id>` for a private reply, because the User is not yet addressable). `ICommentControls.reply_comment` bypasses message middleware (a public comment is not a private message).

## One Messenger method per action (ADR-0016)

Every action that exists on both Platforms has one `IMessenger` method; the Instagram adapter maps it onto native Instagram APIs. Host code does not branch on Platform name; check `messenger.supported_operations` once. See [ADR-0016](../adr/0016-one-messenger-method-per-action.md) and the mapping table in the [public contract](../public-contract.md).

| Action | Method | Instagram mapping |
| --- | --- | --- |
| acknowledge | `mark_as_read(message_id, target, *, typing=False)` | thread seen, then `typing_on` |
| up to 3 choices | `send_button_message(buttons: list[ReplyButton], target, body, header=None, footer=None)` | button template with postbacks; image header becomes a one-card generic template |
| up to 13 choices | `send_list_message(sections, target, body, button_text, ...)` | quick replies (rows flattened; section titles, descriptions and `button_text` dropped) |
| open a URL | `send_cta_message(...)` | button template with one `web_url` |
| 2–10 cards | `send_carousel(cards: Sequence[MessageCard], target, body)` | `body` as text, then a generic template |
| share a location | `send_location(latitude, longitude, target, name=None, address=None)` | text: name, address and a `📍` maps link |
| share a contact | `send_contact(contact, target)` | text card (name, organization, phones, emails, urls) |
| send a sticker | `send_sticker(source, target)` | sent as an image (png/jpeg/gif; `.webp` rejected before I/O) |
| send media with a caption | `send_image/video/document(..., caption=...)` | media, then the caption as a follow-up text; `filename`/`transcript` ignored |

`send_location_request` and `send_contact_request` stay WhatsApp-only: Instagram raises `UnsupportedOperationError` because a text prompt cannot return the data, so gate on `supported_operations`. Reactions have no send method yet (`send_reaction` is a recorded gap: [backlog draft](../backlog/drafts/261105-mid-send-reaction-core-method.md)).

`mark_as_read` gained an optional `target`. WhatsApp marks the message read (and now really sends the typing indicator); existing WhatsApp calls without `target` are unchanged. Custom `IMessenger` implementations and test fakes that override `mark_as_read` must accept the new keyword. Earlier unreleased drafts exposed `mark_seen`, `set_typing`, `send_quick_replies`, `send_buttons`, `send_card`, `IMessenger.reply_comment`, `QuickReply`, `PostbackButton`, `SenderActionResult`, `IMessenger.download_media` and an `InteractionWebhook`/`process_interaction` lane; none of them exist in the released contract.

## Media Library

Uploading and downloading media is the `IMediaLibrary` capability, not a Messenger method. It replaces the unreleased `IMessenger.download_media`.

```python
from pathlib import Path

from wappa.messaging import IMediaLibrary, MediaFamily

library = messenger.require_capability(IMediaLibrary)
stored = await library.upload(Path("menu.png"), MediaFamily.IMAGE)
if stored.success:
    await messenger.send_image(stored.media_id, target)

got = await library.download(webhook.message.media_id)  # inbound media, unchanged id
```

WhatsApp uses the Media API (Media ID). Instagram uploads to `message_attachments` with `is_reusable` (attachment_id) and downloads the attachment URL from the Meta CDN without credentials.

## WhatsApp Templates (breaking, released API)

`send_text_template`, `send_media_template` and `send_location_template` left `IMessenger` and `MessengerPipeline` for the WhatsApp-only `ITemplateMessaging` capability, with the same signatures: `await messenger.require_capability(ITemplateMessaging).send_text_template(...)`. Middleware still sees the same method names, and `OutboundRuntime` / `InboxTemplateTransport` callers change nothing. See `CHANGELOG.md`.

## New event lanes and hooks

| Hook (optional, default no-op) | Universal Model | Instagram source |
| --- | --- | --- |
| `process_message_update` | `MessageUpdateWebhook` (`edited`/`deleted`) | `message_edit`, `message.is_deleted` |
| `process_comment` | `IncomingCommentWebhook` | `comments`, `live_comments` |
| `process_mention` | `MentionWebhook` (`media`/`comment` subject) | `mentions` |
| `process_outbound_echo` | `OutboundEchoWebhook`: messages sent outside Wappa (typed); Wappa's own sends are filtered out | `message_echoes` |
| `process_history_sync` | `HistorySyncWebhook` (typed threads); Instagram reads the same shape through `IConversationHistoryReader` | WhatsApp Coexistence `history` |
| `process_inbox_connection` | `InboxConnectionWebhook` | `/webhook/inboxes/instagram/deauthorize`; WhatsApp `account_offboarded` / `account_reconnected` |

`UniversalWebhook` gains these six members. `IncomingCommentWebhook` and `MentionWebhook` are Instagram-only; the others come from both Platforms. WhatsApp Hosts move consumer edits/revokes to `process_message_update`, Coexistence echoes to `process_outbound_echo`, history to `process_history_sync` and account offboarding to `process_inbox_connection` (see `CHANGELOG.md`). Instagram reactions now reach `process_message` as `InstagramReactionMessage`. Exhaustive `match`/`isinstance`
code over the union must add cases. Behavior changes for existing Instagram
consumers:

- Deletions now reach `process_message_update` (previously `SystemWebhook`
  `UNSUPPORTED_EVENT`).
- Quick-reply selections and postback taps now reach `process_message` once, as `InstagramQuickReplyMessage` or `InstagramButtonReplyMessage` (`is_button_reply`); read the choice with `webhook.get_interactive_selection()`, exactly like WhatsApp `button_reply`/`list_reply`.
- Image/video/audio/file/share/story-mention attachments now reach
  `process_message` with typed messages (`MessageType.SHARE` and
  `MessageType.STORY_MENTION` are new enum members). Unknown attachment types,
  `is_unsupported` and unknown change fields stay
  `SystemWebhook(UNSUPPORTED_EVENT)`; standalone referrals are
  `SystemEventType.REFERRAL`.
- `InboundMessageWebhook.entry_referral` carries message-attached referral
  context.
- Instagram error codes are `code/subcode` strings (e.g. `10/2534022`).
- Instagram text limits are 1000 **UTF-8 bytes** and raise `ValueError` before
  I/O (previously a Pydantic `ValidationError` on 1000 characters).
- Media captions are sent as a follow-up text; `transcript` and `filename` are ignored (Instagram attachments carry none). `send_location`, `send_contact` and `send_sticker` are adapted instead of raising.

Comment handlers must distinguish source, placement and available parent
evidence (`parent_comment_ref is None` is *unknown*, not top-level); Live and
self-authored comments are delivered — use `webhook.is_own_comment` to avoid
reply loops.

## Focused capabilities

`IMessenger.capability(kind)` / `require_capability(kind)` return optional, Inbox-bound capabilities: `IMediaLibrary` (WhatsApp and Instagram, above), `ITemplateMessaging` (WhatsApp Templates), and for Instagram-only actions `ICommentControls` (`reply_comment`, hide/unhide/delete, enable/disable comments on media), `IConversationContentReader` (post, comment, comments/replies pages). Bounded, credential-free CDN downloads are `IMediaLibrary.download(media_id, max_bytes=...)`; the Instagram-only `IAttachmentMediaReader` capability was removed in 0.34. Custom `IMessenger` implementations inherit a `None` default; `MessengerPipeline` delegates to the raw Messenger.

## Trusted credential access (Symphonai migration)

Replace imports of Wappa's internal resolver with:

```python
from wappa.domain.inbox import InboxCredentialAccess

access = InboxCredentialAccess.from_app(wappa.asgi)
credential = await access.resolve(InboxRef(platform=PlatformType.INSTAGRAM, inbox_id=ig_id))
headers = credential.authorization_header()  # trusted backend adapter only
```

Authorize the caller first, resolve per operation (never cache), and keep the
value out of AI arguments, browsers, logs and durable plaintext. Adapt
`runtime_inbox` and its Directory Source to qualified Platform identities. For
Host-initiated sends (agents, delayed jobs, human takeover) use
`await OutboundRuntime.from_app(app).messenger(inbox_ref)`.

## Instagram extension fields

```python
app.register_webhook_field(
    "story_insights", parser=StoryInsight, handler=on_story_insight,
    platform=PlatformType.INSTAGRAM,
)
```

Built-in Instagram fields are reserved. `FieldHandlerRegistry` keys entries by
`(platform, field)`; `get(field, platform=...)` and `fields(platform=...)` take
the Platform (default WhatsApp), and `field in registry` keeps its WhatsApp
meaning. A parse failure rejects the whole authenticated batch before any
delivery is scheduled.

## Connecting accounts (Inbox Connector)

`wappa.connections` provides one contract for every Platform, `IInboxConnector` (ADR-0017), implemented by `InstagramConnector` (Unified Login) and `WhatsAppConnector` (Embedded Signup) on a shared Meta Business Login core: `begin` (one-use state bound to the Host operator), `complete` (code exchange, discovery, scope readiness per `DiscoveredInbox`), `activate` (webhook subscription plus the Wappa-encrypted record) and `disconnect`. The Host owns routes, intent storage, persistence commit and `refresh_inbox` afterwards. The earlier unreleased `InstagramUnifiedLogin`, `UnifiedLoginConfig` and `build_instagram_record` are replaced by this contract.
