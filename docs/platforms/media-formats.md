---
checked_on: 2026-11-06
checked_against:
  - live format matrix, lab app ../wappa_examples/instagram_conversations_example (/formats)
  - https://developers.facebook.com/docs/whatsapp/cloud-api/reference/media/
  - https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/messaging-api/
---

# Media formats: what to send on WhatsApp and Instagram

What each Platform really accepts and renders, from Meta's docs **and** a live run of every format (Gate A, 2026-11-06), and which format a Host should prepare for each use. The skills teach the "Recommended formats" table and the "What each Platform cannot process" lists (see the skills PRD, item 15).

**Wappa does not convert media.** Preparing files in a format that fits is the Host's job, usually once, when the asset is stored (a Host that keeps web masters, WebM video and WebP images, stores a messaging rendition next to each). Wappa's part is to know each Platform's rules and refuse a file that does not fit **before any Platform call**, with an error that names the problem; a Meta link it cannot use would otherwise be accepted and fail minutes later (WhatsApp) or reach the User as something unplayable (Instagram). **Wappa provides the information; the Host decides** which file to send to which Platform. `MediaRenditions` (a list of files for `send_sticker` and `send_audio`) is only a convenience: each Platform takes the first file it accepts, and a Host that branches on the Platform itself is equally supported.

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

- **WhatsApp** (`wappa/messaging/whatsapp/media_rules.py`, content read by `wappa/domain/media_probe.py`): by suffix, image `.jpg/.jpeg/.png/.webp`, video `.mp4/.3gp`, audio `.aac/.amr/.mp3/.m4a/.ogg`, voice `.ogg`, sticker `.webp`; by content for local files and uploads, animated WebP as an image, GIF, HEIC, HEVC, MOV, WebM, OGG without Opus, WAV, a sticker not 512×512, size caps; by stored MIME type for a voice note (`audio/ogg`) or sticker (`image/webp`) sent by Media ID; every carousel card.
- **Instagram** (`wappa/messaging/instagram/media.py`): by suffix, image png/jpeg/gif (WebP by URL only), audio aac/m4a/wav/mp4, video mp4/webm (an upload: MP4 only), document pdf as a file; by content for uploads, WebP bytes and HEVC video; size caps. An audio or video URL in another format is refused like a file (as on WhatsApp); only a document URL Instagram cannot attach is shared as a link text.
- Not covered: an extension-less URL or a Media ID for images and video (no fetch); Meta decides those.

## Live results

### WhatsApp (2026-11-06, test number)

API = Meta's response to the send (or Wappa's refusal before I/O); Delivery = the status webhook. Every ❌ below is 131053 with the reason quoted. Rendering checked on the phone where noted.

| Use | Works (link and upload) | Fails | Reason (Meta) |
| --- | --- | --- | --- |
| image | JPEG, PNG, PNG with alpha, static WebP | animated WebP, GIF static and animated, HEIC | "Animated WebP is not supported for image uploads"; "Unsupported Image mime type image/gif (heic). Please use one of image/webp, image/png, image/jpeg" |
| video | MP4 H.264 Baseline, MP4 H.264 High, 3GP H.264 | MP4 HEVC, MOV, MKV, WebM VP8, WebM VP9 | "videoCodec=hevc ... choose a different file"; "Unsupported Video mime type video/quicktime (x-matroska, webm). Please use one of video/3gpp, video/mp4" |
| audio | AAC (ADTS), M4A AAC, MP3, OGG Opus mono and stereo | OGG Vorbis, WAV, WebM Opus | Vorbis: "uploaded as audio/ogg; codecs=opus, however on processing it is application/octet-stream"; "Unsupported Audio mime type audio/wav (webm)" |
| voice | OGG Opus mono and stereo: waveform on the phone | MP3, M4A, AAC: delivered as a voice bubble **without waveform**; OGG Vorbis, WAV, WebM: 131053 | Meta's voice error lists `audio/ogg; codecs=opus, audio/mpeg, audio/amr, audio/mp4, audio/aac`, but only OGG/Opus renders as a voice note |
| document | PDF, DOCX, XLSX, TXT | — | — |
| sticker | WebP 512×512 static and animated | WebP 256×256; PNG 512×512 (link-raw and upload) | "incorrect dimensions, expected dimension: 512x512"; "Unsupported Sticker mime type image/png. Please use one of application/octet-stream, image/webp" |
| card_image / card_video | same as image and video | same as image and video | one failing card fails the whole carousel, the known-good reference card included |

Findings for the spec and the engine:

