---
checked_on: 2026-11-08
checked_against: Meta WhatsApp Cloud API and Instagram messaging-api, sender-actions, quick-replies, button- and generic-template pages (Graph v26.0), Wappa's tests/test_instagram_conversations.py and the live format matrix of 2026-11-06
revision: 5
---

# Sending and receiving messages

## Contents

- Receive
- Send
- Location, contact and sticker
- One result per send
- Interactive Messages
- Selections
- Media Library: upload and download
- Sender actions

## Receive

Every Platform's conversation message arrives in `process_message(webhook)`: `webhook.message` (`message_type`, `message_id`, text, `media_id` for media, `get_interactive_selection()` for a tapped option) and `webhook.user` (read its fields directly; `webhook.user.delivery_addresses()` builds the reply target). Platform-specific message classes and fields are in `whatsapp.md` and `instagram.md`. Download inbound media with `self.messenger.media.download(webhook.message.media_id)` on every Platform.

## Send

For an incoming DM, pass `webhook.message.message_id`: Instagram preserves the webhook's original `message.mid`, while WhatsApp preserves its native message ID. The adapter handles the wire shape. Meta's [Send a reply](https://developers.facebook.com/documentation/business-messaging/instagram-messaging/features/send-message#send-a-reply) documents top-level `reply_to.mid` on the Facebook Graph/Page-token path.

Instagram first sends `reply_to_message_id` as top-level `reply_to: {"mid": ...}`. If that call is rejected with HTTP 400 and Meta code `100/2534002`, it retries only that refused part once without `reply_to`, preserving the message and recipient. The returned result is the retry result, with `platform_response["wappa_reply_to"] = {"dropped": True, "error_code": "100/2534002"}` on success or failure. This evidence survives split text, media-caption and other multipart emulations alongside `wappa_parts`. Other errors and indeterminate outcomes never trigger quote fallback; accepted parts are never resent. Hosts use the same parameter on both Platforms without branching.

```python
from pathlib import Path
from wappa.messaging import DirectMessage

target = DirectMessage(inbox_ref=self.inbox_ref, addresses=webhook.user.delivery_addresses())
await self.messenger.send_text("Hi!", target=target, reply_to_message_id=webhook.message.message_id)
await self.messenger.send_image("https://cdn.example.com/menu.png", target)
await self.messenger.send_document(Path("assets/menu.pdf"), target)  # uploaded first
```

| Operation | On Instagram: limits and emulation |
| --- | --- |
| `send_text` | text over 1000 UTF-8 bytes is sent as several messages, cut on a word boundary when possible, with the reply context on the first; a `PrivateReply` over the limit raises `ValueError` (one reply per comment) |
| `send_image` | http(s) URL (WebP works by URL) or local png/jpeg/gif ≤ 8 MB; a WebP file is refused (the upload endpoint answers HTTP 500); an animated WebP shows only its first frame, a GIF animates |
| `send_audio` | aac/m4a/wav/mp4 ≤ 25 MB, by URL or file; any other format (`.mp3`, `.ogg`, `.amr`, `.webm`) raises `ValueError` before any call, URL included. Instagram has no voice-note type: every audio shows as a voice bubble and `is_voice` changes nothing. M4A (AAC) plays on both Platforms; pass renditions (`["n.ogg", "n.m4a"]`) when WhatsApp needs an OGG/Opus voice note |
| `send_video` | by URL mp4/webm ≤ 25 MB; as a local file or upload only an H.264 MP4 (a WebM file and HEVC bytes raise `ValueError` before any call); any other format (`.mov`, `.3gp`, `.mkv`), URL included, raises `ValueError` before any call. An HEVC MP4 **link** is accepted but shows an empty placeholder (Wappa cannot see a URL's codec): send H.264 |
| `send_document` | pdf ≤ 25 MB; another format by URL (`.docx`, `.xlsx`, `.txt` …) is shared as a text with `filename` (else the URL's file name) and the link; a local `Path` uploads under `filename` |

On WhatsApp the same calls check Meta's media rules before sending and raise `ValueError` for a format Meta would accept and then fail (131053): images are JPEG, PNG or static WebP (no GIF, HEIC or animated WebP); video is MP4 or 3GP with H.264 (no HEVC, MOV, MKV or WebM); audio is AAC, AMR, MP3, M4A or OGG/Opus; a voice note (`is_voice=True`) is OGG/Opus only, the only format that shows a waveform; a sticker is 512x512 WebP. Convert first; a refusal never reaches Meta. The per-use recommendations and each Platform's "cannot process" list are in `media-formats.md`.

Instagram attachments carry no caption: a `caption` is sent as a follow-up text after the media (a long caption is split the same way as `send_text`), and the send returns one result listing both parts (see "One result per send" below); `filename` names an upload or a link text (an attachable URL has no name slot); `transcript` is middleware-only metadata that no Platform receives. Text keeps WhatsApp's limits on every Platform: `send_text` up to 4096 characters (`TEXT_MAX`) and a caption up to 1024 (`CAPTION_MAX`), checked before any send with `ValueError`. A media source is an http(s) URL Meta can fetch, an attachment_id from `IMediaLibrary.upload`, or a local `Path` (uploaded first, then sent by attachment_id; a non-ASCII file name is transliterated to ASCII). A local file in a format Instagram cannot attach, or over its size limit, raises `ValueError` before any call: there is no link to share. Wappa never converts media; prepare the file in a fitting format (see `media-formats.md`). The `message_attachments` upload was verified live for every family on 2026-11-06. Error codes come back as `code/subcode`: `10/2534022` means outside the messaging window, and `100/2018008` means Meta could not fetch the URL.

## Location, contact and sticker

The same calls work on both Platforms; Instagram adapts them instead of raising:

| Operation | Instagram renders |
| --- | --- |
| `send_location(latitude, longitude, target, name=..., address=...)` | text: name, address and a `📍` Google Maps link |
| `send_contact(contacts, target)` | one text block per card (👤 name, organization, 📞 phones, ✉️ emails, 🔗 urls), split over 1000 UTF-8 bytes; `contacts` is one `ContactCard` or a list, in WhatsApp's contact-card shape (`name.first_name` required; the 👤 line is `name.formatted_name`, built from the name parts when omitted) |
| `send_sticker(source, target)` | an image; with several renditions a png/jpeg/gif one is preferred (pass `[s.webp, s.gif]` for an animated sticker), else a WebP URL |

Location and phone-number requests are WhatsApp-only (`self.whatsapp.send_location_request`, `self.whatsapp.send_contact_request`), because a text prompt on Instagram cannot return the location or phone. `self.whatsapp` is `None` in an Instagram dispatch, so ask the User to type the answer there.

## One result per send

Every call returns one `MessageResult`, even when Instagram needs several messages (a split text, a caption follow-up, a carousel body, a numbered menu). `success` is `True` only when every part was accepted; `message_id` is the final part's ID (the interactive message a User taps), or the media's for a media-plus-caption send; `platform_response["wappa_parts"]` is `{"message_ids": [...every part...], "delivered": n}`, present only for a multi-part send, so read it with `(result.platform_response or {}).get("wappa_parts")`. On a partial failure the error says how many parts were already delivered: never resend the whole call blindly, or the User sees the delivered parts twice. Store `message_id` and the part IDs with your own record to match later `process_status` webhooks: a `StatusWebhook` (`from wappa.webhooks import StatusWebhook`) has `message_id`, `status` (`MessageStatus`: `sent`, `delivered`, `read`, `played`, `failed`, `deleted`, `pending`), `user_id` and `timestamp`. On Instagram only `read` arrives, carrying the last message the User has seen, so treat it as "everything up to this message is read". Classify a failure with `message_outcome(result)` (`ACCEPTED`, `REJECTED`, `INDETERMINATE`, `RATE_LIMITED`); `MessageResult` itself has `success`, `error`, `error_code` and `retry_after`, not an outcome field. Instagram reports no `failed` status: an accepted send comes back as read or not at all.

## Interactive Messages

One Messenger method per action, identical on WhatsApp and Instagram (ADR-0025). Write the call once; the adapter maps it. Never branch on Platform name; check `m.supported_operations` once if the app also runs elsewhere.

```python
from wappa.messaging import (
    CardMedia, InteractiveHeader, ListRow, ListSection, MessageCard, ReplyButton, UrlButton,
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
await m.send_cta_message(
    button_text="Pricing", button_url="https://example.com/pricing", target=target, body="See plans",
    header=InteractiveHeader.of_text("Plans"),  # or of_image/of_video/of_document, as for buttons
)
await m.send_carousel(
    cards=[
        MessageCard(header=CardMedia.image(url="https://example.com/pro.png"), title="Pro", subtitle="$29/mo",
                    buttons=(ReplyButton(id="plan:pro", title="Choose"),)),
        MessageCard(header=CardMedia.video(url="https://example.com/team.mp4", poster_url="https://example.com/team.jpg"),
                    title="Team", subtitle="$99/mo", buttons=(ReplyButton(id="plan:team", title="Choose"),)),
    ],
    target=target, body="Our plans", reply_to_message_id=webhook.message.message_id,
)
```

Interactive limits are the minimum across WhatsApp and Instagram and hold when you build the value, so a message that builds is deliverable on both: button title ≤ 20, 1–3 buttons, button and CTA body ≤ 640, CTA button text ≤ 20, list body ≤ 1000, ≤ 10 rows in total, row title ≤ 20, row description ≤ 72, section title ≤ 24, button id ≤ 256, row id ≤ 200, header text and footer ≤ 60, 2–10 carousel cards, carousel body ≤ 1000, card title and subtitle ≤ 80 each (≤ 160 together), ≤ 2 buttons per card (constants in `wappa.domain.interactive`; `GET /api/{platform}/interactive/limits` reports them). How Instagram renders each one:

- `send_list_message` → quick replies. All rows are flattened and the row `id` is the payload. Quick replies show row titles only, so when a section has a title or a row a description the list is also written into the text after the body as a numbered menu (`1. title — description` under each section title); `button_text` has no slot. The text `header` and footer fold into the text, which is split over 1000 UTF-8 bytes with the quick replies on the last message.
- `send_button_message` → button template with postback buttons. A text header (`InteractiveHeader.of_text(...)`) and footer fold into the text; over 640 characters the header (then the body) is sent first as text. A media header (`of_image`, `of_video`, `of_document`, by `url` or by an `attachment_id` from `IMediaLibrary.upload` as `media_id`) is sent first as its own attachment, then the buttons with the full body.
- `send_text` over 1000 UTF-8 bytes, and long media captions, are split into several messages; a `PrivateReply` is one message per comment and cannot be split.
- `send_cta_message` → button template with one URL button; its header is emulated exactly as for `send_button_message`.
- `send_carousel` → `body` is sent first as a text message (with the reply context), then a generic template. `CardMedia` is URL-only (`url`, plus `poster_url` for a video), so one card serves both Platforms. An image card shows `header.url`; a video card shows `header.poster_url` and opens the video on tap. A video card without `poster_url` raises `UnsupportedOperationError` before any call: card media is never sent apart from its card. Every card needs a `header` (image or video by URL; WhatsApp sends it as the header `link` and takes no Media ID) and a button: one `UrlButton` or 1–2 `ReplyButton`s, never a mix, checked when the `MessageCard` is built; every card in a carousel carries the same button kind and count and the same header kind, all image or all video (`check_carousel`). On WhatsApp title + subtitle become the card body. For a single card, use `send_button_message` with a media header.

Instagram has no phone/email quick replies, so ask the User to type those. WhatsApp Templates are WhatsApp-only, on `self.whatsapp.templates`. "Template" in Meta's Instagram wire format is not a WhatsApp Template.

## Selections

Every choice arrives in `process_message` as an `InboundMessageWebhook`; read it with `webhook.get_interactive_selection()` (the `ReplyButton.id` or `ListRow.id`). This holds for a quick reply, a postback button or card button (`InstagramButtonReplyMessage`, `is_button_reply`), and WhatsApp button and list replies. There is no separate interaction hook. URL buttons produce no event.

Put the flow step in every id so stale taps can be detected; see `wappa-conversational-scores`.

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
