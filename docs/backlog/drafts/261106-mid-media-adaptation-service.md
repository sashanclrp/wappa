---
status: draft (design proposed 2026-11-06; no code; needs a grill session and an ADR before pending/)
origin: WhatsApp First facade gap for media (send_sticker renditions, carousel card media, voice notes)
checked_on: 2026-11-06
supersedes_on_acceptance: the "Wappa never converts media" rule in wappa/domain/media_renditions.py and docs/public-contract.md (send_sticker paragraph)
last_reviewed: 2026-11-06
---

# Media Adaptation: Wappa detects real media types and adapts media to each Platform

## Code reality (2026-11-06)

Platform-neutral media upload/download and rendition selection exist. Automatic probing, adaptation, worker execution, content-hash caching and public media URLs do not. The one-media-seam hardening does not absorb this service.

The Messenger contract mirrors WhatsApp, and every other Platform's adapter emulates it so a Host never writes Platform-specific code. Media is where that promise breaks today. Each Platform accepts different containers, codecs, sizes and dimensions, and some sends need media in a form the Host never supplied: a public https URL instead of a Media ID, an image instead of a video, a WebP sticker, an OGG/Opus voice note. Wappa checks file extensions only and "never converts media" (`wappa/domain/media_renditions.py`), so the Host has to know every Platform's rules and prepare renditions itself. That is exactly the Platform-specific code Wappa exists to remove.

Media Adaptation adds one Platform-neutral engine that reads what a file really is, compares it with what the Inbox's Platform requires for that use, and converts it only when it does not fit. It runs off the event loop, caches its results, and can publish adapted media at a short-lived Wappa-hosted public URL when a Platform only accepts URLs.

## Today

- Rules live in two shapes: `MediaType.get_supported_mime_types` / `get_max_file_size` in `wappa/messaging/whatsapp/models/media_models.py`, and `MEDIA_RULES` (suffix sets and byte caps) in `wappa/messaging/instagram/media.py`. Both key off the file suffix or a guessed MIME type, never the bytes.
- No rule covers codecs, channels, dimensions, animation, or the "needs a public URL" constraint. A wrong codec fails at Meta (WhatsApp `131053`, or silently unplayable on Android) instead of before I/O.
- `send_sticker` takes `MediaRenditions` and picks the first accepted suffix; the Host must ship `["s.webp", "s.png"]`.
- `send_carousel` takes `MessageCard.header: CardMedia` (`kind` image or video, a public `url`, and `poster_url` for an Instagram video card). Card media is URL-only on both Platforms, because WhatsApp card headers take a public link and no Media ID. Instagram rejects a video card without `poster_url` before any call ("pass poster_url, or enable media adaptation"), and a Host with only a local file cannot build a card at all. This service fills exactly those cases.
- `IMediaLibrary.upload(source: Path | bytes, family, *, mime_type=None, filename=None)` (ADR-0024 draft) uploads whatever it is given. Instagram attachments cannot be downloaded back by ID, so an uploaded `attachment_id` cannot later become a card URL.
- Drift found while checking: Wappa lists `video/3gp`, Meta documents `video/3gpp`; Wappa omits static WebP as a WhatsApp image, which Meta now accepts (and transcodes to JPEG).

## Goals

1. One declared `MediaSpec` per Platform on its `PlatformEntry`, replacing both rule tables, with verified values and a source note.
2. Detection from content (magic bytes, Pillow, PyAV) on every outbound file, so a non-conforming file is refused before any Platform call with an error that says what is wrong and what would fit.
3. With adaptation enabled, a conforming file is produced automatically: transcode, resize, re-encode, poster frame, WebP to PNG/GIF and back, MP3/AAC to OGG/Opus. Conforming input passes through byte-for-byte.
4. CPU work never runs on the event loop; repeated sends of the same content reuse cached results.
5. Wappa can serve adapted media at an unguessable, expiring public URL on the app's existing public base URL, shared across workers.
6. No Host-facing signature changes: `IMessenger` send methods and `IMediaLibrary` keep their shapes; behaviour gets better behind them.

