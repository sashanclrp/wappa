# Media upload and download (core interface 3)

## Summary

`IMediaLibrary` (`wappa/domain/interfaces/media_library.py:38-45`) is already the HandlingMedia seam. It has two adapters that really differ: the WhatsApp Media API (`wappa/messaging/whatsapp/media_library.py:31`) and Instagram `message_attachments` with a CDN reader (`wappa/messaging/instagram/media_library.py:27`). Both Platforms really upload and download, so neither adapter needs a `NotSupported` path.

The defects sit around that seam:

- Shared HTTP code branches on `PlatformType.WHATSAPP` to skip the seam on upload (`wappa/api/dependencies/media_transfer.py:94`).
- A second "domain" media ABC, `IMediaHandler`, has 17 abstract members and one adapter.
- The neutral `download` has no size bound. Each Platform therefore grew its own side door for bounded or large reads: `IAttachmentMediaReader` on Instagram and `media_handler.*` on WhatsApp.
- The scaffolded transcription example teaches Hosts to download through the WhatsApp-only side door.

The verifier kept five findings (four from the auditor, one reframed, plus one new) and rejected five as cosmetic, already sanctioned by an ADR, contrary to the evidence, or over-engineering. The auditor's interface proposal was cut down. It no longer takes `bytes | Path`, adds no neutral `limits()`, defines no `IWhatsAppMediaAdmin` ABC, and does not override the ADR-0021 `ValueError`-means-400 rule.

## Confirmed findings

### 03-1 get_media_uploader branches on Platform and imports the WhatsApp handler in shared API code

- Files: `wappa/api/dependencies/media_transfer.py:3-6`, `:23-25`, `:29-32`, `:94-99`, `wappa/domain/interfaces/media_library.py:42`, `wappa/messaging/whatsapp/media_library.py:36-38`, `wappa/messaging/whatsapp/handlers/whatsapp_media_handler.py:66-71`
- Principle: platform-branch
- Severity: high
- Breaking: no (the HTTP contract of `POST /api/{platform}/media/upload` is unchanged). Public surfaces: the upload route (`wappa/api/routes/whatsapp/whatsapp_media.py:81-118`), `IMediaLibrary.upload` (a new optional keyword only).
- Evidence: `media_transfer.py:94` reads `if context.inbox_ref.platform is PlatformType.WHATSAPP:` and builds a `WhatsAppMediaHandler` (imported at `:23`) inside the Platform-neutral API dependency layer. Every other Platform goes through `messenger.capability(IMediaLibrary)` at `:100-107`. The module docstring (`:3-4`) gives the reason: WhatsApp "honours an explicit `media_type`" from the form. `IMediaLibrary.upload(source, family)` (`media_library.py:42`) cannot carry that, and `WhatsAppMediaLibrary.upload` drops `family` (`whatsapp/media_library.py:37`) and calls `upload_media(source)` without a type. The concrete handler already accepts `media_type: str | None` (`whatsapp_media_handler.py:66-71`). The fork exists only because the neutral signature is one keyword short. The `MediaUploader` Protocol (`media_transfer.py:29-32`) is a route-shaped interface that exists only to hide the fork.
- Deletion test: delete the WhatsApp branch and the complexity vanishes. `WhatsAppMediaLibrary.upload` already wraps the same Media API call, and the one thing lost (explicit MIME) comes back as a keyword. The `MediaUploader` Protocol then has one implementer and can go too.
- Proposed fix:
  1. Add `mime_type: str | None = None` to `IMediaLibrary.upload`.
  2. `WhatsAppMediaLibrary` passes it as `media_type` to `upload_media`. Instagram ignores it, because its rules key off the file suffix (`instagram/media.py:68-71`).
  3. `get_media_uploader` becomes `messenger.capability(IMediaLibrary)` or 501 for every Platform, and the `PlatformType` and `WhatsAppMediaHandler` imports are deleted.
  4. `LibraryMediaUploader` stays; the temp-file write (`:61-63`) is cheap and keeps the seam `Path`-only.
  5. Replace the `MediaUploader` Protocol with the concrete `LibraryMediaUploader`.
  6. Add a route test for WhatsApp through the library path, which is the less-tested path today.
- ADR conflict: none. ADR-0021 decision 4 (`docs/adr/0021-platform-messaging-http-api.md:16`) says routes gate on the `IMediaLibrary` capability. The fork contradicts it, and the fix brings the code in line.

### 03-2 IMediaHandler is a hypothetical seam: 17 abstract members, one adapter, published as a domain interface

