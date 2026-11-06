---
checked_on: 2026-11-06
checked_against:
  - live format matrix, lab app ../wappa_examples/instagram_conversations_example (/formats)
  - https://developers.facebook.com/docs/whatsapp/cloud-api/reference/media/
  - https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/messaging-api/
---

# Media formats: what to send on WhatsApp and Instagram

What each Platform really accepts and renders, from Meta's docs **and** a live run of every format (Gate A, 2026-11-06), and which format a Host should prepare for each use. The skills teach the "Recommended formats" table (see the [skills PRD](../developer-experience/261103-mid-instagram-app-skills-and-setup.md), item 15).

**Wappa does not convert media.** Preparing files in a format that fits is the Host's job, usually once, when the asset is stored (a Host that keeps web masters, WebM video and WebP images, stores a messaging rendition next to each). Wappa's part is to know each Platform's rules and refuse a file that does not fit **before any Platform call**, with an error that names the problem; a Meta link it cannot use would otherwise be accepted and fail minutes later.

## Recommended formats

One format per use works on both Platforms, except voice notes and animated stickers, which need a second rendition (`send_sticker` and `send_audio` take `MediaRenditions`, and each Platform picks the file it accepts).

| Use | Universal target | WhatsApp | Instagram | Second rendition |
| --- | --- | --- | --- | --- |
| image (photo) | JPEG | ✅ link and upload | ✅ link and upload | — |
| image (graphic, transparency) | PNG | ✅ (alpha kept) | ✅; alpha becomes white by link, kept by upload | flatten onto a Host background when the look must not depend on the lane |
| image (animated) | none: GIF animates only on Instagram, WhatsApp images cannot animate | send as MP4 video | GIF | yes: MP4 for WhatsApp, GIF for Instagram, or send as video on both |
| video | MP4, H.264 Main (Baseline for old Android), AAC, faststart, ≤ 16 MB | ✅ | ✅ link and upload | — |
| audio | M4A (AAC) | ✅ | listed by Meta; *rendering pending* | — |
| voice | OGG/Opus mono 48 kHz | ✅ the only format with a waveform | not on Instagram's audio list (OGG link *pending*); Instagram has no voice flag | yes: M4A (AAC) for Instagram |
| document | PDF | ✅ | ✅ (the only attachable type; others become a link text) | — |
| sticker (static) | WebP 512×512, ≤ 100 KB | ✅ | ✅ **by URL only** (the upload endpoint answers HTTP 500) | PNG when it must be uploaded to Instagram |
| sticker (animated) | animated WebP 512×512, ≤ 500 KB | ✅ | shows only the first frame | yes: GIF for Instagram |
| card image / card video | JPEG or PNG / MP4 as above, by public URL | ✅ | ✅ (a video card needs `poster_url`, a JPEG) | the poster frame |

In short: **video MP4 (H.264 + AAC), documents PDF, photos JPEG, graphics PNG, audio M4A (AAC), WhatsApp voice notes OGG/Opus, stickers WebP 512×512 plus PNG or GIF for Instagram.** Avoid as messaging formats: WebM, MOV, MKV, HEVC, HEIC, WAV, OGG Vorbis, animated WebP as an image.

## What Wappa refuses before any call