## Non-goals

- No plugin framework, no per-Host custom pipelines, no second engine. One engine, one spec type.
- No document conversion (DOCX to PDF and the like). A document that does not fit is refused.
- No editing for presentation (cropping to a subject, watermarks, thumbnails beyond the poster frame, quality tuning per Host).
- No media hosting product: the public URL exists only so a Platform can fetch a send, and it expires.
- No inbound adaptation. `IMediaLibrary.download` returns the bytes the User sent, unchanged.
- No new Platform behaviour (for example Instagram custom stickers); adaptation only fills existing facades.

## Design

### 1. MediaSpec on the Platform Registry

`PlatformEntry` gains `media_spec: MediaSpec`. `MediaSpec` is a frozen mapping from `MediaUse` to `MediaRule`. `MediaUse` is internal (not Host-facing) because it is finer than the public `MediaFamily`: `image`, `video`, `audio`, `voice`, `document`, `sticker`, `card_image`, `card_video`. `MediaRule` is one frozen dataclass: accepted containers (MIME), accepted video and audio codecs, `max_bytes`, `max_edge` / exact `size` in pixels, color constraints, `animated` (forbidden, allowed, required-limit), `channels` (mono), `delivery` (`media_id | url | url_only`), and a preferred `target` used when adapting (container, codec, encoder settings). The WhatsApp and Instagram tables below become the two specs; `media_models.py` limits and `instagram/media.py` `MEDIA_RULES` are deleted, and their validators read the spec. Platform-specific values live only in `wappa/platforms.py` and the adapter folders, per the registry rule.

WhatsApp Cloud API (Media reference, audio, sticker, image and carousel pages):

| Use | Accepted | Max | Other rules |
| --- | --- | --- | --- |
| image | `image/jpeg`, `image/png`, static `image/webp` (Meta transcodes WebP to JPEG) | 5 MB | 8-bit RGB or RGBA; edge ≤ 4096 px; animated WebP rejected |
| video | `video/mp4`, `video/3gpp` | 16 MB | H.264 video and AAC audio only; one audio stream or none; Meta recommends Main or Baseline profile without B-frames and moov before mdat (High profile with B-frames fails on Android clients) |
| audio | `audio/aac`, `audio/amr`, `audio/mpeg`, `audio/mp4`, `audio/ogg` (Opus only, mono only) | 16 MB | plain `audio/ogg` without Opus is not supported |
| voice | `audio/ogg` with Opus, mono, sent with `voice: true` | 16 MB | play icon only at ≤ 512 KB; other codecs break transcription |
| document | txt, pdf, doc/docx, xls/xlsx, ppt/pptx | 100 MB | no conversion |
| sticker | `image/webp` | 100 KB static, 500 KB animated | 512×512 is **unverified** on the Cloud API pages (it comes from WhatsApp's sticker-app guidelines and third parties; `docs/public-contract.md` already states it) |
| card_image / card_video | image or video header by `link` | as image / video | the interactive media carousel documents only a public `link`, no Media ID |

Expiry facts the engine and cache rely on: Media URLs returned by `GET /{media-id}` expire after 5 minutes; uploaded Media IDs and files last 30 days; webhook Media IDs 7 days. Link media is cached by Meta for 10 minutes per identical URL; a `Content-Type` header is required on the response. Header-driven "Media HTTP Caching" exists but its headers were **not verified**.

Instagram messaging (Instagram API with Instagram Login on `graph.instagram.com`, and via Facebook Login on `graph.facebook.com`, which is what Wappa uses):

| Use | Accepted | Max | Other rules |
| --- | --- | --- | --- |
| image (and sticker, sent as image) | png, jpeg; gif per the Attachment Upload page | 8 MB | GIF is inconsistent across pages (**verify live**); WebP is not documented anywhere (treat as not accepted); the only native sticker is `like_heart` |
| video | mp4, ogg, avi, mov, webm | 25 MB | no codec rules documented (**unverified**; target H.264/AAC mp4 when adapting) |
| audio / voice | aac, m4a, wav, mp4 | 25 MB | no voice flag; MP3 and OGG are not listed, so they adapt to m4a (AAC) |
| document | pdf | 25 MB | other documents are refused |
| card_image | generic template `elements[].image_url` | as image | public URL; no video slot; no documented aspect ratio (Messenger renders 1.91:1 by default; `image_aspect_ratio` reportedly errors on Instagram, third-party sources only, **unverified**) |

Upload and download: `POST /{id}/message_attachments` with `platform=instagram` and `is_reusable=true` returns an `attachment_id` (by URL or `filedata`). No endpoint returns an attachment's bytes, and the Instagram pages state no attachment expiry (Messenger documents 90 days; **unverified for Instagram**). Inbound attachment URLs are signed CDN URLs; their lifetime is **not documented** (Wappa's code notes "may expire within minutes").