- Files: `wappa/domain/interfaces/media_interface.py:30-390`, `wappa/domain/interfaces/__init__.py:14`, `:26`, `wappa/messaging/whatsapp/handlers/whatsapp_media_handler.py:25`, `wappa/api/routes/whatsapp/whatsapp_media.py:39`, `:400`, `:435`, `:506`, `wappa/api/routes/whatsapp/whatsapp_health.py:22`, `:38`, `wappa/api/dependencies/whatsapp_dependencies.py:53-62`, `docs/public-contract.md:1050`
- Principle: hypothetical-seam
- Severity: medium (no shared code dispatches on it, but it is the most likely trap for a third-Platform author)
- Breaking: yes. Public surfaces: `wappa.domain.interfaces.IMediaHandler` (listed at `docs/public-contract.md:1050`).
- Evidence: the ABC declares the properties `platform`, `inbox_id`, `supported_media_types`, `max_file_size` and the methods `upload_media`, `upload_media_from_bytes`, `upload_media_from_url`, `upload_media_from_stream`, `get_media_info`, `download_media`, `download_media_tempfile`, `get_media_as_bytes`, `stream_media`, `delete_media`, `validate_media_type`, `validate_file_size`, `get_media_limits` (abstract members at `media_interface.py:46-378`). Its only implementer is `WhatsAppMediaHandler` (`whatsapp_media_handler.py:25`). Instagram implements only the two-method `IMediaLibrary`. Every annotation that uses `IMediaHandler` sits in a WhatsApp-only route: `whatsapp_media.py:400`, `:435`, `:506` and `whatsapp_health.py:38`. Each of those receives the concrete class from `get_whatsapp_media_handler` (`whatsapp_dependencies.py:53-62`), which is gated by `whatsapp_client()` → `whatsapp_only` (`wappa/api/ARCHITECTURE.md:35`). The repo therefore publishes two "Platform-neutral" media ABCs in two packages, and a new Platform cannot tell which one to implement.
- Deletion test: delete the ABC and keep the concrete class. The four route annotations become `WhatsAppMediaHandler` and nothing else changes, because no caller relies on polymorphism. Complexity vanishes.
- Proposed fix:
  1. Delete `IMediaHandler` from `wappa/domain/interfaces/media_interface.py` and from `wappa/domain/interfaces/__init__.py`.
  2. Re-type the route dependencies to `WhatsAppMediaHandler`.
  3. Do not introduce an `IWhatsAppMediaAdmin` ABC. It would have one adapter and repeat this finding.
  4. WhatsApp-only media operations (info, delete, URL upload, tempfile, stream) stay on the concrete `WhatsAppMediaHandler`. Hosts reach it today as `WhatsAppMessenger.media_handler` after a cast (`wappa/cli/examples/openai_transcript/app/master_event.py:22`, `:34`).
  5. If a non-cast path is wanted, register the concrete class as a capability key in `WhatsAppMessenger.capability` (`whatsapp_messenger.py:82-88`). That makes it an explicit capability with no new interface.
  6. Move the `MediaInfoResult`/`MediaDeleteResult`-shaped models only if they become WhatsApp-only.
  7. Under clean-cut releases, list the removal in CHANGELOG, update `docs/public-contract.md:1050`, and update `wappa/messaging/ARCHITECTURE.md:37`, `:57`, `:98`.
- ADR conflict: none. The ADR-0016 contract map (`docs/adr/0016-one-messenger-method-per-action.md:34`) names only `IMediaLibrary` as the shared media capability. CHANGELOG `:1172` once called `IMediaHandler` "the platform-agnostic media interface", and that description is now false.

### 03-3 The neutral download has no size bound, so each Platform grew a Platform-specific side door (IAttachmentMediaReader on Instagram, media_handler on WhatsApp)

