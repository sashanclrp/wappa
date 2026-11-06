---
status: draft (design proposed 2026-11-06; no code; needs a grill session and an ADR before pending/)
origin: WhatsApp First facade gap for media (send_sticker renditions, carousel card media, voice notes)
checked_on: 2026-11-06
supersedes_on_acceptance: the "Wappa never converts media" rule in wappa/domain/media_renditions.py and docs/public-contract.md (send_sticker paragraph)
last_reviewed: 2026-11-06
---

# Media Adaptation: Wappa detects real media types and adapts media to each Platform

## Code reality (2026-11-06)

Platform-neutral media upload/download and rendition selection exist. Since 2026-11-06 a first slice of phase 1 exists for WhatsApp: `wappa/domain/media_probe.py` reads the real type from the bytes (magic bytes and container headers, no dependency: animated WebP, OGG Opus vs Vorbis, HEVC vs H.264, WebP and PNG dimensions), and `wappa/messaging/whatsapp/media_rules.py` refuses before any call every case the live matrix showed Meta accepting and then failing. Adaptation, worker execution, content-hash caching, public media URLs, the shared `MediaSpec` and the Instagram side do not exist yet. The one-media-seam hardening does not absorb this service.

The Messenger contract mirrors WhatsApp, and every other Platform's adapter emulates it so a Host never writes Platform-specific code. Media is where that promise breaks today. Each Platform accepts different containers, codecs, sizes and dimensions, and some sends need media in a form the Host never supplied: a public https URL instead of a Media ID, an image instead of a video, a WebP sticker, an OGG/Opus voice note. Wappa checks file extensions only and "never converts media" (`wappa/domain/media_renditions.py`), so the Host has to know every Platform's rules and prepare renditions itself. That is exactly the Platform-specific code Wappa exists to remove.

Media Adaptation adds one Platform-neutral engine that reads what a file really is, compares it with what the Inbox's Platform requires for that use, and converts it only when it does not fit. It runs off the event loop, caches its results, and can publish adapted media at a short-lived Wappa-hosted public URL when a Platform only accepts URLs.

## Today

- Rules live in three shapes: `MediaType.get_supported_mime_types` / `get_max_file_size` in `wappa/messaging/whatsapp/models/media_models.py` (the upload allow-list), `RULES` in `wappa/messaging/whatsapp/media_rules.py` (suffix, MIME from the bytes, size and content checks per use, from the live matrix), and `MEDIA_RULES` (suffix sets and byte caps) in `wappa/messaging/instagram/media.py`. Instagram still keys off the suffix only. Phase 1 folds all three into one `MediaSpec` per Platform.
- WhatsApp now covers animation (WebP), codec (HEVC, OGG Vorbis), sticker dimensions and byte caps for local files and uploads, by suffix for URLs, and the stored MIME type for voice notes and stickers by Media ID. Still uncovered: channels, Instagram's codec rules, a remote URL's real content (no fetch), and the "needs a public URL" constraint.
- `send_sticker` takes `MediaRenditions` and picks the first accepted suffix; the Host must ship `["s.webp", "s.png"]`.
- `send_carousel` takes `MessageCard.header: CardMedia` (`kind` image or video, a public `url`, and `poster_url` for an Instagram video card). Card media is URL-only on both Platforms, because WhatsApp card headers take a public link and no Media ID. Instagram rejects a video card without `poster_url` before any call ("pass poster_url, or enable media adaptation"), and a Host with only a local file cannot build a card at all. This service fills exactly those cases.
- `IMediaLibrary.upload(source: Path | bytes, family, *, mime_type=None, filename=None)` (ADR-0025) uploads whatever it is given. Instagram attachments cannot be downloaded back by ID, so an uploaded `attachment_id` cannot later become a card URL.
- Drift found while checking: Wappa listed `video/3gp`, Meta documents `video/3gpp` (fixed); Python guesses `audio/3gpp` for `.3gp`, so a 3GP video upload failed until ef05128; static WebP works as a WhatsApp image (verified live).

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
| sticker | `image/webp` | 100 KB static, 500 KB animated | exactly 512×512, verified live 2026-11-06 (a 256×256 WebP failed with 131053 "expected dimension: 512x512" on both lanes) |
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

### Optimal target per scenario (from the live matrix, 2026-11-06)

The engine converts to the cheapest format that was **verified live** for that Platform and use, and never to a format that only Meta's docs list. "Verified" means accepted, delivered, and rendered correctly on the phone. Instagram cells marked *pending* wait for the Instagram run (the first one hit the app rate limit, see `references/rate-limits.md` in the Instagram PRD).