### 2. The MediaAdapter engine

One module, `wappa/media/` (Platform-neutral; it imports no adapter and never reads `PlatformType`). Three steps, each testable alone:

- `probe(source) -> MediaProbe`: magic bytes first (a small in-tree signature table: JPEG, PNG, GIF, WebP static/animated, ISO-BMFF mp4/m4a/mov/3gp, Matroska/WebM, OGG, WAV, MP3, AMR, PDF, OOXML zip, OLE). Then Pillow (already a core dependency) for image size, mode, bit depth, frame count. Then PyAV, when installed, for streams, codecs, profile, B-frames, channels, duration, bitrate and moov position. A declared MIME or suffix that contradicts the bytes is recorded and the bytes win.
- `plan(probe, rule) -> Conforms | Adapt(steps) | Unfixable(reason)`: pure function, no I/O. This is where every decision is made and every test pins behaviour.
- `adapt(source, plan) -> AdaptedMedia(path, mime, probe)`: executes the steps, re-probes the output and fails if the output still does not conform.

Adaptations, all driven by `MediaRule.target`:

| From | To | When |
| --- | --- | --- |
| any decodable image (WebP, HEIC if Pillow can read it, BMP, TIFF, 16-bit, CMYK) | JPEG, or PNG when alpha matters | container or color not accepted |
| oversize image | downscale to `max_edge`, then a JPEG quality ladder | edge or bytes over the rule |
| image (static) | 512×512 static WebP, fit with transparent padding, ≤ 100 KB | `sticker` on WhatsApp |
| animated GIF / APNG / short WebM | animated WebP ≤ 500 KB (frame-rate and palette ladder) | animated `sticker` on WhatsApp |
| WebP static / animated | PNG / GIF | sticker or image on Instagram |
| video in another codec, container or profile | H.264 Main, AAC, mp4 with faststart, one audio stream | `video` rule mismatch |
| oversize video | bitrate capped from duration; refuse when the floor still does not fit | bytes over the rule |
| video | the frame at 1 second as JPEG (the poster; see Poster frame below) | `card_image` needed but the card has video (Instagram, or a missing `poster_url`) |
| MP3, AAC, WAV, stereo Opus | OGG/Opus mono (48 kHz, voice bitrate) | `voice` on WhatsApp |
| OGG, MP3, WebM audio | m4a (AAC) | `audio` / `voice` on Instagram |

Host-supplied renditions still win: `send_sticker(["s.webp", "s.png"])` keeps working and is adapted only when no rendition conforms. A Media ID input passes through untouched (it already lives on that Platform). A remote URL input passes through unless its probe is wanted; fetching it is a knob (section 7) because it turns Wappa into a URL fetcher.

### 3. Background execution and caching