- Files: `wappa/domain/interfaces/media_library.py:44-45`, `wappa/domain/interfaces/conversation_capabilities.py:160-176`, `wappa/messaging/instagram/media.py:108`, `wappa/messaging/instagram/media_library.py:68-69`, `wappa/messaging/instagram/messenger.py:218-227`, `wappa/messaging/__init__.py:33`, `:146`, `wappa/cli/skills/wappa-instagram-apps/references/text-and-media.md:83`, `docs/public-contract.md:62`
- Principle: hypothetical-seam (also DRY: one action, two capability kinds)
- Severity: medium
- Breaking: yes. Public surfaces: `wappa.messaging.IAttachmentMediaReader`, `messenger.capability(IAttachmentMediaReader)`, `IMediaLibrary.download` (a new optional keyword).
- Evidence:
  - `IAttachmentMediaReader` has `get_bytes(url, *, max_bytes)` and `stream(url, ...)` (`conversation_capabilities.py:160-176`) and one implementer, `InstagramAttachmentReader` (`instagram/media.py:108`).
  - The same object is registered both as its own capability (`instagram/messenger.py:226`) and as the internal collaborator of `InstagramMediaLibrary` (`:221`). `download` there is a one-line pass-through that drops `max_bytes` (`media_library.py:68-69`). The same inbound bytes are therefore reachable through two capability kinds.
  - The Host-facing skill says "For custom size limits or streaming large files, use the Instagram-only `IAttachmentMediaReader`" (`text-and-media.md:83`). `public-contract.md:62` says "Prefer `IMediaLibrary.download` over `IAttachmentMediaReader`".
  - Bounded or large reads are not Instagram-specific. WhatsApp offers the same thing through `stream_media` / `download_media_tempfile` on the concrete handler. In other words, a Platform-neutral need (a bounded read) is answered by a different Platform-specific door on each Platform.
- Correction to the auditor: the claim that `stream()` has no caller is wrong. It is a published Host-facing method, it is exercised in `tests/test_instagram_conversations.py:1093`, and the skill names it. No library-internal caller exists, and none is expected for a Host API. Folding streaming into the neutral seam is not justified either, because no neutral caller exists today: the WhatsApp download route buffers with `download_media` (`whatsapp_media.py:451`).
- Deletion test: delete the `IAttachmentMediaReader` ABC and its capability registration, and give `IMediaLibrary.download` a `max_bytes` keyword. The size-limit use case moves onto the neutral seam on both Platforms. The reader stays an internal collaborator of `InstagramMediaLibrary` (`media_library.py:28-32`), keeping its host allowlist and redirect/time/size bounds. Complexity vanishes from the public surface. Only the Instagram-only `stream()` would have to reappear somewhere, and only if a Host needs it.
- Proposed fix:
  1. `download(media_id, *, max_bytes: int | None = None)` on `IMediaLibrary`. Instagram passes it to `reader.get_bytes`. WhatsApp enforces it on its fetch.
  2. Delete `IAttachmentMediaReader` from `conversation_capabilities.py`, from the `wappa.messaging` exports and from the Instagram capability map.
  3. Keep `InstagramAttachmentReader` as a private helper.
  4. Decide `stream()` on its merits. If Hosts need it, add `stream(media_id, *, max_bytes)` to the neutral seam only together with a WhatsApp adapter (both Platforms can stream). Otherwise drop it.
  5. Update `docs/public-contract.md:60`, `:62`, the skill (`SKILL.md:41`, `text-and-media.md:83`), `docs/migration/instagram-conversation-contracts.md:147` and `wappa/messaging/ARCHITECTURE.md:48`.
- ADR conflict: amends the ADR-0016 contract-map row for `IMediaLibrary` (`0016-one-messenger-method-per-action.md:34`). Record the new keyword there.

### 03-5 The media download route bypasses IMediaLibrary although both Platforms implement download

- Files: `wappa/api/routes/whatsapp/whatsapp_media.py:425-451`, `wappa/api/dependencies/whatsapp_dependencies.py:53-62`, `docs/adr/0021-platform-messaging-http-api.md:16`
- Principle: platform-leak
- Severity: low
- Breaking: no (WhatsApp URL and behaviour unchanged; Instagram gains a 200 where it answered 501). Public surfaces: `GET /api/{platform}/media/download/{media_id}`.
- Evidence: `download_media` takes `IMediaHandler = Depends(get_whatsapp_media_handler)` (`whatsapp_media.py:435`), so the route answers 501 on Instagram. Its description tells Instagram Hosts to "fetch them directly" (`:428-431`), which skips the credential-free host allowlist that `InstagramAttachmentReader` enforces. `IMediaLibrary.download` exists on both Platforms (`media_library.py:44-45`). ADR-0021 decision 4 says "a Platform that gains a capability serves the route unchanged". The upload route was moved onto the capability for that reason, and the download route was not. The route also makes an extra `get_media_info` call for headers (`:441`), which `MediaBytes.content_type` already carries (`whatsapp/media_library.py:59-63`).
- Deletion test: not a deletion case. It is a missing symmetry, which the existing neutral seam can serve with no new abstraction.
- Proposed fix:
  1. Gate the download route on `requires_capability(IMediaLibrary)` and serve `MediaBytes` with its `content_type`.
  2. Keep `GET /media/{id}` (info), `DELETE /media/{id}` and limits as WhatsApp-only routes on the concrete handler. ADR-0021 decision 4 explicitly lists "the WhatsApp Media API, limits" as WhatsApp-only.
  3. Drop the "fetch directly" advice.