| Use | Input that fails | WhatsApp target (verified) | Instagram target |
| --- | --- | --- | --- |
| image | GIF (static) | PNG (lossless; JPEG when there is no alpha and the file is a photo) | as-is: GIF static was accepted |
| image | GIF animated, animated WebP | first frame as PNG for an image; or MP4 H.264 when the Host asked for motion (send as video) | upload accepted, link rejected (400): *pending* rendering |
| image | HEIC / HEIF, AVIF | JPEG | JPEG (HEIC rejected, 400) |
| image | static WebP | as-is (works) | as-is by link (accepted, read); upload refused by Wappa's rule: *pending* rendering |
| image | over 5 MB (WhatsApp) / 8 MB (Instagram), edge over 4096 px | downscale, then JPEG quality ladder | same, 8 MB cap |
| video | HEVC in MP4, MOV, MKV, WebM VP8/VP9 | MP4, H.264 Main (Baseline for old Android), AAC, faststart, one audio stream | MP4 H.264 (the only format accepted so far; MOV and WebM *pending*, first run rate-limited) |
| video | 3GP H.264 | as-is (works once sent as `video/3gpp`) | MP4 (3GP link rejected) |
| video | over 16 MB (WhatsApp) / 25 MB (Instagram) | bitrate ladder from duration; refuse below the floor | same, 25 MB |
| audio | WAV, WebM Opus, OGG Vorbis | MP3 or M4A (AAC); OGG/Opus also works | M4A (AAC) |
| voice | MP3, M4A, AAC, WAV, WebM, OGG Vorbis | OGG/Opus mono, 48 kHz: the **only** format that renders a waveform (MP3/M4A/AAC deliver as a voice bubble without one) | M4A (AAC); Instagram has no voice flag |
| sticker | PNG, JPEG, GIF | WebP 512x512 (fit with transparent padding), ≤ 100 KB static | PNG (sent as an image) |
| sticker | WebP not 512x512 (256x256 failed: "expected dimension: 512x512") | resize and pad to 512x512 WebP | PNG |
| sticker | animated GIF / APNG / short video | animated WebP 512x512 ≤ 500 KB (frame-rate and palette ladder) | GIF (*pending*) |
| card_image / card_video | any of the image or video failures above | same target as image or video; check every card, one bad card fails the whole carousel | image or poster frame (JPEG) |
| document | — | as-is (PDF, DOCX, XLSX, TXT all delivered) | PDF only; another type is shared as a link text |

Rules the engine must follow, all from the matrix:

- **Refuse or adapt before I/O.** A link Meta cannot use is still answered 200; the failure arrives later as a status webhook (seconds to minutes; a HEIC link failed after 6 minutes). Only a check before the call gives the Host a synchronous answer.
- **Probe the bytes, not the name.** Three failures are invisible to a suffix: animated vs static WebP, OGG Vorbis vs Opus, sticker dimensions. HEVC hides inside a valid `.mp4`.
- **Prefer upload + Media ID** for anything sent more than once: Meta recommends it for throughput, the URL cache lasts only 10 minutes, and a Media ID survives 30 days.
- **Check Media IDs where the use is narrower than the upload.** A PNG uploads fine as an image, then fails as a sticker; an MP3 uploads as audio, then has no waveform as a voice note. WhatsApp checks the stored MIME type for voice notes and stickers today.
- **Mind rate limits.** Adaptation must not multiply calls: one upload per content hash per Inbox, reuse the Media ID; Instagram allows 10 audio/video sends per second per account and an app-level hourly budget.

Host-supplied renditions still win: `send_sticker(["s.webp", "s.png"])` keeps working and is adapted only when no rendition conforms. A Media ID input passes through untouched (it already lives on that Platform). A remote URL input passes through unless its probe is wanted; fetching it is a knob (section 7) because it turns Wappa into a URL fetcher.

### 3. Background execution and caching

