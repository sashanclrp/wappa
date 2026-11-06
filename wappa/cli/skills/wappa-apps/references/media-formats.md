---
checked_on: 2026-11-06
checked_against:
  - Wappa's live format matrix of 2026-11-06 (every family by link and upload on WhatsApp and Instagram)
  - wappa/messaging/whatsapp/media/rules.py and wappa/messaging/instagram/media/rules.py
  - https://developers.facebook.com/docs/whatsapp/cloud-api/reference/media/
  - https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/messaging-api/
revision: 2
---

# Media formats on WhatsApp and Instagram

## Contents

- The unified kit: one set of files, no Platform branch
- Recommended formats
- What each Platform cannot process
- What Wappa refuses before any call
- How to use these facts

**Wappa provides the facts; the Host decides.** Wappa never converts media. It knows each Platform's rules and refuses a file that doesn't fit before any Platform call, raising `ValueError` with the reason and "convert it before sending". Preparing files is the Host's job, ideally once, when the asset is stored.

## The unified kit: one set of files, no Platform branch

Prepare every asset in the format below and the same send works on WhatsApp and Instagram, with no `if instagram … else …` in your code:

| Use | Prepare | Send with |
| --- | --- | --- |
| Photo | JPEG (a static WebP works by URL on both, but Instagram refuses a WebP upload, so JPEG is the one format that works by link and by file everywhere) | `send_image(url_or_path, target)` |
| Graphic, logo, screenshot | PNG, flattened onto your background if transparency matters | `send_image` |
| Video, including "animated" content | MP4: H.264 Main, AAC audio, faststart, ≤ 16 MB | `send_video` |
| Audio (music, message, podcast clip) | M4A (AAC) | `send_audio` |
| Document | PDF, ≤ 25 MB | `send_document` |
| Card or header image | JPEG or PNG at a public https URL | `InteractiveHeader.of_image`, `CardMedia.image` |
| Card or header video | MP4 H.264 at a public https URL, plus a JPEG poster | `InteractiveHeader.of_video`, `CardMedia.video(url, poster_url)` |
| **Voice note** (waveform on WhatsApp) | OGG/Opus mono **and** M4A (AAC) | `send_audio([note.ogg, note.m4a], target, is_voice=True)`: WhatsApp takes the OGG, Instagram the M4A |
| **Sticker** | WebP 512×512 (static ≤ 100 KB, animated ≤ 500 KB) **and** a PNG (static) or GIF (animated) | `send_sticker([s.webp, s.png], target)`: WhatsApp takes the WebP, Instagram the PNG or GIF |

The last two rows are the only uses no single format covers. Pass both files as a plain list (`MediaRenditions` is a path or URL, or a sequence of them): each Platform takes the first one it accepts, so your code still has one call. Size every asset to the smaller cap (WhatsApp: image 5 MB, video and audio 16 MB), and keep http(s) URLs with a real file suffix so Wappa can check them.

Branching on `self.inbox_ref.platform` to choose a file is supported too, but the kit above makes it unnecessary. The sections below are the evidence behind the kit, for when an asset can't follow it.

## Recommended formats

One format per use works on both Platforms, except voice notes, animated images and animated stickers, which need a second rendition.

| Use | Universal target | WhatsApp | Instagram | Second rendition |
| --- | --- | --- | --- | --- |
| image (photo) | JPEG | ✅ link and upload | ✅ link and upload | — |
| image (graphic, transparency) | PNG | ✅ (alpha kept) | ✅; alpha becomes white by link, kept by upload | flatten onto a Host background when the look must not depend on the lane |
| image (animated) | none | ❌ images cannot animate: send an MP4 video | GIF animates in a DM (not in a card) | yes: MP4 for WhatsApp, GIF for Instagram, or send as video on both |
| video | MP4, H.264 Main (Baseline for old Android), AAC, faststart, ≤ 16 MB | ✅ link and upload | ✅ link and upload | — |
| audio | M4A (AAC) | ✅ | ✅ (shown as a voice bubble) | — |
| voice note | OGG/Opus mono 48 kHz | ✅ the only format with a waveform | ❌ OGG does not play; Instagram has no voice-note type, every audio is a voice bubble | yes: M4A (AAC) for Instagram |
| document | PDF | ✅ | ✅ (the only attachable type; other types by URL become a link text) | — |
| sticker (static) | WebP 512×512, ≤ 100 KB | ✅ | ✅ **by URL only** (the upload endpoint answers HTTP 500) | PNG when it must be uploaded to Instagram |
| sticker (animated) | animated WebP 512×512, ≤ 500 KB | ✅ | ❌ first frame only | yes: GIF for Instagram |
| card image | JPEG or PNG, by public URL | ✅ | ✅ (a GIF shows as a still) | — |
| card video | MP4 H.264, by public URL | ✅ plays in the card | ⚠️ the card shows `poster_url` (a JPEG) and a tap opens the video URL in the browser | the poster frame |