- A link is accepted (200) and fails later for every unsupported format: the verdict arrives as a status webhook, seconds to minutes later (a HEIC link that Meta could not fetch failed after 6 minutes with "http code 503"). Only refusal before I/O gives the Host a synchronous answer, so Wappa enforces these rules at send time (`wappa/messaging/whatsapp/media_rules.py`).
- Suffix rules alone miss three cases: animated vs static WebP, OGG Vorbis vs Opus, and sticker dimensions. Each needs the bytes (magic bytes, the WebP `ANIM` chunk, the OGG codec header, image size); `wappa/domain/media_probe.py` reads them.
- By Media ID nothing has a suffix. Wappa now checks the stored MIME type (`GET /{media_id}`) for voice notes (`audio/ogg`) and stickers (`image/webp`) before sending (677f34a, 13cec65); other families still pass through.
- Python maps `.3gp` to `audio/3gpp`; WhatsApp needs `video/3gpp` for a video. Fixed in the Media Library (ef05128) and in the lab's asset server.
- A carousel should be checked card by card before sending, since one bad card loses the whole message.
- Re-check after the MetaGraphClient move (15:02): HEVC, MOV, MKV, WebM VP8 and VP9 are refused by Wappa before any call on both the link and upload lanes; only the lab's `link-raw` lane, which bypasses Wappa's rules, reaches Meta and fails by status (131053).

### Instagram (2026-11-06, test account, every family by link and upload)

API = Meta's response; Instagram sends no `failed` status (every accepted send came back `read`), so the phone is the only verdict. Rendering checked by the tester. The development app's rate limit (code 4) split the run into slices of about five calls.

| Use | Works | Fails or degrades | Notes |
| --- | --- | --- | --- |
| image | JPEG, PNG, static GIF, static WebP, HEIC by link; animated GIF **animates** (link and upload) | animated WebP shows only its first frame; PNG with alpha: transparent area filled **white by link**, kept **by upload**; a static WebP **upload** answers HTTP 500 (code 1) | Wappa accepts WebP URLs and refuses WebP files and animated WebP bytes |
| video (links) | MP4 H.264 Baseline and High, WebM VP8, WebM VP9: play, with a poster frame | HEVC MP4 and MOV: accepted, shown as an **empty grey placeholder**; MKV and 3GP: (then) shared as link text | Wappa now refuses MOV, MKV and 3GP links; HEVC by link cannot be detected without fetching |
| video (uploads) | MP4 H.264 | MOV, WebM VP8 and VP9: HTTP **500** (code 1); HEVC MP4: the upload succeeds, the send is refused, 3/1545003 "Public attachments are not allowed to be sent directly" | Wappa refuses every video upload except an H.264 MP4 |
| audio and voice (links) | M4A AAC, AAC ADTS, WAV PCM: a voice bubble with "View transcription" | MP3, OGG Opus mono and stereo, OGG Vorbis, WebM Opus: (then) shared as raw link text | Wappa now refuses these links, as WhatsApp does; `is_voice` changes nothing on Instagram |
| audio (uploads) | M4A AAC, AAC ADTS, WAV PCM | MP3, OGG, WebM: refused by Wappa before I/O | no HTTP 500: the upload list matches Meta's documented list |
| sticker (sent as image) | PNG 512 (same alpha behaviour as images), static WebP 512 and 256 by URL | animated WebP 512 shows its first frame | Instagram has no sticker size rule |
| document | PDF, link and upload | DOCX, XLSX, TXT by URL: shared as a link text (the file opens from it) | kept as emulation: the User still gets the file |
| card_image | JPEG, PNG, PNG with alpha, static WebP | animated WebP and GIF show as a still | — |
| card_video | every format: the card shows `poster_url`; a tap opens the video URL in the browser, where it plays | — | a card is a link, not a player, on Instagram |

Findings:

- Instagram's verdict is the phone, not a status: accepted sends are `read`, never `failed`, so a format Instagram degrades (animated WebP, alpha, HEVC or MOV by link) looks like a success to the Host. Only rules enforced before I/O protect the Host, which is why Wappa refuses rather than shares an unplayable audio or video link (decision 2026-11-06: follow WhatsApp).
- Animation: GIF is Instagram's animation format (in a DM, not in a card); WhatsApp's is animated WebP (stickers) or MP4 (video).
- Transparency depends on the lane on Instagram (white matte by link, transparent by upload), so a Host that needs a predictable look flattens transparent images before sending.
- Audio: M4A (AAC) plays on both Platforms. A WhatsApp voice note needs OGG/Opus, which Instagram does not play, so voice notes on both need two files.
- An Instagram upload that answers HTTP 500 is a format refusal in practice (WebM and MOV video, WebP image: code 1 "unknown error"), not an outage.
- WebM is the one format where the lanes split on Instagram: it plays by URL and fails as an upload; WhatsApp refuses it in both.

## What the skills teach

- Prepare media once, in the recommended format, when the asset is stored; never rely on Meta or Wappa to convert.
- Teach both "cannot process" lists as facts; the Host decides per Platform. Renditions (`send_sticker(["s.webp", "s.gif"])`, `send_audio(["v.ogg", "v.m4a"], is_voice=True)`) are one way to do it, not the required one.
- Prefer upload + Media ID for media sent more than once on WhatsApp (Media IDs live 30 days; Meta's URL cache lasts about 10 minutes); on Instagram WebP and WebM work only by URL.
- A Meta acceptance is not delivery: on WhatsApp watch `failed` status webhooks (131053) for links; on Instagram there is no failed status, so only the recommended formats are safe.
- Test new formats in small runs: the Instagram development app allows about 10-20 calls per burst before code `4` (`references/rate-limits.md`).
