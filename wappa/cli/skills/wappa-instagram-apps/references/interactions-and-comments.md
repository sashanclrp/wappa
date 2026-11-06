---
checked_on: 2026-11-05
checked_against: Meta Instagram quick-replies, button-template, generic-template, private-replies and comment-moderation pages (Graph v26.0) and Wappa's tests/test_instagram_conversations.py and ADR-0016
revision: 3
---

# Interactions, comments and reads

## Contents

- Interactive Messages
- Selections
- Comments and mentions
- Replies: public versus private
- Comment Controls
- Post and comment reads

## Interactive Messages

One Messenger method per action, identical on WhatsApp and Instagram (ADR-0016). Write the call once; the adapter maps it. Never branch on Platform name; check `m.supported_operations` once if the app also runs elsewhere.

```python
from wappa.messaging import (
    InteractiveHeader, ListRow, ListSection, MessageCard, ReplyButton, UrlButton,
)

await m.send_list_message(
    sections=[ListSection(title="Services", rows=[ListRow(id="form:service:website", title="Website")])],
    target=target, body="Pick one", button_text="Options",
)
await m.send_button_message(
    buttons=[ReplyButton(id="form:budget:small", title="< $1k"), ReplyButton(id="form:budget:large", title="$1k+")],
    target=target, body="Budget?", footer="Tap one",
)
await m.send_button_message(  # media header: Instagram sends the image, then the buttons
    buttons=[ReplyButton(id="plan:pro", title="Choose")], target=target, body="Pro", footer="$29/mo",
    header=InteractiveHeader.of_image(url="https://example.com/pro.png"),
)
await m.send_cta_message(button_text="Pricing", button_url="https://example.com/pricing", target=target, body="See plans")
await m.send_carousel(
    cards=[MessageCard(title="Pro", subtitle="$29/mo", image_url="https://example.com/pro.png",
                       buttons=(ReplyButton(id="plan:pro", title="Choose"), UrlButton(title="Details", url="https://example.com/pro")))],
    target=target, body="Our plans",
)
```

Interactive limits are the minimum across WhatsApp and Instagram and hold when you build the value, so a message that builds is deliverable on both: button title ≤ 20, 1–3 buttons, button body ≤ 640, list body ≤ 1000, ≤ 10 rows in total, row title ≤ 20, header text and footer ≤ 60 (constants in `wappa.domain.interactive`). Instagram mappings:

- `send_list_message` → quick replies. All rows are flattened and the row `id` is the payload. Section titles, row descriptions and `button_text` are dropped; the text `header` and footer fold into the text, which is split over 1000 UTF-8 bytes with the quick replies on the last message.
- `send_button_message` → button template with postback buttons. A text header (`InteractiveHeader.of_text(...)`) and footer fold into the text; over 640 characters the header (then the body) is sent first as text. A media header (`of_image`, `of_video`, `of_document`, by `url` or by an `attachment_id` from `IMediaLibrary.upload` as `media_id`) is sent first as its own attachment, then the buttons with the full body.
- `send_text` over 1000 UTF-8 bytes, and long media captions, are split into several messages; a `PrivateReply` is one message per comment and cannot be split.
- `send_cta_message` → button template with one URL button.
- `send_carousel` → 2–10 cards; `body` is sent first as a text message, then a generic template (title/subtitle at most 80, up to 3 buttons). On WhatsApp every card needs `image_url`, title + subtitle become a 160-character card body, and every card carries the same buttons kind and count (one `UrlButton` or 1–2 `ReplyButton`s). For a single card, use `send_button_message` with an image header.

Instagram has no phone/email quick replies, so ask the User to type those. WhatsApp Templates are the WhatsApp-only `ITemplateMessaging` capability. "Template" in Meta's Instagram wire format is not a WhatsApp Template.

## Selections

Every choice arrives in `process_message` as an `InboundMessageWebhook`; read it with `webhook.get_interactive_selection()` (the `ReplyButton.id` or `ListRow.id`). This holds for a quick reply, a postback button or card button (`InstagramButtonReplyMessage`, `is_button_reply`), and WhatsApp button and list replies. There is no separate interaction hook. URL buttons produce no event.

Put the flow step in every id so stale taps can be detected; see `wappa-conversational-scores`.

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

```python
from wappa.messaging import ICommentControls, PrivateReply

controls = m.require_capability(ICommentControls)
result = await controls.reply_comment(webhook.comment_ref, "Thanks!")   # public; CommentResult.comment_id
dm = await m.send_text("Here is the price list…", target=PrivateReply(comment_ref=webhook.comment_ref))
```

A private reply is text only, and only one is allowed per comment: within 7 days for posts/Reels, and only during the broadcast for Live. The DM lands in Requests unless the User follows you. You may send ordinary `DirectMessage`s only after the User answers, and only within 24 hours of that answer. Never build a `DirectMessage` from a commenter's ID, and never switch between public and private silently. Public replies work only on top-level, non-hidden comments, and not on Live. `send_text` is the only send that accepts a `PrivateReply`, and only Instagram delivers it today; every other send, and every other Platform's adapter, rejects it.

## Comment Controls

```python
from wappa.messaging import ICommentControls

controls = m.require_capability(ICommentControls)
await controls.hide_comment(ref); await controls.unhide_comment(ref)
await controls.delete_comment(ref)                      # media owner only
await controls.set_comments_enabled(webhook.post_ref, False)
```

These return `ControlResult` (`accepted`/`rejected`/`indeterminate`). None of them work on Live. Never retry a destructive control on an indeterminate outcome. A successful control does not mean a webhook will follow. Moderation policy (what to hide, who may) belongs to the app, so test only on disposable comments.

## Post and comment reads

```python
from wappa.messaging import IConversationContentReader

reader = m.require_capability(IConversationContentReader)
post = await reader.get_post(webhook.post_ref)          # caption, media_type, permalink, children, counts
page = await reader.list_comments(webhook.post_ref, limit=25)   # top-level, ≤ 50; page.value.next_cursor
replies = await reader.list_replies(webhook.comment_ref, after=cursor)
```

The Instagram reader also has `get_mentioned_post(post_ref)` and `get_mentioned_comment(comment_ref)`, for media on other accounts. Each read returns a `ReadResult`: `found`, `not_found`, `access_denied`, `rejected` or `unavailable`. Missing fields are `None`. A read failure must not stop handling the original event. Processors never make network calls, so enrichment is an explicit step in your handler.