In short: **video MP4 (H.264 + AAC), documents PDF, photos JPEG, graphics PNG, audio M4A (AAC), WhatsApp voice notes OGG/Opus, stickers WebP 512×512 plus PNG or GIF for Instagram.** Avoid as messaging formats: MOV, MKV, HEVC, HEIC, WAV, OGG Vorbis, animated WebP as an image, and WebM (Instagram plays it by URL, WhatsApp refuses it).

## What each Platform cannot process

Each list is what Wappa refuses before any call (✋) or what Meta takes but the User does not get as intended (⚠️). The Host decides what to send where.

**WhatsApp cannot:**

- ✋ image: GIF, HEIC, animated WebP (images never animate).
- ✋ video: MOV, MKV, WebM (VP8 or VP9), HEVC (H.265); only MP4 or 3GP with H.264.
- ✋ audio: WAV, WebM, OGG Vorbis; voice note: anything but OGG/Opus (⚠️ MP3, M4A or AAC as a voice note arrive with no waveform, so Wappa refuses them).
- ✋ sticker: anything but WebP 512×512 (PNG and a 256×256 WebP fail).
- ✋ over the size caps: image 5 MB, video and audio 16 MB, static sticker 100 KB, animated sticker 500 KB, document 100 MB.
- ✋ a carousel with one bad card (the whole carousel fails) or mixed image and video headers.

**Instagram cannot:**

- ✋ image: an uploaded WebP (HTTP 500; a WebP URL works); ⚠️ animated WebP (first frame only); ⚠️ PNG transparency by link (white matte).
- ✋ video: MOV, MKV, 3GP, OGG, AVI; an upload other than an H.264 MP4 (WebM uploads answer HTTP 500, an uploaded HEVC's send is refused 3/1545003); ⚠️ an HEVC MP4 **link** is accepted but shows an empty placeholder (Wappa cannot see a URL's codec).
- ✋ audio: MP3, OGG (Opus or Vorbis), WebM, AMR; only AAC, M4A, WAV and MP4 audio play. There is no separate voice note.
- ⚠️ document: only PDF attaches; another type by URL is shared as a text with the file name and link (the file opens from it); ✋ another type as a file.
- ⚠️ cards: a GIF card image is a still; a video card is its poster, and the tap opens the video in the browser.
- ✋ over the size caps: image 8 MB, audio, video and document 25 MB.

Neither Platform: an extension-less URL or a Media ID is not checked (no fetch); Meta decides, and on Instagram there is no `failed` status to tell the Host.

## What Wappa refuses before any call

- **WhatsApp** (`wappa/messaging/whatsapp/media/rules.py`, content read by `wappa/domain/media_probe.py`): by suffix, image `.jpg`, `.jpeg`, `.png`, `.webp`, video `.mp4/.3gp`, audio `.aac`, `.amr`, `.mp3`, `.m4a`, `.ogg`, voice `.ogg`, sticker `.webp`; by content for local files and uploads, animated WebP as an image, GIF, HEIC, HEVC, MOV, WebM, OGG without Opus, WAV, a sticker not 512×512, size caps; by stored MIME type for a voice note (`audio/ogg`) or sticker (`image/webp`) sent by Media ID; every carousel card.
- **Instagram** (`wappa/messaging/instagram/media/rules.py`): by suffix, image png/jpeg/gif (WebP by URL only), audio aac/m4a/wav/mp4, video mp4/webm (an upload: MP4 only), document pdf as a file; by content for uploads, WebP bytes and HEVC video; size caps. An audio or video URL in another format is refused like a file (as on WhatsApp); only a document URL Instagram cannot attach is shared as a link text.
- Not covered: an extension-less URL or a Media ID for images and video (no fetch); Meta decides those.

## How to use these facts

- Store a messaging rendition next to each web master (WebM → MP4 H.264 + AAC, WebP → JPEG or PNG, OGG → M4A) and send that.
- Never catch and ignore the `ValueError`: it means Meta would accept the file and the User would get nothing (WhatsApp 131053) or something unplayable (Instagram). Fix the asset or pick another rendition.
- An extension-less URL or a Media ID is not checked; Instagram has no `failed` status, so an unplayable file there is silent. Prefer URLs with a real suffix.
- Re-check this file when its `checked_on` is about six months old, or when Meta's media pages change; trust the live Platform over this copy and say which rows look stale.
