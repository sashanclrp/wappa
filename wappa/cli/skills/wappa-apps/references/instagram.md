---
checked_on: 2026-11-08
checked_against: Meta Instagram quick-replies, button-template, generic-template, private-replies and comment-moderation pages (Graph v26.0) and Wappa's tests/test_instagram_conversations.py and ADR-0025
revision: 5
---

# Instagram-only features

## Contents

- What Instagram adds to a message
- Comments and mentions
- Replies: public versus private
- Comment Controls
- Post and comment reads

## What Instagram adds to a message

Instagram messages arrive in `process_message` as typed classes from `wappa.webhooks.instagram`:

| `webhook.message.message_type` | Class | Useful fields |
| --- | --- | --- |
| `text` | `InstagramTextMessage` | `text`; `context.is_story_reply`, `context.story_url`, `get_reply_context()` |
| `image` / `video` / `audio` / `document` | `Instagram*Message` | `url`, `urls` (several attachments), `text` |
| `share` | `InstagramShareMessage` | `attachment_type` (`ig_post`, `ig_reel`, …), `shared_media_id` when supplied, `url` |
| `story_mention` | `InstagramShareMessage` | `url` (expires with the story; do not store the media) |
| `interactive` | `InstagramQuickReplyMessage` / `InstagramButtonReplyMessage` (postback, `is_button_reply`) | `get_interactive_selection()` = the option id, text = title |

`webhook.user.user_id` is the Instagram-scoped ID (IGSID) for this Inbox; phone/BSUID fields stay empty. `media_id` on Instagram messages is the CDN URL; pass it unchanged to `IMediaLibrary.download`. `webhook.entry_referral` carries ad/link context attached to a message.

## Comments and mentions

`process_comment(webhook: IncomingCommentWebhook)` fields:

- `source`: `comments` or `live_comments`; `is_live` is the shortcut.
- `comment_ref` and `post_ref`: Inbox-qualified references.
- `media_product_type`: `FEED`, `REELS`, `AD`, and so on.
- `parent_comment_ref`: `None` means unknown, not top-level.
- `author` (`author_id`, `username`), `text`, `ad_id`.
- `is_own_comment`: your account's own replies. Ignore them, or the app answers itself in a loop.

Wappa filters nothing; your handler decides.

`process_mention(webhook: MentionWebhook)`: `subject` is `media` (a caption mention, with no Comment) or `comment` (has `comment_ref`). Story mentions sent as DMs arrive in `process_message` instead.

## Replies: public versus private

For temporarily disabled Instagram quote handling and `wappa_reply_to` result evidence, see [Send](messaging.md). Hosts keep using `reply_to_message_id` without a Platform branch; requested quotes are omitted before the send, without a rejected extra request.

`self.instagram` is the Instagram Platform Messenger, ready in every Instagram dispatch (`None` on other Platforms): the same Messenger as `self.messenger` plus `comments`, `content` and `history`.

```python
from wappa.messaging import PrivateReply

ig = self.instagram  # None outside an Instagram dispatch
result = await ig.comments.reply_comment(webhook.comment_ref, "Thanks!")   # public; CommentResult.comment_id
dm = await ig.send_text("Here is the price list…", target=PrivateReply(comment_ref=webhook.comment_ref))
```

A private reply is text only, and only one is allowed per comment: within 7 days for posts/Reels, and only during the broadcast for Live. The DM lands in Requests unless the User follows you. You may send ordinary `DirectMessage`s only after the User answers, and only within 24 hours of that answer. Never build a `DirectMessage` from a commenter's ID. One comment may get both a public reply and a private reply; what you must not do is send one when the User was told to expect the other. Public replies work only on top-level, non-hidden comments, and not on Live. `send_text` is the only send that accepts a `PrivateReply`, and only Instagram delivers it today; every other send, and every other Platform's adapter, rejects it.

## Comment Controls

```python
comments = self.instagram.comments
await comments.hide_comment(ref); await comments.unhide_comment(ref)
await comments.delete_comment(ref)                      # media owner only
await comments.set_comments_enabled(webhook.post_ref, False)
```

These return `ControlResult` (`accepted`/`rejected`/`indeterminate`/`rate_limited`). None of them work on Live. Never retry a destructive control on an indeterminate outcome. A successful control does not mean a webhook will follow. Moderation policy (what to hide, who may) belongs to the app, so test only on disposable comments.

## Post and comment reads

```python
reader = self.instagram.content
post = await reader.get_post(webhook.post_ref)          # caption, media_type, permalink, children, counts
page = await reader.list_comments(webhook.post_ref, limit=25)   # top-level, ≤ 50; page.value.next_cursor
replies = await reader.list_replies(webhook.comment_ref, after=cursor)
```

The Instagram reader also has `get_mentioned_post(post_ref)` and `get_mentioned_comment(comment_ref)`, for media on other accounts. Each read returns a `ReadResult`: `found`, `not_found`, `access_denied`, `rejected` or `unavailable`. Missing fields are `None`. A read failure must not stop handling the original event. Processors never make network calls, so enrichment is an explicit step in your handler.
