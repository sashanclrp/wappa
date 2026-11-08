---
checked_on: 2026-11-03
checked_against: Meta Instagram Platform documentation, Graph v26.0; live evidence dated separately below
---

# Instagram reference

Current support and the evidence behind it. All rows below have an implementation; offline coverage is in `tests/test_instagram_conversations.py`, `tests/test_instagram_connection.py`, `tests/test_instagram_text.py` and `tests/test_unified_event_lanes.py`. A missing live observation does not mean an operation is unsupported. Evidence was reconciled on 2026-11-08 without new Meta calls.

The [public contract](../public-contract.md#instagram-conversations-contract) owns imports, event models, method signatures, value limits and results. The shipped [Instagram guide](../../wappa/cli/skills/wappa-apps/references/instagram.md) teaches Host usage; this reference owns the native inventory and verification qualifications behind that guide. [Setup observations](instagram-setup.md), [media results](media-formats.md), [rate limits](rate-limits.md) and the [live ledger](../verification/261103-instagram-conversations-live-tests.md) own their respective facts.

## Runtime boundaries

- The receiving professional account is the Inbox and Platform Account. IGSIDs are scoped to that Inbox; identity and cache state use `(InboxRef, user_id)`. A public comment author is not automatically an eligible DM destination.
- Quick replies and postbacks each produce one `InboundMessageWebhook` selection through `process_message`. Edits/deletions use `process_message_update`, external echoes use `process_outbound_echo`, public comments use `process_comment`, and public media/comment mentions use `process_mention`. Story mentions in DMs remain messages. Missing parent evidence means unknown, not top-level.
- Processors translate without I/O. Reads, downloads, comment controls and public `reply_comment` use Focused Capabilities; ordinary messaging uses the Messenger. The Host Application owns moderation policy, AI, durable history, Conversational Flows, assignment and takeover across immediate and delayed sends.
- One Meta Application Configuration authenticates exact POST bytes before parsing or Directory lookup. Separate `/webhook/inboxes/whatsapp` and `/webhook/inboxes/instagram` routes preserve Platform identity. Instagram uses explicit Inbox routing; webhooks never enroll accounts. See [ADR-0022](../adr/0022-inbox-identity-and-directory.md) and [ADR-0023](../adr/0023-inbound-webhooks.md).
- Unified Login uses `graph.facebook.com` and Business Integration System User tokens. `IInboxConnector` handles begin/complete/activate/disconnect; the Host owns authenticated connection intent, durable commit and Directory refresh. Trusted extensions resolve current credentials through `InboxCredentialAccess` per operation and own their extra clients. See [ADR-0026](../adr/0026-inbox-connection.md).
- Registered extension fields use the same authenticated, qualified, whole-batch admission. Built-in collisions fail; registration neither subscribes an account nor grants permissions. Publishing and insights stay with the Host or extensions.

Why, 2026-11-03: the [scope session](../design-sessions/261103-instagram-scope-and-extensions.md) separated Platform mechanisms from Host policy. The resulting current decisions live in ADRs, including [ADR-0025](../adr/0025-messenger-contract.md) and [ADR-0028](../adr/0028-whatsapp-first.md); the original implementation sequence is in git history.

## Native subscription fields

App-level selection and account-level `subscribed_apps` are separate. The live account read-back on 2026-11-03 included `messages`, `messaging_postbacks`, `messaging_seen`, `messaging_referral`, `comments`, `live_comments`, `mentions` and `message_edit`. Subscription success alone proves no delivery. `message_edit` remains an explicitly unverified subscription field in `wappa/connections/instagram.py`, tried separately because Meta's Unified Login field table and examples disagree; edit delivery was observed on 2026-11-05.

`message_reactions` is the subscription-field spelling; `reaction` is the event object. `message_echoes` in Meta material is not proof of a separate required subscription: the observed echoes arrived through `messages`. Extra fields such as `story_insights`, `messaging_optins`, `messaging_policy_enforcement` and `response_feedback` require extension-specific permissions and schemas. `messaging_handover` and `standby` have no built-in cross-app control implementation. Preserve `message.admin_text` / `message.handoff_reason` as control evidence when applicable; their availability in Unified Login is unverified since 2026-11-03.

## Inbound

| Native variant | Lane | Live evidence |
| --- | --- | --- |
| `message.text` | message (text) | 2026-11-03 (text echo) |
| `message.attachments[type=image]` | message (image) | 2026-11-05: inbound photo downloaded and echoed |
| `audio` / `video` / `file` | message (audio/video/document) | 2026-11-05: audio/video downloaded and echoed; no inbound PDF observation recorded |
| `ig_post` / `ig_reel` / `reel` / `share` / `story` | message (share, `shared_media_id` if supplied) | no recorded observation |
| `story_mention` | message (story_mention) | no recorded observation |
| `reply_to.story` (story reply) / `reply_to.mid` | text with context | no recorded observation |
| `message.quick_reply` | message with selection (once) | 2026-11-05: form service selection |
| `message.referral` (attached) | `entry_referral` on message | no recorded observation; needs CTD ad / ig.me link |
| `postback` | message with selection (`InstagramButtonReplyMessage`) | 2026-11-05: buttons, carousel and form confirmation |
| `referral` (standalone) | system REFERRAL | no recorded observation |
| `message_edit` | message update (edited) | 2026-11-05: MessageUpdateWebhook observed |
| `message.is_deleted` | message update (deleted) | no recorded observation |
| `read` | status READ | 2026-11-03 |
| echo / `is_self` | OutboundEchoWebhook | 2026-11-03 |
| `reaction` | InboundMessageWebhook with BaseReactionMessage | 2026-11-05: react and unreact |
| `is_unsupported`, `ephemeral`, unknown types | system UNSUPPORTED | n/a |
| `changes: comments` (incl. replies via `parent_id`, ad media fields) | comment | 2026-11-05: regular comments and own-reply loop filter; ad variants not separately verified |
| `changes: live_comments` | comment (Live source) | no recorded observation; needs a Live broadcast |
| `changes: mentions` (media / comment) | mention | 2026-11-05: comment mention; no media mention observation recorded |
| registered extension field (e.g. `story_insights`) | CustomWebhook | no recorded observation |

## Outbound and capabilities

| Operation | Native call | Live evidence |
| --- | --- | --- |
| `send_text` DM | `POST /{ig}/messages` `recipient.id` | 2026-11-03 |
| `send_text` PrivateReply | `recipient.comment_id` | 2026-11-05: accepted and echo received; follow-up DM not separately established in the record |
| `send_image/audio/video/document` by URL | `attachment.payload.url` | 2026-11-05: accepted with echoes/read evidence in Block 4 |
| media by uploaded id (`send_image(stored.media_id, …)`) | `attachment.payload.attachment_id` | 2026-11-05: /image-upload accepted |
| caption on image/video/document | follow-up `send_text` after the media | no recorded observation |
| `send_location` | text: name, address, `📍` maps link | 2026-11-05: accepted |
| `send_contact` | text contact card | 2026-11-05: accepted |
| `send_sticker` | sent as an image (png/jpeg/gif preferred, else a WebP URL; WebP upload fails with HTTP 500; animated WebP shows one frame) | 2026-11-05: PNG rendition accepted; 2026-11-06: static WebP renders by URL, its upload answers HTTP 500, animated WebP shows its first frame |
| media by local `Path` | `POST /{ig}/message_attachments` → `attachment_id`, then send | 2026-11-06: format matrix exercised file uploads; see media results |
| `IMediaLibrary.upload(path, family)` | `POST /{ig}/message_attachments` with `is_reusable` → `attachment_id` | 2026-11-05: /image-upload accepted |
| `send_list_message` | `message.quick_replies` (rows flattened; Meta native cap 13, Wappa shared list cap 10) | 2026-11-05: quick replies and form selections |
| `send_button_message` | button template with postbacks; media header sent as a separate attachment | 2026-11-05: accepted and postbacks observed |
| `send_cta_message` | button template with one `web_url` | 2026-11-05: accepted |
| `send_carousel` | `body` as text, then generic template | 2026-11-05: accepted and Choose tap observed |
| `mark_as_read(…, typing, target)` | `sender_action` `mark_seen`, then `typing_on` | 2026-11-05: /read accepted |
| `IMediaLibrary.download(media_id)` | CDN GET of the attachment URL, no auth, host-restricted | 2026-11-05: photo, voice and video downloaded and echoed |
| `ICommentControls.reply_comment` | `POST /{comment}/replies` | 2026-11-05: accepted; own comment ignored |
| hide / unhide / delete comment | `POST /{c}?hide=`, `DELETE /{c}` | 2026-11-06: hide/unhide/delete accepted on regular comments; Live unverified |
| enable / disable comments | `POST /{media}?comment_enabled=` | 2026-11-06: disable accepted; enable through Wappa unverified |
| `get_post` | `GET /{media}?fields=…children{…}` | **2026-11-03**: a Reel (REELS) and a 10-child CAROUSEL_ALBUM were read, including caption, permalink and counts |
| `list_comments` (pagination) | `GET /{media}/comments` | **2026-11-03**: 3 items with `has_more` |
| `get_post` not found | error `100/33` → `not_found` | **2026-11-03** |
| `get_comment`, `list_replies` | `GET /{c}`, `/{c}/replies` | no recorded observation |
| `get_mentioned_post/comment` | `/{ig}?fields=mentioned_media…` | 2026-11-05: mentioned comment read; no mentioned-post observation recorded |
| `InboxCredentialAccess` | directory resolution | **2026-11-03**: the example's `app.setup` resolved the account through it |
| `resolve_platform_user_profile` | `GET /{igsid}?fields=name,username,profile_pic`, merged over webhook evidence | `/whoami` accepted on 2026-11-05/06; exact returned profile fields not separately recorded |
| `IConversationHistoryReader.read_history` | `GET /{ig}/conversations`, then `GET /{conversation}/messages` | 2026-11-08: raw diagnostic lookup matched webhook and history IDs; public reader call not independently live-certified |
| subscriptions read | `GET /{ig}/subscribed_apps` | 2026-11-05: all eight fields on multiple connected Inboxes |
| subscribe all fields | `POST /{ig}/subscribed_apps` | 2026-11-05: subscription accepted and read back |
| Unified Login begin/complete/discover/scopes | dialog + `oauth/access_token` + `assigned_instagram_accounts` + `debug_token` | 2026-11-05: core Gate B passed; Creator connection user-reported 2026-11-08 |


## Private replies and content access

`PrivateReply` addresses `recipient.comment_id` on `POST /{ig}/messages`. Meta permits one private reply per triggering comment, within seven days on posts/Reels or during the Live broadcast. Follow-up requires the recipient to respond, then the private-reply guide gives a 24-hour response window. Other entry points, including eligible Click-to-Direct interactions, have action-specific rules; a public post or mention grants no unrestricted DM access. Wappa accepts text only for PrivateReply, capped at 1000 UTF-8 bytes and without quoting; it cannot split that one reply. [Meta private replies](https://developers.facebook.com/documentation/instagram-platform/private-replies).

Shares retain URLs and available `shared_media_id` evidence. A URL-only share remains processable; it is not a complete Post or proof the owned-post reader can resolve it. Post/comment reads can fail through permissions, deletion, expiry or inaccessible content. Attachment downloads use host-restricted CDN requests without Meta credentials. `IMediaLibrary.info` and `delete` raise `UnsupportedOperationError`.

Ad IDs, Creative IDs and Instagram media IDs are distinct. Meta creative fields `effective_instagram_media_id` and `effective_object_story_id` can identify referenced content; resolving that relationship is an extension operation, separate from reading a post. [Meta creative-read example](https://www.postman.com/meta/facebook-marketing-api/request/xowugm6/retrieving-adcreative-details-l-1).

## Exclusions and verification limits

Wappa has no outbound reactions, heart-sticker action, native `media_share`, multi-image send, standalone `typing_off`, ice-breaker/menu configuration, cross-app handover or HUMAN_AGENT tag. Inbound reactions, `resolve_platform_user_profile` and the Focused Capability `self.instagram.history` are implemented; older scope notes excluding them are superseded by the current contract. The Host owns durable history synchronization and storage; the history reader returns the shared `HistoryThread` shape. Native phone/email quick replies are disabled in the reviewed Meta guide; the Host can request text entry. Conversational Flows use selections and Host state rather than an Instagram equivalent of WhatsApp Flows.

Unverified since 2026-11-03: the reviewed HUMAN_AGENT guidance describes a separate seven-day human-agent window, but selected-flow approval and request fields are unverified. Wappa exposes no HUMAN_AGENT operation. The reported Creator Conversations API bootstrap prerequisite was not established as a universal rule; Creator connection passed by user report on 2026-11-08 without a recorded bootstrap determination.

The live ledger closes conversation checks on 2026-11-06 and Unified Login plus Host integration on 2026-11-08. It does not certify independent-customer App Review/Advanced Access or actual business-portfolio token revocation. Several individual variants in the tables still lack a recorded observation. Quoting is suppressed in 0.34.8 after tested webhook, outbound and matching history IDs failed with `100/2534002` on `graph.facebook.com/v26.0`; this does not establish failure on every account or Login mode. See the [quote evidence](../verification/261103-instagram-conversations-live-tests.md#history-id-gap-closed--2026-11-08-direct-read-only-live-lookup).

## Meta sources

Reviewed 2026-11-03; no external recheck during this consolidation. Dashboard and subscription observations use Unified Login; examples under Instagram Login do not establish equivalent authorization.

- [Fields and permissions](https://developers.facebook.com/documentation/instagram-platform/webhooks/fields), [notification examples](https://developers.facebook.com/documentation/instagram-platform/webhooks/examples), [changelog](https://developers.facebook.com/docs/instagram-platform/changelog).
- [Messaging](https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/messaging-api/), [quick replies](https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-instagram-login/messaging-api/quick-replies), [button messages](https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-instagram-login/messaging-api/button-template), [carousels](https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-instagram-login/messaging-api/generic-template), [sender actions](https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-instagram-login/messaging-api/sender-actions).
- [Comment controls and replies](https://developers.facebook.com/documentation/instagram-platform/comment-moderation), [Unified Login](https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-unified-login), [documentation index](https://developers.facebook.com/documentation/instagram-platform/llms.txt).