- Probing an image header runs in `asyncio.to_thread`. Decoding and encoding run in one app-wide `ProcessPoolExecutor` (spawn context, `max_tasks_per_child`, default 1 worker per Hypercorn worker), started lazily on first use and shut down with the app lifespan.
- Each job has a timeout. On timeout the pool is terminated and recreated, since a running process-pool job cannot be cancelled; the send returns an outcome instead of hanging. A semaphore caps queued jobs; past the cap a send fails fast as unavailable rather than piling up.
- Input caps before any decode: `max_input_bytes`, max pixels (Pillow decompression-bomb limit kept on), max duration.
- Result cache keyed by `(sha256(content), rule fingerprint, engine version)` holds the adapted bytes in the MediaStore (section 4) with a TTL. The Platform Media ID returned by a previous upload is held separately, per Inbox, in the Media ID cache (Redis DB 6; see Media ID cache below). Same content to the same Inbox therefore uploads once.
- Read only what a job needs. A poster frame does not need the whole video: PyAV opens the source over HTTP (or from S3) and either seeks with `Range` requests (MP4 with the `moov` index at the front) or decodes sequentially from the start (WebM, whose cues often sit at the end), so a poster at 1 second reads the container header plus the first second of data, typically 1-3 MB of a 20 MB file, in memory with no disk write. Only when the source refuses `Range` and the index is at the end does the job stream to a temp file under the size cap, extract, and delete it immediately (seconds, not minutes). The one path that needs the whole file is reusing a Media ID across Platforms (download from one Platform, upload to another), bounded by WhatsApp's 16 MB video cap and deleted right after upload.
- Cache first, regenerate on miss. Every derived artifact (poster, adapted sticker, transcoded audio) is reproducible from a durable source (the Host's URL, its S3 object, or bytes Wappa uploaded), so the cache is cache-aside with regeneration: look up `media:{content hash}:{rule}`; on a hit, serve; on a miss, take a single-flight lock (`SET media:lock:{key} NX EX 30`), regenerate, re-store with its TTL, release. Concurrent misses for the same key wait on the lock and reuse the result instead of all regenerating (no thundering herd when a campaign of thousands of sends misses at once). A Redis flush or expiry mid-campaign therefore costs one regeneration per artifact, never a failed send.
- Campaigns upload once. For media that does not need a URL (template headers, ordinary media messages), the cheapest path is Meta's own Media ID: upload once per Inbox, cache the ID (WhatsApp IDs live 30 days; Instagram `is_reusable` attachment IDs), and every send references the ID, so neither S3 nor Redis nor Wappa's public route is touched per message. The Media ID cache (below) is tried before any URL path. Only carousel cards, which accept URLs only, need the public-URL path.
- Pre-adaptation at upload: `IMediaLibrary.upload(path, family)` adapts for that Inbox's spec before uploading and also stores the adapted bytes keyed by the returned Media ID. That is the only way an Instagram `attachment_id` can later become a card URL, since Instagram offers no download.

### Media ID cache (per Inbox) — UNDECIDED: Wappa's job or the Host's?

**Status: open decision, to settle in the grill session before this PRD moves to pending.** The design below describes the Wappa-owned option; it is not yet accepted.

What it is: after an upload, Meta returns a Media ID that the same Inbox can reuse for 30 days (WhatsApp). The cache remembers "this exact file, adapted for this use, was already uploaded for this Inbox: its ID is X", so a campaign of 10,000 sends with the same header video uploads once instead of 10,000 times.

| Option | How it works | For | Against |
| --- | --- | --- | --- |
| **A. Wappa owns it (automatic)** | Adapters consult the cache before every upload; described below | Facade: Hosts never think about uploads; Wappa already knows the Inbox lifecycle (disconnect, credential rotation, `evict_inbox`) needed to invalidate IDs, and the content hash of the adapted bytes, which only Wappa computes; self-healing re-upload on an expired ID is natural in the adapter | Wappa takes on another stateful cache, its storage, TTLs and failure modes; more surface in a library |
| **B. The Host owns it (primitives only)** | Wappa already offers the primitives: `IMediaLibrary.upload(...)` returns the Media ID, and every `send_*` accepts a Media ID. A Host such as Symphonai uploads its campaign assets once and stores the IDs in its own database next to the campaign | Nothing new in Wappa; campaigns, assets and their lifetimes are Host business concepts; the Host decides persistence | Every Host reimplements it; the Host must handle ID expiry and Inbox credential rotation itself; when adaptation changes the bytes, the Host must upload through Wappa to get the ID of the adapted file |
| **C. Both: primitives plus an opt-in Wappa cache** | B by default; A behind a setting | Simple Hosts get A, Hosts with their own asset store use B | Two paths to document and test |

Storage, if A or C: one Redis pool or two. The separate `media_ids` pool on DB 6 shown below is also **undecided**: Redis eviction is per instance, not per DB, and both key families can live in the `media` pool on DB 5 with `decode_responses=False` (the JSON record decoded by the cache class), separated by `KeyFactory` prefixes (`media:...` for bytes, `{inbox}:mediaid:...` for IDs). The leaning is one pool unless the grill session finds a reason for two.


The Media ID cache is the critical cache: it is what makes a campaign of thousands of sends cost one upload. It is per Inbox by construction, because a Media ID belongs to the Inbox (WhatsApp phone number, Instagram account) whose token uploaded it and is meaningless on any other Inbox or Platform.

- **Pool:** a new `media_ids` alias on **DB 6**, beside the media-bytes pool on DB 5, following the one-pool-per-logical-DB convention in `wappa/persistence/redis/redis_client.py` (`users` 0, `state_handler` 1, `table` 2, `expiry` 3, `ai_state` 4, `media` 5, `media_ids` 6). It stays separate from DB 5 because the two differ in every dimension: DB 5 holds binary bytes for minutes (`decode_responses=False`), DB 6 holds small JSON records for days (`decode_responses=True`, like the existing pools); flushing ephemeral media bytes must never drop the IDs a running campaign depends on, and losing an ID costs a re-upload while losing bytes costs a regeneration.
- **Keys:** built only by the existing `KeyFactory` (`wappa/persistence/redis/redis_handler/utils/key_factory.py`), never by f-strings in callers. It gains `media_id_prefix = "mediaid"`, `media_id(inbox, use, content_key)` returning `{inbox}:mediaid:{use}:{content_key}`, and `media_id_pattern(inbox, use=None)` for SCAN, using the same `_segment` / `glob_escape` rules as every other pattern. `inbox` is always `InboxRef.cache_namespace` (`<platform>__<inbox_id>`), so a key can never collide across Inboxes or Platforms (Inbox Namespace rule in `wappa/persistence/CONTEXT.md`). `content_key` is `sha256(adapted bytes)` plus the rule fingerprint, so the same source adapted differently for two uses gets two IDs.
- **Value:** a small JSON record: `media_id`, `platform`, `mime_type`, `size`, `uploaded_at`, `expires_at`, `rule_fingerprint`, `engine_version`.
- **TTL:** set per Platform from its `MediaSpec` (`media_id_ttl`), always under the Platform's own expiry: WhatsApp uploaded Media IDs last 30 days, so 29 days; Instagram `is_reusable` attachment IDs use a conservative 7 days until the lifetime is verified (Messenger documents 90 days).
- **Single flight:** concurrent sends of the same new content take `SET {key}:lock NX EX 30` before uploading; the others wait and read the ID, so a campaign start uploads once, not once per worker.
- **Self-healing:** if the Platform rejects a cached ID as invalid or expired (for example WhatsApp media errors such as 131053, or an Instagram invalid attachment), the adapter deletes the key, re-uploads once and retries the send once; a second failure is returned as the Platform's own result.
- **Inbox lifecycle:** disconnecting an Inbox, rotating its credentials to a different account, or `OutboundRuntime.evict_inbox` deletes `media_id_pattern(inbox)`, so no ID outlives the account that owns it.
- **Every backend, not only Redis:** the Media ID cache is one more cache type in the cache domain (`wappa/persistence/cache_factory.py`), so it follows the Host's configured backend. With JSON it is stored in the server folder through the existing JSON cache backend (same keys from `KeyFactory`, TTL enforced on read and by the sweeper), so a Host without Redis keeps one-upload-per-campaign on a single host; the memory backend makes it per process and lost on restart. The existing parameterized cache contract suite covers all three backends. Redis is the recommended backend.
- **Not for cards:** carousel cards accept URLs only, so the Media ID cache never serves them.

### 4. Wappa-hosted public media URLs

- Route: `GET /media/public/{token}` (and `HEAD`), mounted on the existing app beside the webhook routes. It is a service route, so an embedding Host keeps it. The base comes from a new `SYSTEM_PUBLIC_BASE_URL` (the same https origin Meta already reaches for webhooks); without it, any send that needs a URL fails before I/O with a message naming the setting.
- Token: 256 random bits, base64url. It is an opaque capability looked up in the store, not a signed payload. The bytes have to be stored anyway, so a stored record costs nothing and allows early revocation; an HMAC-signed stateless token would add a secret to manage for no gain. Record: content hash, pinned content type, size, `expires_at`, optional filename.
- Storage: one small `MediaStore` seam (put, get, delete with TTL, public URL for a key) with two real adapters:
  - **Redis, DB 5, a new `media` pool alias.** It follows the existing one-pool-per-logical-DB convention in `wappa/persistence/redis/redis_client.py` (`users` 0, `state_handler` 1, `table` 2, `expiry` 3, `ai_state` 4). The `media` pool must be created with `decode_responses=False` (every current pool decodes to text, which would corrupt bytes). Values are binary strings (`SET media:{hash}:{rule} <bytes> EX <ttl>`) plus a small metadata hash (content type, size, filename). Redis is for small, ephemeral artifacts only: posters, stickers, thumbnails, short voice notes, with a per-object cap (default 1 MB); videos never go to Redis, because Redis memory costs far more than object storage. A separate DB isolates `FLUSHDB` and `SCAN`, but `maxmemory-policy` is per instance: with `volatile-lru` (or `volatile-ttl`) TTL-bearing media keys are evicted before Host keys without a TTL; when media volume matters, point the `media` pool at its own Redis instance.
  - **S3-compatible object storage** (S3, R2, MinIO, GCS interop). Durable, serves its own presigned or public URLs, so Wappa's public route is not involved and costs nothing to serve. Derived artifacts are written back next to their source and kept for the source's lifetime: `catalog/shoe-12.webm` gets `catalog/shoe-12.poster.jpg`, so a catalog video's poster is generated once ever and the card's `image_url` is that object's URL.
  - **Server folder** (the fallback when the Host runs without Redis). Wappa already lets a Host choose the memory, JSON or Redis cache backend; when it chose JSON or memory, media follows it onto the server's disk instead of failing. Bytes go to `SYSTEM_MEDIA_STORE_DIR/bytes/<inbox namespace>/<content key>` (written to a temp name and renamed, so a reader never sees half a file), with a sidecar metadata file holding the content type, size and `expires_at`. A sweeper task on the app lifespan deletes expired files every minute and on startup, and a size cap (`SYSTEM_MEDIA_STORE_MAX_BYTES`) evicts oldest-first. The public route serves from it the same way. It works for one host with any number of workers on that host (shared disk, atomic renames, `O_EXCL` lock files for single flight); several hosts need a shared volume or Redis/S3.
- Response: the pinned `Content-Type` from the probe (never from the token or a query), `Content-Length`, `X-Content-Type-Options: nosniff`, `Content-Disposition: inline` for media and `attachment` for documents, `Referrer-Policy: no-referrer`, `Cache-Control: public, max-age=` the remaining TTL. Single-range `Range` support for video, since Meta's fetcher may use it (**unverified**).
- Safety: unknown, expired and malformed tokens all return the same `404` with no body difference and constant-time lookup; no index, no listing, no path segments beyond the token; size served is capped by the record; tokens and URLs are never logged in full (prefix only).
- TTL: default **10 minutes** for Redis-held artifacts. Meta fetches media sent by `link` at send time and serves the bytes to Users from its own CDN, not from the Host's server: WhatsApp documents that it caches link media for 10 minutes, and Instagram message images are served from Meta's `fbcdn` / `lookaside` hosts, so the working assumption (strong, **to verify**) is that Instagram also copies `image_url` at send. 10 minutes covers retries and Meta's fetch. If the live check shows Instagram re-fetching at render, card images move to the S3 adapter (permanent) rather than to a longer Redis TTL. Because every artifact regenerates on a miss (section 3), a short TTL never breaks a later send; it only costs one regeneration.

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
| `SYSTEM_MEDIA_URL_TTL_SECONDS` | 600 | lifetime of Redis-held artifacts and their public URLs (regenerated on miss) |
| `SYSTEM_MEDIA_STORE` | `redis` when the cache backend is Redis, else `dir` | `redis` (pool alias `media`, DB 5), `s3`, or `dir` (server folder) |
| `REDIS_MEDIA_URL` | the Redis URL with DB 5 | connection for the `media` pool (bytes); may point at a separate instance |
| `REDIS_MEDIA_IDS_URL` | the Redis URL with DB 6 | only if the Media ID cache is Wappa-owned AND a separate pool is chosen (both undecided) |
| `SYSTEM_MEDIA_REDIS_MAX_OBJECT_BYTES` | 1 MB | refuse larger objects in Redis (use S3) |
| `SYSTEM_MEDIA_S3_BUCKET` / `SYSTEM_MEDIA_S3_PREFIX` / `SYSTEM_MEDIA_S3_ENDPOINT` | unset | S3-compatible store; credentials from the standard provider chain, never from Wappa settings |
| `SYSTEM_MEDIA_STORE_DIR` | `./.wappa/media` | server-folder store, used when the cache backend is JSON or memory (or `SYSTEM_MEDIA_STORE=dir`) |
| `SYSTEM_MEDIA_STORE_MAX_BYTES` | 1 GB | size cap of the server-folder store; oldest files are evicted first |

Startup log: when media adaptation or public URLs are enabled, Wappa logs one line naming the stores it chose, for example `MEDIA_STORE bytes=dir:./.wappa/media ids=json`. When either store is not Redis (or S3 for bytes), it adds one warning: `Media Adaptation is running on the server folder (single host). It works, but caches are lost on redeploy without a persistent volume and do not scale across hosts; Redis (DB 5 media, DB 6 media_ids) is recommended for production and campaigns.` With the memory backend the warning also says the Media ID cache is per process and lost on restart. The warning is logged once per process, at startup, never per send.

Logs (secret-free, no bytes, token prefix only): one `MEDIA_PROBE` line per file at debug; `MEDIA_ADAPTED` at info with use, from/to MIME and codecs, sizes, duration in ms, and cache hit; `MEDIA_REFUSED` at warning with the reason; `MEDIA_CODEC_UNVERIFIED` once per process when PyAV is absent. Counters for adaptations, cache hits, timeouts and pool restarts go through the existing logger; no metrics backend is added.

Failures reuse existing outcomes, with no new result type:

- Local rule violation that cannot or may not be adapted (wrong family, document type, detection-only mode, `Unfixable`): `ValueError` before I/O, HTTP 400, per ADR-0024. The message names the detected type, the rule and the fix (for example "install wappa[media] and set SYSTEM_MEDIA_ADAPT=1").
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
- MediaStore: one parameterized suite over the server-folder, Redis (fake) and S3 (fake) stores, per the cache contract pattern, including TTL expiry, the sweeper, the size cap, atomic writes and the single-flight lock. A startup test asserts the store-selection line and the Redis recommendation warning for the JSON and memory backends, and no warning for Redis.
- Public route: valid token serves pinned type and headers; expired, unknown and malformed tokens give identical 404s; no listing; HEAD and Range; token not logged.
- Messenger parity: the existing parity and pipeline suites gain cases showing that WhatsApp and Instagram given the same Host call produce conforming payloads, with fake HTTP only.

Live checks (added to the live test plan, run by hand on test Inboxes, never in CI): WhatsApp voice note from an MP3 shows the waveform and transcription; WhatsApp sticker from a PNG and from a GIF; WhatsApp High-profile MP4 plays on Android after adaptation; WhatsApp and Instagram carousels from local files and from Media IDs; Instagram card with video shows the poster; Instagram GIF image and WebP-as-image behaviour; whether an Instagram card image still renders after its public URL expires (sets the TTL and whether cards need S3); whether Meta's fetcher uses `Range`; a template campaign that survives a Redis `FLUSHDB` of DB 5 mid-run (regeneration path); a poster generated from an S3-hosted WebM and MP4 by Range read.

### 9. Phased rollout

0. Format matrix (live, no Wappa code change; done first, because it decides the spec tables). See Format matrix below. Observed results override documentation where they disagree.
1. Detection (no new dependency): `MediaSpec` on `PlatformEntry`, the two verified specs, `probe` with magic bytes and Pillow, `plan`, refusal errors before I/O, the `3gpp` and static-WebP drift fixes. Breaking only where a lying suffix used to slip through; listed in the CHANGELOG. **Partly done for WhatsApp (2026-11-06):** `wappa/domain/media_probe.py` (no Pillow yet) and `wappa/messaging/whatsapp/media_rules.py` refuse every failure the matrix found; what remains is the shared `MediaSpec`, `plan`, Pillow-backed details (bit depth, edge length), and the Instagram rules once its run is complete.
2. Adaptation: the `wappa[media]` extra, `adapt`, the process pool, the content cache and the Media ID cache, pre-adaptation in `IMediaLibrary.upload`. Off by default.
3. Public URLs: `MediaStore`, `/media/public/{token}`, `SYSTEM_PUBLIC_BASE_URL`, carousel filling with the URL-only `CardMedia(kind, url, poster_url)` card contract. Gate on the Instagram re-fetch live check.

Each phase updates `docs/public-contract.md`, both `ARCHITECTURE.md` files, `CONTEXT.md` (new terms: Media Spec, Media Use, Media Adaptation, Public Media URL) and the CHANGELOG in the same change; phase 1 lands with the ADR that retires "Wappa never converts media".

### Source media: S3 and WebM masters

A Host that keeps its media in S3 gets the best case: Range reads for probing and posters, durable write-back of derived artifacts, and URLs served by S3. The container of the master matters, though. WhatsApp accepts video only as MP4 or 3GPP with H.264 video and AAC audio; it does not accept WebM. Instagram accepts both. A WebM master therefore means a full transcode (VP8/VP9 to H.264) before any WhatsApp send, which costs real CPU, unlike a poster frame. The recommendation is an MP4 master (H.264 + AAC, `faststart`), which plays on WhatsApp, Instagram and the web; a WebM rendition can be kept beside it for a website. If the master stays WebM, the engine transcodes once per video and writes the MP4 back to S3 (`clip.webm` gets `clip.wa.mp4`), so the cost is paid once per video, never per send.

### Scale and cost

Worst case modelled: 100 distinct 20 MB videos per minute, each needing a poster (no cache hits).

| Resource | With Range / sequential reads (this design) | Naive full download |
| --- | --- | --- |
| Data downloaded | about 1-2 MB per video: about 200 MB/min, about 12 GB/hour | 20 MB per video: 2 GB/min, about 120 GB/hour |
| CPU | one 1080p frame decode + JPEG encode about 0.1-0.2 s: about 15 CPU-seconds/min, about a quarter of one core | same, plus disk I/O |
| Disk | none (in memory) | about 20 MB per job briefly, a few hundred MB at peak |
| Redis | 100 posters x about 100 KB = 10 MB per minute, expiring after 10 minutes (about 100 MB resident at steady state) | same |
| Egress | Meta fetches each poster once (about 100 KB) and serves Users from its CDN | same |

Ingress is free on most clouds, so the worst case costs about a quarter of a core and a little Redis memory, a few dollars a month; with realistic reuse (the same catalog videos sent to many Users) the cache hit rate is high and the cost is close to zero. The limits to protect are bandwidth and concurrency, not storage: the process pool size, a cap on concurrent remote reads, and the queue cap (section 3), so a burst gets a fast `MEDIA_UNAVAILABLE` instead of piling up. The zero-cost paths stay first: a Host-supplied `poster_url`, posters written back to S3, pre-adaptation at upload, and the Media ID cache for campaigns.

### Poster frame

When a video card has no `poster_url`, the poster is the frame at **1 second** (a seek by timestamp, not by frame index, because frame rates vary: 1 second is frame 30 at 30 fps and frame 25 at 25 fps). The first frame is often black or a fade-in, so it is used only when the clip is shorter than 1 second. If the frame at 1 second is near-black (mean luminance below a small threshold), the engine tries 2 seconds, then falls back to the first decodable frame. The poster keeps the video's aspect ratio, is scaled to the `card_image` rule, and is encoded as JPEG. The whole step (download, decode, encode, publish) runs in the background pool under the same per-job timeout and cache as every other adaptation, and its failure returns the same pre-send rejection as adaptation off, so a send never half-completes.

## Open questions

- **Who owns the Media ID cache: Wappa (automatic), the Host (primitives only), or both?** And if Wappa, one Redis pool (DB 5, two key families) or a separate DB 6? See Media ID cache.

- License of the bundled FFmpeg in PyAV wheels (likely GPL through x264/x265): accept for the opt-in extra, or require a system FFmpeg or OpenH264 for H.264 encoding?
- Does Instagram copy `image_url` at send (working assumption: yes, bytes are served from Meta's CDN) or hotlink it at render? Live check: send a card whose image URL expires after 10 minutes, then open the thread on a device that never loaded it. If it hotlinks, card images must use the S3 adapter.
- Is GIF accepted as an Instagram image on the Facebook Login path, and is WebP silently accepted or refused?
- Instagram `attachment_id` lifetime (Messenger documents 90 days): what TTL is safe for the Media ID cache?
- WhatsApp sticker dimensions: is 512×512 enforced by the Cloud API, or only advised?
- Poster frame: decided 2026-11-06, see Poster frame.
- Should `SYSTEM_MEDIA_FETCH_URLS` exist at all, or should Host URLs always pass through untouched?
- Multi-host deployments without Redis or S3: the server-folder store needs a shared volume; Wappa cannot detect several hosts reliably, so it relies on the startup warning. Is a warning enough, or should a setting assert single-host?
- Does the WhatsApp Cloud API honour `Range` and HTTP caching headers when it fetches link media, and does Meta's fetcher re-fetch within its 10-minute cache?
- Does `MediaUse` stay internal? `MediaFamily.STICKER` already exists (hardening F10); should `MediaFamily` also gain `VOICE` so `IMediaLibrary.upload` can pre-adapt voice notes (a public contract change)?

### Format matrix (phase 0 live test)

Meta's docs and Meta's behaviour can differ (for example, WhatsApp does not list WebM video, but it may accept it), so the spec tables are confirmed by sending every format for real before they are coded. The test runs in the lab app `../wappa_examples/instagram_conversations_example`, whose `media_lab` Score already sends `/image`, `/audio`, `/video` and `/file` from `app/example-assets` over its public `PUBLIC_BASE_URL`, on whichever Platform the command came from.

- Assets: one small file per format in the lab's `app/assets/formats/` (served at `/example-assets/formats/`), generated by `app/generate_formats.py`. Mixing image and video card headers in one WhatsApp carousel failed live with 131009 ("same structure for all cards"); Wappa now refuses it when the carousel is built. Images: JPEG, PNG, PNG with alpha, static WebP, animated WebP, GIF, animated GIF, HEIC. Video: MP4 H.264 Baseline + AAC, MP4 H.264 High with B-frames, MP4 HEVC, MOV, 3GPP, WebM VP8, WebM VP9, MKV. Audio: MP3, M4A/AAC, mono OGG/Opus, stereo OGG/Opus, OGG Vorbis, WAV, AMR, WebM audio. Documents: PDF, DOCX, XLSX, TXT. Stickers: static WebP 512x512, animated WebP, PNG. Each at a size well under every limit, plus one file just over each Platform's size cap.
- Command: `/formats <family>` (image, video, audio, voice, document, sticker, card) sends every asset of that family to the sender, once **by link** and once **by upload** (`IMediaLibrary.upload`, then the Media ID or attachment ID), each labelled with the file, its container and codec: as the caption for image, video and document (Instagram receives it as Wappa's follow-up text), as a text sent first for audio, voice and sticker, which take no caption. `/formats card` sends carousels whose cards use image and video URLs of each format.
- Two outcomes are recorded per file and per Platform, because Meta can accept a send and fail it later: the **API response** (accepted, or the error code) and the **delivery result** from the status webhook (WhatsApp `failed` with error codes such as 131053, or `delivered` / `read`), which the lab logs against the outgoing message ID. A third column is filled by the tester on the phone: renders, plays, plays without sound, shows as a file, or missing.
- Run from both Platforms: from the test WhatsApp number and from the test Instagram account. Results go into a table in this PRD (Platform x use x format: API / delivery / rendering) and replace the **unverified** markers in the spec tables. A format Meta accepts but the phone cannot play counts as not accepted.
- Questions the matrix answers: WebM video and audio on WhatsApp and Instagram; HEVC and High-profile H.264 playback on Android; GIF and WebP as Instagram images and stickers; whether WhatsApp's 512x512 sticker size is enforced; whether static WebP works as a WhatsApp image; Instagram audio formats beyond AAC/M4A/WAV; video and image card headers by format on both Platforms; the size-cap behaviour at the boundary.
- Safety: only the tester's own test WhatsApp number and Instagram account receive messages; nothing is sent to other Users.

#### WhatsApp results (2026-11-06, test number, rerun after 2e5fd84 and ef05128)

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

- A link is accepted (200) and fails later for every unsupported format: the verdict arrives as a status webhook, seconds to minutes later (a HEIC link that Meta could not fetch failed after 6 minutes with "http code 503"). Only refusal before I/O gives the Host a synchronous answer, so the spec table must be enforced at send time.
- Suffix rules alone miss three cases: animated vs static WebP, OGG Vorbis vs Opus, and sticker dimensions. Each needs the bytes (magic bytes, the WebP `ANIM` chunk, the OGG codec header, image size). These are phase 1 detection.
- By Media ID nothing has a suffix. Wappa now checks the stored MIME type (`GET /{media_id}`) for voice notes (`audio/ogg`) and stickers (`image/webp`) before sending (677f34a, 13cec65); other families still pass through.
- Python maps `.3gp` to `audio/3gpp`; WhatsApp needs `video/3gpp` for a video. Fixed in the Media Library (ef05128) and in the lab's asset server.
- A carousel should be checked card by card before sending, since one bad card loses the whole message.

## Exit criteria

- The phase 0 format matrix is run on both Platforms, its results table is in this PRD, and every spec value is either documented and observed or marked as documented only.
- Both Platform specs live on `PlatformEntry`, cite their sources and the matrix, and are the only media rule tables in the tree.
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