- **WhatsApp** (`wappa/messaging/whatsapp/media_rules.py`, content read by `wappa/domain/media_probe.py`): by suffix, image `.jpg/.jpeg/.png/.webp`, video `.mp4/.3gp`, audio `.aac/.amr/.mp3/.m4a/.ogg`, voice `.ogg`, sticker `.webp`; by content for local files and uploads, animated WebP as an image, GIF, HEIC, HEVC, MOV, WebM, OGG without Opus, WAV, a sticker not 512×512, size caps (image 5 MB, video and audio 16 MB, sticker 500 KB, static sticker 100 KB, document 100 MB); by stored MIME type for a voice note (`audio/ogg`) or sticker (`image/webp`) sent by Media ID; every carousel card.
- **Instagram** (`wappa/messaging/instagram/media.py`): image png/jpeg/gif (and WebP by URL only), audio aac/m4a/wav/mp4, video mp4/ogg/avi/mov/webm by URL, document pdf, image 8 MB and the rest 25 MB; a WebP file (the upload endpoint answers HTTP 500) and animated WebP bytes; a video file other than an H.264 MP4 (MOV and WebM uploads answer HTTP 500, an HEVC upload's send is refused). A document, audio or video **URL** in another format is shared as a text with the file name and link instead of failing.
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

### Instagram (2026-11-06, test account; partial: the development app's rate limit)

API = Meta's response; Instagram sends no `failed` status (every accepted send came back `read`), so the phone is the only verdict. Rendering checked by the tester.

| Use | Works | Fails or degrades | Notes |
| --- | --- | --- | --- |
| image | JPEG, PNG, static GIF, static WebP, HEIC by link; animated GIF **animates** (link and upload) | animated WebP shows only its first frame; PNG with alpha: transparent area filled **white by link**, kept (chat background shows through) **by upload** | a static WebP **upload** answers HTTP 500 ("unknown error", code 1, rerun 14:50) while the same file renders by URL; Wappa now accepts WebP URLs and refuses WebP files and animated WebP bytes before I/O |
| video | MP4 H.264 Baseline and High, link and upload; WebM VP8 and VP9 links accepted (rendering *pending*) | uploads: MOV, WebM VP8 and VP9 answer HTTP **500** (code 1); an HEVC MP4 uploads but its send is refused, 3/1545003 "Public attachments are not allowed to be sent directly"; MKV link: shared as link text (Wappa's rule) | Wappa now refuses every video upload except an H.264 MP4 before I/O; links for HEVC, MOV, 3GP *pending* |
| sticker (sent as image) | PNG 512 (link and upload; same alpha behaviour as images), static WebP 512 and 256 | animated WebP 512 shows its first frame | Instagram has no sticker size rule |
| card_image | JPEG, PNG, PNG with alpha, static WebP, animated WebP (first frame) | — | GIF and video cards *pending* |
| audio and voice (links) | M4A AAC, AAC ADTS, WAV PCM: a voice-note bubble with "View transcription" | MP3, OGG Opus mono and stereo, OGG Vorbis, WebM Opus: outside Instagram's audio list, so Wappa shares each as a text with the file name and link (by design, not a Meta failure) | Instagram has no separate voice-note type: `is_voice` changes nothing, audio and voice render the same; uploads *pending* |
| document | PDF, link and upload | other types by link: shared as a link text (Wappa's rule) | — |

Findings:

- Instagram's verdict is the phone, not a status: accepted sends are `read`, never `failed`, so a format Instagram degrades (animated WebP, alpha) looks like a success to the Host. Only rules enforced before I/O protect the Host.
- Animation: GIF is Instagram's animation format; WhatsApp's is animated WebP (stickers) or MP4 (video). A Host that animates on both ships both renditions.
- Transparency depends on the lane on Instagram (white matte by link, transparent by upload), so a Host that needs a predictable look flattens transparent images onto its own background before sending.
- Audio: M4A (AAC) is the one audio file that plays on both Platforms (WhatsApp audio and Instagram voice bubble). A WhatsApp voice note still needs OGG/Opus, which Instagram does not play, so a Host that sends voice notes on both keeps two renditions (OGG/Opus and M4A).
- An Instagram upload that answers HTTP 500 is a format refusal in practice (MOV, WebM video, WebP image: code 1 "unknown error"), not an outage: MP4 stays the only video upload format until a rerun says otherwise.

## What the skills teach

- Prepare media once, in the recommended format, when the asset is stored; never rely on Meta to convert.
- Ship two renditions only where needed: `send_sticker(["s.webp", "s.gif"])` for an animated sticker, `send_audio(["v.ogg", "v.m4a"], is_voice=True)` for a voice note on both Platforms.
- Prefer upload + Media ID for media sent more than once (WhatsApp Media IDs live 30 days; Meta's URL cache lasts about 10 minutes), except WebP on Instagram, which works only by URL.
- A Meta acceptance is not delivery: on WhatsApp watch `failed` status webhooks (131053) for links; on Instagram there is no failed status, so only the recommended formats are safe.
- Test new formats in small runs: the Instagram development app allows about 10-20 calls per burst before code `4` (`references/rate-limits.md`).
