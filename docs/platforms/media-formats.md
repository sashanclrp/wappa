---
checked_on: 2026-11-06
checked_against:
  - live format matrix, lab app ../wappa_examples/instagram_conversations_example (/formats)
  - https://developers.facebook.com/docs/whatsapp/cloud-api/reference/media/
  - https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/messaging-api/
---

# Media format evidence

Authoritative live format results from 2026-11-06, used to derive the shipped [media preparation guide](../../wappa/cli/skills/wappa-apps/references/media-formats.md). That guide owns recommended formats, per-Platform caps and preparation instructions; the [public contract](../public-contract.md#messenger-operations-one-method-per-action-adr-0025) owns validation and send behavior. Wappa does not convert media; the Host Application prepares renditions.

The tables distinguish Meta acceptance, status webhooks and phone rendering. They record the format tests, including raw calls that bypassed Wappa validation; accepted test formats are not necessarily recommended or permitted by Wappa. Local validation is implemented in `wappa/messaging/whatsapp/media/rules.py`, `wappa/messaging/instagram/media/rules.py` and `wappa/domain/media_probe.py`. Extension-less URLs and most Media IDs provide no format/codec evidence for validation without fetching; WhatsApp voice/sticker IDs are checked against stored MIME.

Source note, 2026-11-06: the original Host guidance preferred reusable WhatsApp Media IDs, citing a 30-day Media ID lifetime and roughly 10-minute Meta URL caching. These lifetimes have no separate live confirmation in this record; unverified since 2026-11-06.

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

- A link is accepted (200) and fails later for every unsupported format: the verdict arrives as a status webhook, seconds to minutes later (a HEIC link that Meta could not fetch failed after 6 minutes with "http code 503"). Only refusal before I/O gives the Host a synchronous answer, so Wappa enforces these rules at send time (`wappa/messaging/whatsapp/media/rules.py`).
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