- Probing an image header runs in `asyncio.to_thread`. Decoding and encoding run in one app-wide `ProcessPoolExecutor` (spawn context, `max_tasks_per_child`, default 1 worker per Hypercorn worker), started lazily on first use and shut down with the app lifespan.
- Each job has a timeout. On timeout the pool is terminated and recreated, since a running process-pool job cannot be cancelled; the send returns an outcome instead of hanging. A semaphore caps queued jobs; past the cap a send fails fast as unavailable rather than piling up.
- Input caps before any decode: `max_input_bytes`, max pixels (Pillow decompression-bomb limit kept on), max duration.
- Result cache keyed by `(sha256(content), rule fingerprint, engine version)` holds the adapted bytes in the MediaStore (section 4) with a TTL. A second key `(InboxRef, content hash, MediaUse)` holds the Platform Media ID returned by a previous upload, with a TTL under the Platform's expiry (WhatsApp 29 days; Instagram a conservative 7 days until verified). Same content to the same Inbox therefore uploads once.
- Pre-adaptation at upload: `IMediaLibrary.upload(path, family)` adapts for that Inbox's spec before uploading and also stores the adapted bytes keyed by the returned Media ID. That is the only way an Instagram `attachment_id` can later become a card URL, since Instagram offers no download.

### 4. Wappa-hosted public media URLs

- Route: `GET /media/public/{token}` (and `HEAD`), mounted on the existing app beside the webhook routes. It is a service route, so an embedding Host keeps it. The base comes from a new `SYSTEM_PUBLIC_BASE_URL` (the same https origin Meta already reaches for webhooks); without it, any send that needs a URL fails before I/O with a message naming the setting.
- Token: 256 random bits, base64url. It is an opaque capability looked up in the store, not a signed payload. The bytes have to be stored anyway, so a stored record costs nothing and allows early revocation; an HMAC-signed stateless token would add a secret to manage for no gain. Record: content hash, pinned content type, size, `expires_at`, optional filename.
- Storage: one small `MediaStore` (put, get, delete with TTL) with two implementations: a directory (default, single host or a shared volume) and Redis when `REDIS_URL` is set (per-object cap, default 16 MB). Workers on several hosts must use Redis or a shared volume; the directory store refuses to start in Redis routing setups that imply several hosts (open question).
- Response: the pinned `Content-Type` from the probe (never from the token or a query), `Content-Length`, `X-Content-Type-Options: nosniff`, `Content-Disposition: inline` for media and `attachment` for documents, `Referrer-Policy: no-referrer`, `Cache-Control: public, max-age=` the remaining TTL. Single-range `Range` support for video, since Meta's fetcher may use it (**unverified**).
- Safety: unknown, expired and malformed tokens all return the same `404` with no body difference and constant-time lookup; no index, no listing, no path segments beyond the token; size served is capped by the record; tokens and URLs are never logged in full (prefix only).
- TTL: default 1 hour for message media (Meta fetches at send). Card images get a longer default (7 days) because it is **unverified** whether Instagram copies `image_url` at send or re-fetches it when the thread renders; if it re-fetches, an expired card image breaks old carousels. Gate on a live check.

### 5. Where it plugs in

