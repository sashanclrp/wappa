# Instagram capability matrix

Checked in per I02 ("one row per inbound variant and outbound operation"). Operations follow ADR-0016 (one Messenger method per action). Provider facts come from Meta's Instagram Platform docs (Graph v26.0, fetched 2026-11-03: webhooks examples/fields, messaging-api, quick-replies, button/generic template, sender-actions, private-replies, comment-moderation, ig-media, Unified Login authentication/get-started). Setup: Unified Login, `graph.facebook.com`, Business Integration System User token.

Status legend. **Impl**: implemented in the working tree. **Offline**: covered by automated tests (`tests/test_instagram_conversations.py`, `tests/test_instagram_connection.py`, `tests/test_instagram_text.py`, example `tests/`). **Live**: observed against the real account, with the date. "Pending" means no live evidence yet, not that it's known to fail.

## Inbound

| Native variant | Lane | Impl | Offline | Live |
| --- | --- | --- | --- | --- |
| `message.text` | message (text) | yes | yes | 2026-11-03 (text echo) |
| `message.attachments[type=image]` | message (image) | yes | yes | pending |
| `audio` / `video` / `file` | message (audio/video/document) | yes | yes | pending |
| `ig_post` / `ig_reel` / `reel` / `share` / `story` | message (share, `shared_media_id` if supplied) | yes | yes | pending |
| `story_mention` | message (story_mention) | yes | yes | pending |
| `reply_to.story` (story reply) / `reply_to.mid` | text with context | yes | yes | pending |
| `message.quick_reply` | message with selection (once) | yes | yes | pending |
| `message.referral` (attached) | `entry_referral` on message | yes | yes | pending (needs CTD ad / ig.me link) |
| `postback` | message with selection (`InstagramButtonReplyMessage`) | yes | yes | pending |
| `referral` (standalone) | system REFERRAL | yes | yes | pending |
| `message_edit` | message update (edited) | yes | yes | subscription accepted for Unified Login (2026-11-03 read-back lists it); delivery pending live edit (A-09) |
| `message.is_deleted` | message update (deleted) | yes | yes | pending |
| `read` | status READ | yes | yes | 2026-11-03 |
| echo / `is_self` | system MESSAGE_ECHO | yes | yes | 2026-11-03 |
| `reaction` | system UNSUPPORTED (excluded) | ignored by design | yes | n/a |
| `is_unsupported`, `ephemeral`, unknown types | system UNSUPPORTED | yes | yes | n/a |
| `changes: comments` (incl. replies via `parent_id`, ad media fields) | comment | yes | yes | pending (needs Advanced Access, Live app) |
| `changes: live_comments` | comment (Live source) | yes | yes | pending (needs a Live broadcast) |
| `changes: mentions` (media / comment) | mention | yes | yes | pending |
| registered extension field (e.g. `story_insights`) | CustomWebhook | yes | yes | pending |

## Outbound and capabilities

| Operation | Native call | Impl | Offline | Live |
| --- | --- | --- | --- | --- |
| `send_text` DM | `POST /{ig}/messages` `recipient.id` | yes | yes | 2026-11-03 |
| `send_text` PrivateReply | `recipient.comment_id` | yes | yes | pending |
| `send_image/audio/video/document` by URL | `attachment.payload.url` | yes | yes | pending |
| media by uploaded id (`send_image(stored.media_id, …)`) | `attachment.payload.attachment_id` | yes | yes | pending; `/image-upload` |
| caption on image/video/document | follow-up `send_text` after the media | yes | yes | pending |
| `send_location` | text: name, address, `📍` maps link | yes | yes | pending |
| `send_contact` | text contact card | yes | yes | pending |
| `send_sticker` | sent as an image (png/jpeg/gif; `.webp` rejected) | yes | yes | pending |
| media by local `Path` | `POST /{ig}/message_attachments` → `attachment_id`, then send | yes | yes | pending |
| `IMediaLibrary.upload(path, family)` | `POST /{ig}/message_attachments` with `is_reusable` → `attachment_id` | yes | yes | pending; **Meta documents the upload on the Page path only**, so confirm with `/image-upload` |
| `send_list_message` | `message.quick_replies` (rows flattened, ≤ 13) | yes | yes | pending |
| `send_button_message` | button template with postbacks; image header → one-card generic template | yes | yes | pending |
| `send_cta_message` | button template with one `web_url` | yes | yes | pending |
| `send_carousel` | `body` as text, then generic template | yes | yes | pending |
| `mark_as_read(…, typing, target)` | `sender_action` `mark_seen`, then `typing_on` | yes | yes | pending |
| `IMediaLibrary.download(media_id)` | CDN GET of the attachment URL, no auth, host-restricted | yes | yes | pending |
| `ICommentControls.reply_comment` | `POST /{comment}/replies` | yes | yes | pending |
| hide / unhide / delete comment | `POST /{c}?hide=`, `DELETE /{c}` | yes | yes | pending (not on Live) |
| enable / disable comments | `POST /{media}?comment_enabled=` | yes | yes | pending |
| `get_post` | `GET /{media}?fields=…children{…}` | yes | yes | **2026-11-03**: a Reel (REELS) and a 10-child CAROUSEL_ALBUM were read, including caption, permalink and counts |
| `list_comments` (pagination) | `GET /{media}/comments` | yes | yes | **2026-11-03**: 3 items with `has_more` |
| `get_post` not found | error `100/33` → `not_found` | yes | yes | **2026-11-03** |
| `get_comment`, `list_replies` | `GET /{c}`, `/{c}/replies` | yes | yes | pending |
| `get_mentioned_post/comment` | `/{ig}?fields=mentioned_media…` | yes | n/a | pending |
| attachment bytes | CDN GET, no auth, host-restricted | yes | yes | pending |
| `InboxCredentialAccess` | directory resolution | yes | yes | **2026-11-03**: the example's `app.setup` resolved the account through it |
| subscriptions read | `GET /{ig}/subscribed_apps` | yes | yes | **2026-11-03**: returned `messages, messaging_seen` |
| subscribe all fields | `POST /{ig}/subscribed_apps` | yes | yes | pending (`app.setup --subscribe`) |
| Unified Login begin/complete/discover/scopes | dialog + `oauth/access_token` + `assigned_instagram_accounts` + `debug_token` | yes | yes | pending (needs `IG_LOGIN_CONFIG_ID`, redirect URI registered) |

## Not implemented by decision

Cross-app handover/standby, heart sticker, `media_share` outbound, multi-image sends, HUMAN_AGENT tag, history sync, publishing and insights (extension-owned). `send_location_request` / `send_contact_request` raise `UnsupportedOperationError` (a text prompt cannot return the data).

Known gap, not a decision: reactions. `send_reaction(message_id, emoji, target)` is a missing core method on every Platform, and inbound Instagram reactions are dropped as `UNSUPPORTED_EVENT` ([backlog draft](../../../drafts/261105-mid-send-reaction-core-method.md)).
