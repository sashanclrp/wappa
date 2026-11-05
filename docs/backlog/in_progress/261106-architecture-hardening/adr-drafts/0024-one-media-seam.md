# One media seam: IMediaLibrary

Status: Proposed, 2026-11-05. Draft for H-18, H-19, H-20, H-21.

## Context

ADR-0016 names `IMediaLibrary` (upload, download) as the shared media capability, and both Platforms implement it. Two more media seams grew around it. `IMediaHandler` is a 17-member domain ABC with one WhatsApp adapter, consumed only by WhatsApp-gated routes, yet published next to `IMessenger`. `IAttachmentMediaReader` is an Instagram capability that exists because `IMediaLibrary.download` has no size bound. The shared HTTP upload dependency branches on WhatsApp because `upload` cannot carry an explicit MIME type, and the download route bypasses `IMediaLibrary` so Instagram gets 501 for a capability it has, contrary to ADR-0021 decision 4.

## Decision

1. `IMediaLibrary` is the only media interface Wappa publishes: `upload(source: Path, family: MediaFamily, *, mime_type: str | None = None) -> UploadResult` and `download(media_id: str, *, max_bytes: int | None = None) -> ReadResult[MediaBytes]`. `media_id` is exactly `webhook.message.media_id` on download and the reusable send ID on upload. A local-rule violation raises `ValueError` (HTTP 400); a Platform refusal or an oversize download returns `REJECTED`.
2. `IMediaHandler` is deleted. `WhatsAppMediaHandler` stays a concrete WhatsApp-internal class reached through `WhatsAppMessenger.media_handler` and the WhatsApp extension router (info, delete, limits, upload from URL, temp-file download).
3. `IAttachmentMediaReader` is deleted as an interface and a capability; `InstagramAttachmentReader` stays private behind `InstagramMediaLibrary`. A neutral `stream()` is added only with a real caller and both adapters.
4. HTTP upload and download take `requires_capability(IMediaLibrary)` on every Platform, with no Platform branch and no `MediaUploader` protocol.

## Consequences

A third Platform implements one media interface. Breaking: `wappa.domain.interfaces.IMediaHandler`, `wappa.messaging.IAttachmentMediaReader` and its `stream()` are removed; `GET /api/instagram/media/download/{id}` starts serving. Scaffolds and the Instagram skill teach `require_capability(IMediaLibrary).download(...)`.

## Supersedes

None fully. Amends the ADR-0016 contract-map `IMediaLibrary` row (new keywords) and applies ADR-0021 decision 4 to media download. Banner both on acceptance.