- Each adapter calls the engine at its existing resolve step, before any upload or send: `WhatsAppMessenger._resolve_media_object` and the Instagram local-path upload path, plus both `IMediaLibrary.upload` implementations. The call is `prepare(source, use, spec) -> PreparedMedia` with `PreparedMedia` being a local path, a cached Media ID, or a public URL, depending on `MediaRule.delivery`.
- `send_audio(..., is_voice=True)` selects `MediaUse.voice`; `send_sticker` selects `sticker`; carousel cards select `card_image` / `card_video`.
- Carousel: card media is `url_only` on both Platforms, so a Host with only a local file gets a public URL from section 4 and passes it as `CardMedia.url`. When an Instagram card carries video and `poster_url` is empty, Wappa produces the poster automatically: download the video from `CardMedia.url` (bounded by the card_video rule's `max_bytes`), extract the poster frame, encode it as JPEG to the `card_image` rule, publish it at a section 4 public URL, and send that URL as the element's `image_url`; tapping the card opens `CardMedia.url`. A Host-supplied `poster_url` always wins, and the poster is cached by (video content hash, rule), so the same video sent to many Users is processed once. With adaptation off, the clear pre-send rejection stays. The URL-only `CardMedia(kind, url, poster_url)` card contract is in place; this PRD adds no card fields itself.
- `IMessenger` and `IMediaLibrary` signatures do not change. `pick_rendition` stays as the first step, and its docstring loses "Wappa never converts media".

### 6. Packaging

- Core (no extra): the magic-byte table plus Pillow give detection for every family, and image, sticker and poster-from-image adaptation. Video and audio codec checks report "unverified" without PyAV and do not reject on codec alone, so sends that work today keep working.
- `wappa[media]` adds `av` (PyAV, Python ≥ 3.12, binary wheels with FFmpeg bundled). It is the first `[project.optional-dependencies]` entry in `pyproject.toml`. Adaptation is off by default even when installed; `SYSTEM_MEDIA_ADAPT=1` turns it on. With adaptation off, detection still refuses non-conforming media before upload with a clear `ValueError`.
- License, **must verify before release**: PyAV itself is BSD-3. The pyav-ffmpeg build script enables `libx264` and `libx265` and `--enable-version3`; x264 and x265 are GPL, and FFmpeg normally requires `--enable-gpl` to link them, so the bundled FFmpeg is likely GPL, not LGPL. Wappa only declares a dependency and does not redistribute FFmpeg, but Hosts that ship images (Docker) do distribute it. Options: accept and document GPL for the extra, or encode H.264 through a system FFmpeg or OpenH264 build. Decide in the ADR.

### 7. Configuration, observability, failure outcomes

| Setting | Default | Meaning |
| --- | --- | --- |
| `SYSTEM_MEDIA_ADAPT` | off | adapt non-conforming media; off means detect and refuse |
| `SYSTEM_MEDIA_WORKERS` | 1 | process-pool size per app worker |
| `SYSTEM_MEDIA_JOB_TIMEOUT_SECONDS` | 60 | per adaptation job |
| `SYSTEM_MEDIA_MAX_INPUT_BYTES` | 100 MB | refuse larger inputs before decode |
| `SYSTEM_MEDIA_FETCH_URLS` | off | fetch Host URLs to probe and adapt them (unauthenticated media client, https only, public addresses only, size-capped) |
| `SYSTEM_PUBLIC_BASE_URL` | unset | origin for `/media/public/{token}`; unset disables public URLs |
| `SYSTEM_MEDIA_URL_TTL_SECONDS` / `SYSTEM_MEDIA_CARD_URL_TTL_SECONDS` | 3600 / 604800 | public URL lifetimes |
| `SYSTEM_MEDIA_STORE_DIR` | `./.wappa/media` | directory store; Redis is used when `REDIS_URL` is set |

Logs (secret-free, no bytes, token prefix only): one `MEDIA_PROBE` line per file at debug; `MEDIA_ADAPTED` at info with use, from/to MIME and codecs, sizes, duration in ms, and cache hit; `MEDIA_REFUSED` at warning with the reason; `MEDIA_CODEC_UNVERIFIED` once per process when PyAV is absent. Counters for adaptations, cache hits, timeouts and pool restarts go through the existing logger; no metrics backend is added.

Failures reuse existing outcomes, with no new result type:

- Local rule violation that cannot or may not be adapted (wrong family, document type, detection-only mode, `Unfixable`): `ValueError` before I/O, HTTP 400, per ADR-0021 and ADR-0024. The message names the detected type, the rule and the fix (for example "install wappa[media] and set SYSTEM_MEDIA_ADAPT=1").
- Adaptation timed out, pool restarting, or queue full: `MessageResult` / `UploadResult` `REJECTED` with `error_code="MEDIA_UNAVAILABLE"` and no Platform call. `IMediaLibrary.download` is unaffected.
- Public URL needed but `SYSTEM_PUBLIC_BASE_URL` unset: `ValueError`.
- Platform refuses an adapted file anyway: the Platform's own `REJECTED` result, with `platform_response` kept, plus a `MEDIA_ADAPTED` log line so the mismatch can be traced to a spec value.

### 8. Test plan

Offline, on fixtures checked into `tests/fixtures/media/` (each a few KB, generated once by a script kept beside them): JPEG, PNG with alpha, 16-bit PNG, CMYK JPEG, static and animated WebP, animated GIF, oversize-edge PNG, MP4 H.264 Baseline, MP4 H.264 High with B-frames, MP4 HEVC, MOV, WebM VP9, MP3, AAC, WAV, stereo OGG/Opus, mono OGG/Opus, OGG Vorbis, AMR, PDF, DOCX, a file whose suffix lies, a truncated file.

- `probe`: every fixture detected from bytes, suffix lies ignored.
- `plan`: a table-driven suite over (fixture, WhatsApp spec, Instagram spec, every `MediaUse`) asserting Conforms / Adapt(steps) / Unfixable. Pure, fast, no PyAV needed where the probe is recorded.
- `adapt` (skipped when `av` is not importable, run in CI with the extra): output re-probes as conforming; sticker ≤ 100 KB / 500 KB at 512×512; voice note is mono Opus; video is H.264/AAC faststart; poster is the frame at 1 second, or the first decodable frame for a clip shorter than 1 second.
- Spec tests pin each table row and fail when a value changes without its source note changing.
- Executor: timeout restarts the pool and returns `MEDIA_UNAVAILABLE`; queue cap; no event-loop blocking (a slow fake job does not delay a concurrent coroutine).
- Cache: same content and rule hit; changed rule fingerprint misses; Media ID cache is Inbox-scoped and never crosses Inboxes or Platforms.
- MediaStore: one parameterized suite over the directory and Redis (fake) stores, per the cache contract pattern.
- Public route: valid token serves pinned type and headers; expired, unknown and malformed tokens give identical 404s; no listing; HEAD and Range; token not logged.
- Messenger parity: the existing parity and pipeline suites gain cases showing that WhatsApp and Instagram given the same Host call produce conforming payloads, with fake HTTP only.

Live checks (added to the live test plan, run by hand on test Inboxes, never in CI): WhatsApp voice note from an MP3 shows the waveform and transcription; WhatsApp sticker from a PNG and from a GIF; WhatsApp High-profile MP4 plays on Android after adaptation; WhatsApp and Instagram carousels from local files and from Media IDs; Instagram card with video shows the poster; Instagram GIF image and WebP-as-image behaviour; whether an Instagram card image still renders after its public URL expires; whether Meta's fetcher uses `Range`.

### 9. Phased rollout

1. Detection (no new dependency): `MediaSpec` on `PlatformEntry`, the two verified specs, `probe` with magic bytes and Pillow, `plan`, refusal errors before I/O, the `3gpp` and static-WebP drift fixes. Breaking only where a lying suffix used to slip through; listed in the CHANGELOG.
2. Adaptation: the `wappa[media]` extra, `adapt`, the process pool, the content cache and the Media ID cache, pre-adaptation in `IMediaLibrary.upload`. Off by default.
3. Public URLs: `MediaStore`, `/media/public/{token}`, `SYSTEM_PUBLIC_BASE_URL`, carousel filling with the URL-only `CardMedia(kind, url, poster_url)` card contract. Gate on the Instagram re-fetch live check.

Each phase updates `docs/public-contract.md`, both `ARCHITECTURE.md` files, `CONTEXT.md` (new terms: Media Spec, Media Use, Media Adaptation, Public Media URL) and the CHANGELOG in the same change; phase 1 lands with the ADR that retires "Wappa never converts media".

### Poster frame

When a video card has no `poster_url`, the poster is the frame at **1 second** (a seek by timestamp, not by frame index, because frame rates vary: 1 second is frame 30 at 30 fps and frame 25 at 25 fps). The first frame is often black or a fade-in, so it is used only when the clip is shorter than 1 second. If the frame at 1 second is near-black (mean luminance below a small threshold), the engine tries 2 seconds, then falls back to the first decodable frame. The poster keeps the video's aspect ratio, is scaled to the `card_image` rule, and is encoded as JPEG. The whole step (download, decode, encode, publish) runs in the background pool under the same per-job timeout and cache as every other adaptation, and its failure returns the same pre-send rejection as adaptation off, so a send never half-completes.

## Open questions

- License of the bundled FFmpeg in PyAV wheels (likely GPL through x264/x265): accept for the opt-in extra, or require a system FFmpeg or OpenH264 for H.264 encoding?
- Does Instagram copy `image_url` at send, or hotlink it at render? This sets the card URL TTL, and possibly whether card images must be permanent.
- Is GIF accepted as an Instagram image on the Facebook Login path, and is WebP silently accepted or refused?
- Instagram `attachment_id` lifetime (Messenger documents 90 days): what TTL is safe for the Media ID cache?
- WhatsApp sticker dimensions: is 512×512 enforced by the Cloud API, or only advised?
- Poster frame: decided 2026-11-06, see Poster frame.
- Should `SYSTEM_MEDIA_FETCH_URLS` exist at all, or should Host URLs always pass through untouched?
- Multi-host deployments without Redis: refuse public URLs at startup, or document a shared volume as the requirement?
- Does `MediaUse` stay internal, or should `MediaFamily` gain `STICKER` / `VOICE` so `IMediaLibrary.upload` can pre-adapt for those uses (a public contract change)?

## Exit criteria

- Both Platform specs live on `PlatformEntry`, cite their sources, and are the only media rule tables in the tree.
- A Host can send an MP3 as a WhatsApp voice note, a PNG as a WhatsApp sticker, a WebP as an Instagram sticker, an HEVC MP4 as a WhatsApp video, and a carousel from local files on both Platforms, with no Platform-specific code and no signature changes.
- With adaptation off, every non-conforming file is refused before I/O with an actionable message.
- No adaptation runs on the event loop; offline suites cover probe, plan, adapt, cache, store and route; live checks are recorded in the live test plan.
- ADR accepted; public contract, architecture docs, glossary and CHANGELOG updated.

## Sources (checked 2026-11-06)

- WhatsApp supported media, sizes, codecs, expiry: https://developers.facebook.com/docs/whatsapp/cloud-api/reference/media
- WhatsApp audio and voice messages: https://developers.facebook.com/docs/whatsapp/cloud-api/messages/audio-messages
- WhatsApp sticker messages: https://developers.facebook.com/docs/whatsapp/cloud-api/messages/sticker-messages
- WhatsApp interactive media carousel (link-only card headers): https://developers.facebook.com/documentation/business-messaging/whatsapp/messages/interactive-media-carousel-messages
- WhatsApp link media caching (10 minutes) and Content-Type requirement: https://developers.facebook.com/docs/whatsapp/cloud-api/reference/messages/
- Instagram API with Instagram Login, messaging: https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/messaging-api
- Instagram messaging via Messenger Platform, send message: https://developers.facebook.com/docs/messenger-platform/instagram/features/send-message
- Instagram attachment upload (`message_attachments`, `is_reusable`, GIF): https://developers.facebook.com/documentation/business-messaging/instagram-messaging/features/attachment-upload
- Instagram generic template: https://developers.facebook.com/docs/messenger-platform/instagram/features/generic-template
- PyAV installation (Python ≥ 3.12, FFmpeg bundled): https://pyav.basswood.io/docs/stable/overview/installation.html
- pyav-ffmpeg enabled libraries and build flags: https://github.com/pyav-org/pyav-ffmpeg and https://raw.githubusercontent.com/PyAV-Org/pyav-ffmpeg/main/scripts/build-ffmpeg.py
