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
| `send_image` | http(s) URL (WebP works by URL) or local png/jpeg/gif ≤ 8 MB; a WebP file is refused (the upload endpoint answers HTTP 500); an animated WebP shows only its first frame, a GIF animates |
| `send_audio` | aac/m4a/wav/mp4 ≤ 25 MB, by URL or file; any other format (`.mp3`, `.ogg`, `.amr`, `.webm`) raises `ValueError` before any call. Every audio shows as a voice bubble; pass renditions (`["n.ogg", "n.m4a"]`) to serve both Platforms |
| `send_video` | by URL mp4/webm ≤ 25 MB; as a local file only an H.264 MP4 (WebM, MOV and HEVC uploads fail); any other format (`.mov`, `.3gp`, `.mkv`) raises `ValueError` before any call. An HEVC MP4 link is accepted but shows an empty placeholder: send H.264 |
| `send_document` | pdf ≤ 25 MB; another format by URL (`.docx`, `.xlsx`, `.txt` …) is shared as a text with `filename` (else the URL's file name) and the link; a local `Path` uploads under `filename` |

On WhatsApp the same calls check Meta's media rules before sending and raise `ValueError` for a format Meta would accept and then fail (131053): images are JPEG, PNG or static WebP (no GIF, HEIC or animated WebP); video is MP4 or 3GP with H.264 (no HEVC, MOV, MKV or WebM); audio is AAC, AMR, MP3, M4A or OGG/Opus; a voice note (`is_voice=True`) is OGG/Opus only, the only format that shows a waveform; a sticker is 512x512 WebP. Convert first; a refusal never reaches Meta.

Instagram attachments carry no caption: a `caption` is sent as a follow-up text after the media (a long caption is split the same way as `send_text`), and the send returns one result listing both parts; `filename` names an upload or a link text (an attachable URL has no name slot); `transcript` is middleware-only metadata that no Platform receives. Text keeps WhatsApp's limits on every Platform: `send_text` up to 4096 characters (`TEXT_MAX`) and a caption up to 1024 (`CAPTION_MAX`), checked before any send with `ValueError`. A media source is an http(s) URL Meta can fetch, an attachment_id from `IMediaLibrary.upload`, or a local `Path` (uploaded first, then sent by attachment_id; a non-ASCII file name is transliterated to ASCII). A local file in a format Instagram cannot attach, or over its size limit, raises `ValueError` before any call: there is no link to share, and conversion is not shipped yet. Meta documents the upload only on the Page path, so verify it live on your setup and treat a refusal as data, not a bug to retry. Error codes come back as `code/subcode`: `10/2534022` means outside the messaging window, and `100/2018008` means Meta could not fetch the URL.

## Location, contact and sticker

The same calls work on both Platforms; Instagram adapts them instead of raising:

| Operation | Instagram renders |
| --- | --- |
| `send_location(latitude, longitude, target, name=..., address=...)` | text: name, address and a `📍` Google Maps link |
| `send_contact(contacts, target)` | one text block per card (👤 name, organization, 📞 phones, ✉️ emails, 🔗 urls), split over 1000 UTF-8 bytes; `contacts` is one `ContactCard` or a list, in WhatsApp's contact-card shape (`name.first_name` required; the 👤 line is `name.formatted_name`, built from the name parts when omitted) |
| `send_sticker(source, target)` | an image; with several renditions a png/jpeg/gif one is preferred (pass `[s.webp, s.gif]` for an animated sticker), else a WebP URL |

Location and phone-number requests are WhatsApp-only (`self.whatsapp.send_location_request`, `self.whatsapp.send_contact_request`), because a text prompt on Instagram cannot return the location or phone. `self.whatsapp` is `None` in an Instagram dispatch, so ask the User to type the answer there.

## Media Library: upload and download

Storing and reading media is the shared Media Library (`IMediaLibrary`), ready on every Messenger as `self.messenger.media`:

```python
from pathlib import Path
from wappa.messaging import MediaFamily

library = self.messenger.media
stored = await library.upload(Path("assets/menu.png"), MediaFamily.IMAGE)
if stored.success:
    await self.messenger.send_image(stored.media_id, target)  # reuse the id on this Inbox

got = await library.download(webhook.message.media_id)
if got.found:
    data, mime = got.value.content, got.value.content_type
```

`upload` returns an `UploadResult` (`success`, `media_id`, `outcome`, `error_code`): a Media ID on WhatsApp, a reusable `message_attachments` attachment_id on Instagram. `download` is the same call on both Platforms: pass `webhook.message.media_id` unchanged (a Media ID on WhatsApp, the CDN attachment URL on Instagram). On Instagram it sends no credentials and only fetches https Meta CDN hosts (`fbsbx.com`, `fbcdn.net`, `cdninstagram.com`), following at most 3 redirects, each to an allowed host. Outcomes: `found`, `not_found` (expired/deleted, which happens within minutes), `rejected` (host, size), `unavailable` (timeout). Download promptly. Store bytes only where your policy allows; story mentions are never stored. For a custom size limit pass `max_bytes` (`library.download(media_id, max_bytes=5_000_000)`, default 25 MB on Instagram); an oversize read is `rejected` with `error_code="SIZE"`. `upload` takes a `Path` or raw `bytes`; name the upload with `filename` and set its content type with `mime_type` on both Platforms; Instagram's rules key off the suffix, so a `filename` without one takes the `Path`'s suffix or, for `bytes`, the suffix of a known `mime_type` (`filename="report", mime_type="application/pdf"` uploads `report.pdf`), and a non-ASCII name is transliterated to ASCII. `MediaFamily.STICKER` uploads as an image on Instagram. `info(media_id)` and `delete(media_id)` follow the WhatsApp Media API; Instagram has neither endpoint and raises `UnsupportedOperationError`.

## Sender actions

To acknowledge an inbound message on any Platform, call `await self.messenger.mark_as_read(message_id, target, typing=True)`; `target` is required and `typing` is keyword-only. On WhatsApp it marks that message read and shows typing. On Instagram it marks the thread seen (there is no per-message seen), then sends `typing_on`. It returns a `MessageResult`. It is not a message, and it is the only seen/typing call on every Platform.

Instagram DM webhooks carry only the User's scoped ID, so `webhook.user.get_display_name()` is the raw IGSID. To learn the User's name, call `profile = await self.messenger.resolve_platform_user_profile(webhook.user)`: on Instagram it looks up `name`, `username` and `profile_pic` with the Inbox token and returns a `PlatformUserProfile` (`profile_name`, `username`, `picture_url`, plus the webhook evidence). It never raises for a Graph failure; check `profile.found` (or `profile.outcome`: `not_found`, `access_denied`, `rejected`, `unavailable`) and keep the evidence. On WhatsApp the same call returns the webhook evidence with no request. Wappa never calls it for you and never caches it: store the fields in your own User record and decide when to resolve again.
