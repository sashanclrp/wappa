---
checked_on: 2026-11-05
checked_against: Meta Instagram messaging-api, sender-actions and webhooks examples (Graph v26.0) and Wappa's tests/test_instagram_conversations.py
revision: 3
---

# Text, media and sender actions

## Contents

- Receive
- Send
- Location, contact and sticker
- Media Library: upload and download
- Sender actions

## Receive

`process_message(webhook)` gets typed messages from `wappa.webhooks.instagram`:

| `webhook.message.message_type` | Class | Useful fields |
| --- | --- | --- |
| `text` | `InstagramTextMessage` | `text`; `context.is_story_reply`, `context.story_url`, `get_reply_context()` |
| `image` / `video` / `audio` / `document` | `Instagram*Message` | `url`, `urls` (several attachments), `text` |
| `share` | `InstagramShareMessage` | `attachment_type` (`ig_post`, `ig_reel`, …), `shared_media_id` when supplied, `url` |
| `story_mention` | `InstagramShareMessage` | `url` (expires with the story; do not store the media) |
| `interactive` | `InstagramQuickReplyMessage` / `InstagramButtonReplyMessage` (postback, `is_button_reply`) | `get_interactive_selection()` = the option id, text = title |

`webhook.user.user_id` is the Instagram-scoped ID (IGSID) for this Inbox; phone/BSUID fields stay empty. `media_id` on Instagram messages is the CDN URL; pass it unchanged to `IMediaLibrary.download`. `webhook.entry_referral` carries ad/link context attached to a message.

## Send

```python
from pathlib import Path
from wappa.messaging import DirectMessage

target = DirectMessage(inbox_ref=self.inbox_ref, addresses=webhook.user.delivery_addresses())
await self.messenger.send_text("Hi!", target=target, reply_to_message_id=webhook.message.message_id)
await self.messenger.send_image("https://cdn.example.com/menu.png", target)
await self.messenger.send_document(Path("assets/menu.pdf"), target)  # uploaded first
```

| Operation | Limits and emulation |
| --- | --- |
| `send_text` | text over 1000 UTF-8 bytes is sent as several messages, cut on a word boundary when possible, with the reply context on the first; a `PrivateReply` over the limit raises `ValueError` (one reply per comment) |
| `send_image` | https URL or local png/jpeg/gif ≤ 8 MB |
| `send_audio` | aac/m4a/wav/mp4 ≤ 25 MB |
| `send_video` | mp4/ogg/avi/mov/webm ≤ 25 MB |
| `send_document` | pdf ≤ 25 MB |

Instagram attachments carry no caption: a `caption` is sent as a follow-up text after the media (a long caption is split the same way as `send_text`), and `filename` and `transcript` are ignored. A media source is an https URL Meta can fetch, an attachment_id from `IMediaLibrary.upload`, or a local `Path` (uploaded first, then sent by attachment_id). Meta documents the upload only on the Page path, so verify it live on your setup and treat a refusal as data, not a bug to retry. Error codes come back as `code/subcode`: `10/2534022` means outside the messaging window, and `100/2018008` means Meta could not fetch the URL.

## Location, contact and sticker

The same calls work on both Platforms; Instagram adapts them instead of raising:

| Operation | Instagram renders |
| --- | --- |
| `send_location(latitude, longitude, target, name=..., address=...)` | text: name, address and a `📍` Google Maps link |
| `send_contact(contacts, target)` | one text block per card (👤 name, organization, 📞 phones, ✉️ emails, 🔗 urls), split over 1000 UTF-8 bytes; `contacts` is one `ContactCard` or a list, in WhatsApp's contact-card shape (only `name.formatted_name` required) |
| `send_sticker(source, target)` | an image; png/jpeg/gif only, a `.webp` file is rejected before I/O |

`send_location_request` and `send_contact_request` stay WhatsApp-only: Instagram raises `UnsupportedOperationError`, because a text prompt cannot return the location or phone. Check `self.messenger.supported_operations` first and ask the User to type the answer otherwise.

## Media Library: upload and download

Storing and reading media is the shared `IMediaLibrary` capability, not a Messenger method:

```python
from pathlib import Path
from wappa.messaging import IMediaLibrary, MediaFamily

library = self.messenger.require_capability(IMediaLibrary)
stored = await library.upload(Path("assets/menu.png"), MediaFamily.IMAGE)
if stored.success:
    await self.messenger.send_image(stored.media_id, target)  # reuse the id on this Inbox

got = await library.download(webhook.message.media_id)
if got.found:
    data, mime = got.value.content, got.value.content_type
```

`upload` returns an `UploadResult` (`success`, `media_id`, `outcome`, `error_code`): a Media ID on WhatsApp, a reusable `message_attachments` attachment_id on Instagram. `download` is the same call on both Platforms: pass `webhook.message.media_id` unchanged (a Media ID on WhatsApp, the CDN attachment URL on Instagram). On Instagram it sends no credentials and only fetches https Meta CDN hosts (`fbsbx.com`, `fbcdn.net`, `cdninstagram.com`), following at most 3 redirects, each to an allowed host. Outcomes: `found`, `not_found` (expired/deleted, which happens within minutes), `rejected` (host, size), `unavailable` (timeout). Download promptly. Store bytes only where your policy allows; story mentions are never stored. For a custom size limit pass `max_bytes` (`library.download(media_id, max_bytes=5_000_000)`, default 25 MB on Instagram); an oversize read is `rejected` with `error_code="SIZE"`. `upload` takes a `Path` or raw `bytes`; name a `bytes` upload with `filename` (Instagram's rules key off the suffix, so bytes need a `filename` or a known `mime_type`), and `mime_type` is otherwise ignored on Instagram. `MediaFamily.STICKER` uploads as an image on Instagram. `info(media_id)` and `delete(media_id)` follow the WhatsApp Media API; Instagram has neither endpoint and raises `UnsupportedOperationError`.

## Sender actions

To acknowledge an inbound message on any Platform, call `await self.messenger.mark_as_read(message_id, target, typing=True)`; `target` is required and `typing` is keyword-only. On WhatsApp it marks that message read and shows typing. On Instagram it marks the thread seen (there is no per-message seen), then sends `typing_on`. It returns a `MessageResult`. It is not a message, and it is the only seen/typing call on every Platform.