- ADR conflict: none for download. ADR-0021 sanctions the WhatsApp-only status of info, delete and limits, so those are not findings.

### 03-10 (new) The scaffolded transcription example teaches Hosts the WhatsApp-only side door for a neutral action

- Files: `wappa/cli/examples/openai_transcript/app/master_event.py:10`, `:22`, `:34-36`, `:68`, `wappa/cli/examples/openai_transcript/README.md:7`, `wappa/cli/main.py:67-71`, `wappa/core/events/event_handler.py:118`
- Principle: platform-leak
- Severity: low
- Breaking: no (example code only). Public surfaces: the `openai_transcript` scaffold (`wappa/cli/main.py:67`).
- Evidence: the handler's messenger is typed `IMessenger | None` (`event_handler.py:118`). The example imports the concrete `WhatsAppMessenger` (`master_event.py:10`), casts to it (`:22`) and downloads inbound audio with `messenger.media_handler.download_media_tempfile(audio_id)` (`:34-36`). The README advertises that path (`README.md:7`). Downloading an inbound media message is exactly `IMediaLibrary.download(webhook.message.media_id)` on both Platforms (`docs/public-contract.md:62`). Hosts that copy the scaffold get code that cannot move to Instagram, and they learn a concrete-cast pattern instead of the capability pattern.
- Deletion test: delete the cast and the `media_handler` call, and the example still works through `require_capability(IMediaLibrary).download(...)`. It writes the bytes to a temp file or passes them in memory, as the commented alternative at `:68` already does. No complexity reappears.
- Proposed fix: rewrite the example to use `self.messenger.require_capability(IMediaLibrary).download(media_id)`, then update the README line. Keep the WhatsApp message-type check, or use the neutral media message type if one exists.
- ADR conflict: none.

## Rejected findings

- 03-4 "messenger_factory and WhatsAppMessenger build media concretes inline; capability re-created per call". Rejected as cosmetic and partly merged. `WhatsAppMediaLibrary` (`whatsapp/media_library.py:32-34`) is a stateless two-field wrapper, so building it per `capability()` call (`whatsapp_messenger.py:86-87`) costs nothing observable. The factory construction (`messenger_factory.py:180-184`) is the legitimate composition root. The per-request `get_whatsapp_media_handler` (`whatsapp_dependencies.py:53-62`) follows the same pattern as every other per-request WhatsApp handler dependency (`:65-70`). The one genuinely redundant construction (`media_transfer.py:95-99`) disappears with 03-1.
- 03-6 "IMediaLibrary signature cannot carry what WhatsApp needs". Merged and partly rejected. The `mime_type` keyword is the fix for 03-1 and `max_bytes` is the fix for 03-3. Three parts are rejected:
  - `source: Path | bytes`: a second input mode on the seam to save one temp-file write in a single caller (`media_transfer.py:61-63`).
  - A neutral `limits(family)`: its only consumer is the WhatsApp-only limits route, so it would be a hypothetical seam.
  - "Local-rule failures return REJECTED, never raise": ADR-0021 decision 4 (`0021-platform-messaging-http-api.md:16`) makes `ValueError` the documented local-rule signal that answers 400, and Instagram's `validate_local_file` (`instagram/media.py:68-84`) follows it.
- 03-7 "Instagram and WhatsApp both fit one HandlingMedia without NotSupported". Rejected because it is a design observation, not a defect. It is correct, and it is folded into the Summary and the Interface proposal.
- 03-8 "WhatsAppMediaHandler has five upload/download variants with no production caller". Rejected because the evidence does not hold and there is no architectural payoff:
  - `download_media_tempfile` has a scaffolded Host caller (`openai_transcript/app/master_event.py:34`).
  - `upload_media_from_url` is a released, documented Host feature (CHANGELOG `:1169-1173`), tested in `tests/test_media_upload_from_url.py` and `tests/test_media_download_client_isolation.py:102`.
  - These methods are Host API on a WhatsApp-only concrete class, so "no internal caller" does not show dead code.
  - Once 03-2 removes the ABC, these are plain WhatsApp extension methods, and keeping them costs no seam.
- 03-9 "Stale architecture docs name IMediaHandler". Rejected because the docs are not stale today. `wappa/messaging/ARCHITECTURE.md:37`, `:57`, `:98` describe `IMediaHandler` accurately as it exists now, and `ARCHITECTURE.md:326` describes `IAttachmentMediaReader` as it exists. The doc updates are listed in the proposed fix of 03-2 and 03-3, where they belong.

