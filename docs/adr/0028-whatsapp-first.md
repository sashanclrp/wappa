# WhatsApp First: neutral contracts mirror WhatsApp; limits are the minimum

Accepted, 2026-11-06 (user rule from the architecture-hardening review). Shapes every Platform-neutral contract described in [ADR-0025](0025-messenger-contract.md) and the HTTP request models in [ADR-0024](0024-outbound-http-routes-and-transports.md).

## Context

WhatsApp is Wappa's broadest Platform and the one most Hosts start on. When the neutral contract was first drawn alongside Instagram, it was narrowed toward the smaller Platform: button headers lost video and document, CTA headers became text only, carousel cards lost video, `send_document` dropped its caption, `send_contact` took one card, and list limits were checked per section instead of in total. Each narrowing silently removed a WhatsApp feature from every Host. Validating limits only at send time also meant a value could be built that one Platform could not deliver.

## Decision

1. **The shape follows WhatsApp.** Every Platform-neutral contract (the `IMessenger` methods, the neutral value types in `wappa/domain/`, and the HTTP request models fronting them) mirrors the WhatsApp Cloud API's seams and full feature set, so the WhatsApp adapter maps 1:1 and loses nothing. Examples: `InteractiveHeader` is text, or an image, video or document by `MediaRef` (`url` or `media_id`) with a document `filename`; `send_cta_message` takes the same header; `send_list_message` takes a text header; `CardMedia` is an image or video by URL (WhatsApp card headers accept a public link only) with an optional `poster_url`; `send_contact` takes several cards with optional phones; `send_document` carries its caption.
2. **Limits on structured values are the most restrictive across the installed Platforms**, enforced when the value is built, so a value that constructs is deliverable on every Platform with no send-time surprise. This covers button title, ID and count, list row title, description, ID and counts, section title, header text, footer, interactive body, list button text, card title, subtitle and count, CTA display text and carousel size. The limits live in one small constants block in `wappa/domain/interactive.py`, each constant commented with the per-Platform values it is the minimum of; plain arguments are checked by `check_button_message`, `check_list_message`, `check_cta_message` and `check_carousel`. There is no limits framework.
3. **Free-form text keeps WhatsApp's limit.** A `send_text` body or a media caption is divisible, so it keeps WhatsApp's limit and a stricter Platform splits it into several messages (Instagram: 1000 UTF-8 bytes, on a word boundary when possible). Splitting preserves meaning, while a lower shared limit would remove WhatsApp capability. A split send returns one `MessageResult`: success only when every part was delivered, every part's message ID in `platform_response`, and a partial failure says how many parts were sent.
4. **Other Platforms emulate, and reject only when emulation is impossible.** Instagram sends a media header as its own message before the buttons or CTA template, folds text headers and footers into the body, flattens list sections into quick replies, and turns a video card into its poster image that opens the video on tap. When the meaning cannot be kept (a video card without `poster_url`, `send_location_request`), the adapter raises `UnsupportedOperationError` before any I/O and names the fix. A card is one visual unit, so card media is never sent apart from the card.
5. **No lowest common denominator.** A WhatsApp feature or field is never dropped because another Platform lacks it; only limits take the minimum. Optional fields that only another Platform uses (for example `MessageCard.default_url` on Instagram) stay, and WhatsApp ignores them.
6. **Shared code never imports WhatsApp classes or branches on Platform.** The WhatsApp shapes are copied into Wappa's own neutral types. Platform-only features are reached through `capability()` ([ADR-0025](0025-messenger-contract.md) rule 4), never through a Platform check.

## Consequences

- A Host writing for WhatsApp gets the whole Cloud API surface through the neutral contract, and the same code runs on Instagram through emulation.
- Some structured limits are lower than WhatsApp's own (for example a list row title is 20 characters because Instagram quick replies are 20, and a button-message body is 640 because the Instagram button template is 640). A Host that needs WhatsApp's higher structured limit on WhatsApp alone has no per-Platform escape hatch, by design.
- Adding a Platform with a stricter structured limit lowers the shared constant and is a breaking change listed in `CHANGELOG.md`.
- Media cases Instagram cannot emulate today (a video card without a poster, media by WhatsApp media ID only) are the scope of the media adaptation backlog (`docs/backlog/drafts/261106-mid-media-adaptation-service.md`).

## Alternatives rejected

- The lowest common denominator shape (silently drops WhatsApp features for every Host).
- Per-Platform limits checked at send time (a value builds and then fails on one Platform).
- Lowering the free-form text limit to the strictest Platform (loses capability that splitting keeps).
- Silent truncation (loses meaning without telling the Host).