## Checked and legitimate

- `wappa/domain/factories/messenger_factory.py:180-184` builds `WhatsAppMediaHandler`. This is the composition root and the right home for Platform construction.
- `IMediaLibrary` with `WhatsAppMediaLibrary` and `InstagramMediaLibrary` is two adapters with real variation (Media API upload/ID-resolve vs `message_attachments` plus a host-restricted CDN fetch). This is the one real seam in the area and the right HandlingMedia shape.
- `wappa/messaging/instagram/media.py` (`MEDIA_RULES`, `validate_local_file`, `ALLOWED_CDN_SUFFIXES`, `InstagramAttachmentReader`'s allowlist and redirect bounds) holds Platform rules inside the Instagram adapter package, which is the correct location. Only the public ABC registration is a finding (03-3).
- `wappa/api/dependencies/media_transfer.py:35-86` (`media_family`, `LibraryMediaUploader`) is a Platform-free translation from HTTP bytes and MIME to the seam. Keep it once 03-1 removes the branch.
- The WhatsApp-only info, delete, limits and health routes are behind `whatsapp_client()` → `whatsapp_only` 501 (`wappa/api/ARCHITECTURE.md:35`), and ADR-0021 decision 4 sanctions them. They are legitimate Platform-only surfaces once they are typed against the concrete handler instead of the ABC (03-2).
- `WhatsAppMessenger.media_handler` as a concrete attribute (`whatsapp_messenger.py:62`, `:71`) is fine as the WhatsApp extension surface inside the WhatsApp adapter. It is not declared on `IMessenger`, so it does not leak into the neutral contract. The only problem is the example teaching it for a neutral action (03-10).

## Interface proposal

HandlingMedia is `IMediaLibrary`, amended in place. No rename is required: the name already says "media library" and a rename would churn every Host for no behaviour. It is reached through `messenger.capability(IMediaLibrary)` / `require_capability(IMediaLibrary)`. Following ADR-0016, it has one method per action, and SRP is kept separate from sending:

```python
class IMediaLibrary(ABC):
    async def upload(self, source: Path, family: MediaFamily, *, mime_type: str | None = None) -> UploadResult: ...
    async def download(self, media_id: str, *, max_bytes: int | None = None) -> ReadResult[MediaBytes]: ...
```

- `upload` returns an opaque reusable `media_id`, which is a WhatsApp Media ID or an Instagram attachment_id. That ID goes to `send_image` / `send_video` / `send_audio` / `send_document` on the same Inbox.
  - `mime_type` is honoured where the Platform takes one (WhatsApp) and ignored otherwise.
  - Local-rule violations raise `ValueError` (400 per ADR-0021). Platform refusals return `REJECTED`.
- `download` takes `media_id` exactly as `webhook.message.media_id` (a WhatsApp Media ID, or the Instagram CDN URL). `max_bytes` bounds the read, and the Platform default applies when it is `None`. An oversize read returns `REJECTED`/`SIZE`.
- Adapters:
  - `WhatsAppMediaLibrary` resolves the ID, then fetches with the credential-free download client.
  - `InstagramMediaLibrary` uses `message_attachments` for upload and the private `InstagramAttachmentReader` for host-restricted, bounded CDN reads.
  - Neither needs a `NotSupported` path.
- Not added, because no neutral caller exists: `bytes` sources, `limits()`, `stream()`, info and delete. Add `stream(media_id, *, max_bytes)` later only with a real caller and both adapters.
- Deleted:
  - The `IMediaHandler` ABC. Keep the concrete `WhatsAppMediaHandler`.
  - The `IAttachmentMediaReader` ABC and its capability registration and export. Keep the reader private to the Instagram adapter.
- WhatsApp-only extension (explicit, no new ABC): the concrete `WhatsAppMediaHandler`, reached as `WhatsAppMessenger.media_handler`. Optionally it can also be registered as a capability key in `WhatsAppMessenger.capability` so Hosts need no cast. It owns `get_media_info`, `delete_media`, `upload_media_from_url`, `download_media_tempfile`, `stream_media` and the limits helpers. The WhatsApp-only info, delete, limits and health routes depend on it directly.
- HTTP layer:
  - `get_media_uploader` is `capability(IMediaLibrary)` or 501 for every Platform, with no `PlatformType.WHATSAPP` branch and no `WhatsAppMediaHandler` import (03-1).
  - The download route is gated on `IMediaLibrary` too (03-5).
  - Info, delete and limits stay WhatsApp-only under ADR-0021 decision 4.
