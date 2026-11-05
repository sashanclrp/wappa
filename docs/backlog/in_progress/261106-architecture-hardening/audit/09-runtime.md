# Multi-Inbox / multi-Platform runtime and composition root

## Summary

Verifier pass over the auditor's 9 findings for area 09. Multi-Inbox holds up. `InboxRef.cache_namespace` is Platform-qualified, the callback is one payload-routed route, routing proves membership before dispatch, and credentials are a discriminated union. Multi-Platform is not yet provable. The live runtime repeats the Platform set `{WHATSAPP, INSTAGRAM}` as an allow-list or an "Instagram, else WhatsApp" branch in about 9 places across 6 shared files, and `ARCHITECTURE.md:286-312` writes those edits up as the recipe for adding a Platform.

The verification changed four things. (1) The auditor treated `wappa/webhooks/factory.py` (the schema registries) as part of the live seam. It is not: `SchemaFactory`, `PlatformDetector` and `WebhookFactory` have no runtime callers and only reference each other. They belong with the dead scaffolding (finding 09-3), not with the registry finding. (2) Finding 09-9's WhatsApp message-type fallback can never run, because `button`, `order` and `unsupported` are already `MessageType` members, so it is dead code rather than a seam. (3) Finding 09-2's main fix is already done. `WhatsAppMessenger.capability(IMediaLibrary)` already returns `WhatsAppMediaLibrary`, so the branch in `media_transfer.py` is a leftover. (4) Finding 09-5 is wrong on the facts: Instagram SSE events do carry `user_id`, and `bsuid`/`phone` are WhatsApp identifiers. Findings 09-6 is merged into 09-1. Findings 09-5, 09-7 and 09-8 are rejected (09-7's dead URL aliases move into 09-3).

Result: 4 confirmed findings (09-1 high, 09-2 medium, 09-3 medium, 09-4 low) and 5 rejected or merged.

## Confirmed findings

### 09-1 No single Platform table: the live runtime repeats the Platform set in 9 places

Files: `wappa/api/controllers/webhook_controller.py:116`, `wappa/api/controllers/webhook_controller.py:136-140`, `wappa/processors/factory.py:231-255`, `wappa/processors/factory.py:312-319`, `wappa/domain/factories/messenger_factory.py:111`, `wappa/domain/factories/messenger_factory.py:131-141`, `wappa/domain/factories/messenger_factory.py:197-198`, `wappa/domain/inbox/services.py:85-90`, `wappa/domain/inbox/services.py:118-123`, `wappa/domain/inbox/services.py:139-143`, `wappa/domain/inbox/services.py:149`, `wappa/domain/inbox/services.py:298-304`, `wappa/core/events/field_registry.py:89-96`, `wappa/api/dependencies/inbox_context.py:59-63`, `ARCHITECTURE.md:301-311`

Principle: OCP

Severity: high

Breaking + public surfaces: not breaking. Internal lookups change; `PlatformType`, `MessengerFactory`, `processor_factory` and `InboxCredentialService` keep their signatures.

Evidence: The controller allows only `{PlatformType.WHATSAPP, PlatformType.INSTAGRAM}` (`webhook_controller.py:116`) and then picks the router with a ternary, "Instagram, else WhatsApp" (`:136-140`). `_create_processor` uses an if/elif chain (`processors/factory.py:231-255`), and `get_supported_platforms` returns a hand-written set (`:312-319`). `MessengerFactory` has its own allow-set (`messenger_factory.py:111`), an "Instagram, else WhatsApp" construction branch (`:131-141`) and a third literal list (`:197-198`). `InboxCredentialService` picks the record class with "Instagram, else WhatsApp" in two places (`services.py:85-90`, `:118-123`), runs isinstance checks against both record classes in two more (`:139-143`, `:298-304`), and repeats the allow-set (`:149`). `field_registry.py:89-93` returns Instagram's built-in fields or else WhatsApp's, and `:96` repeats the set. `RoutePlatform` (`inbox_context.py:59-63`) is a second enum with the same two members. Every "else" branch silently treats an unlisted Platform as WhatsApp. Only the allow-list in front of each one stops that, so each pair has to be edited together. `ARCHITECTURE.md:301-311` lists these edits as the steps for adding a Platform.

Deletion test: Deleting the scattered allow-lists today breaks each caller, so the complexity is spread across them, not concentrated. With one table keyed by `PlatformType`, each site becomes one lookup and the "else = WhatsApp" fallthrough disappears. Two adapters exist for every one of these entries, so the seam is real, not hypothetical.

Proposed fix: Add one composition-root module (for example `wappa/platforms.py`) holding `PLATFORMS: dict[PlatformType, PlatformEntry]`, with two entries. `PlatformEntry` is a frozen dataclass of lazily imported callables, not a new abstract hierarchy: `create_processor`, `route_payload`, `build_messenger`, `active_record` and `inactive_record` (the record classes), and `builtin_fields`. The controller, `ProcessorFactory`, `MessengerFactory`, `InboxCredentialService` and `field_registry` look entries up with `PLATFORMS[platform]`, and an unknown key fails loudly. The supported sets and `RoutePlatform`'s members come from `PLATFORMS.keys()`. The isinstance checks in `services.py:139` and `:298` become checks on the record's `status` discriminator, or a check against a `tuple` of record classes built from the table. Rewrite `ARCHITECTURE.md:301-311` to say "add one `PLATFORMS` entry plus the adapters". Connectors stay Host-composed (`IInboxConnector` instances are built by the Host, not looked up), so they do not go in the table.

ADR conflict: none. ADR-0010 and ADR-0021 require a payload-routed callback and a `/api/{platform}` family, and say nothing about where the per-Platform choice lives. ADR-0011 expects the credential union to grow by one member per Platform, and table-driven record selection is consistent with that.

### 09-2 WhatsApp-only shortcuts in the shared HTTP dependencies bypass capabilities that already exist

Files: `wappa/api/dependencies/media_transfer.py:1-6`, `wappa/api/dependencies/media_transfer.py:89-108`, `wappa/messaging/whatsapp/messenger/whatsapp_messenger.py:82-88`, `wappa/messaging/whatsapp/media_library.py:31-38`, `wappa/api/dependencies/inbox_context.py:39`, `wappa/api/dependencies/inbox_context.py:94-106`, `wappa/api/dependencies/inbox_context.py:136-149`, `wappa/api/dependencies/inbox_context.py:163-175`, `wappa/api/dependencies/whatsapp_dependencies.py:46-50`

Principle: platform-branch

Severity: medium

Breaking + public surfaces: not breaking. The behaviour of `POST /api/{platform}/media/upload` stays the same, and `InboxExecutionContext` is an internal dependency.

Evidence: `get_media_uploader` branches on `PlatformType.WHATSAPP` and builds `WhatsAppMediaHandler` from `context.whatsapp_client()` (`media_transfer.py:94-100`). Every other Platform goes through `messenger.capability(IMediaLibrary)` (`:101-108`). But `WhatsAppMessenger.capability(IMediaLibrary)` already returns `WhatsAppMediaLibrary` (`whatsapp_messenger.py:86-87`), so the auditor's proposed fix is already half in place, and the branch is a leftover. According to the module docstring (`media_transfer.py:3-5`), the branch exists only so WhatsApp can use the form's explicit `media_type` and skip the temp file. `WhatsAppMediaLibrary.upload` ignores `family` (`media_library.py:37`). Templates work the same way: `ITemplateMessaging` is already a capability of `WhatsAppMessenger` (`whatsapp_messenger.py:84-85`), yet `template_transport()` gates with `whatsapp_only(...)` (`inbox_context.py:146`). The shared `InboxExecutionContext` imports `WhatsAppClient` (`:39`) and builds it in `whatsapp_client()` (`:163-175`). Its only consumers are `whatsapp_dependencies.get_whatsapp_client` (`whatsapp_dependencies.py:46-50`) and the media branch above.

Deletion test: If the WhatsApp branch in `get_media_uploader` is deleted, `LibraryMediaUploader` serves both Platforms through the two `IMediaLibrary` adapters that already exist, and no complexity comes back. If `whatsapp_client()` moves into `whatsapp_dependencies.py`, which is already WhatsApp-only, the shared context sheds its WhatsApp import, and the code lives in one WhatsApp file instead of a shared one.

Proposed fix: Delete the WhatsApp branch in `get_media_uploader`. If WhatsApp needs the explicit MIME type, let `WhatsAppMediaLibrary.upload` pass it through from `family`/the file, inside the adapter. Move WhatsApp client construction into `wappa/api/dependencies/whatsapp_dependencies.py`. This needs one neutral accessor on the context for the resolved credentials, so the private `_credentials` is not reached from outside. Replace the `whatsapp_only(...)` gate in `template_transport()` with the existing `requires_capability(ITemplateMessaging)` pattern. Keep `whatsapp_only` only for the routes that really have no capability (health, validators, limits). Do not add new capability interfaces.

ADR conflict: none. This is what ADR-0009 (route capability groups) and ADR-0021 ask for, and the code's own comment says "Prefer requires_capability" (`inbox_context.py:97-98`).

### 09-3 Dead Platform scaffolding: Telegram/Teams branches, an unused capability table, and an unused schema-factory/detector stack

Files: `wappa/schemas/core/types.py:12-17`, `wappa/schemas/core/types.py:152-260`, `wappa/processors/factory.py:16-160`, `wappa/processors/factory.py:241-255`, `wappa/processors/factory.py:377-545`, `wappa/webhooks/factory.py:17-766`, `wappa/webhooks/factory.py:437-451`, `wappa/core/events/webhook_factory.py:94-106`, `wappa/api/controllers/webhook_controller.py:53`, `wappa/api/controllers/webhook_controller.py:71`, `wappa/api/controllers/webhook_controller.py:226-227`, `ARCHITECTURE.md:307`, `wappa/webhooks/ARCHITECTURE.md:36`, `wappa/webhooks/ARCHITECTURE.md:95`, `wappa/webhooks/ARCHITECTURE.md:173-174`

Principle: over-engineering

Severity: medium

Breaking + public surfaces: breaking. `PlatformType.TELEGRAM` and `PlatformType.TEAMS` are members of a public enum (`docs/public-contract.md:335`). The helpers in `wappa.schemas.core.types` and the generated `WebhookURLFactory.generate_whatsapp_*` methods are importable. Under the clean-cut policy each one is listed in CHANGELOG, with no aliases kept.

Evidence: `PlatformType` has `TELEGRAM` and `TEAMS` (`types.py:15-16`), and no adapter exists for either. `PLATFORM_CAPABILITIES` and its helpers (`types.py:152-260`) have no callers outside `types.py`; the only other reference is a doc line (`wappa/webhooks/ARCHITECTURE.md:173`). `_create_processor` has Telegram/Teams branches whose only job is to raise (`processors/factory.py:241-255`). The auditor missed a bigger dead stack. `PlatformDetector` (`processors/factory.py:16-160`), `WebhookFactory`/`webhook_factory` (`:377-545`) and the whole `SchemaFactory`/`MessageSchemaRegistry`/`WebhookSchemaRegistry` module (`webhooks/factory.py`, singleton at `:766`) are referenced only by each other. A repo-wide search for `schema_factory`, `webhook_factory.`, `PlatformDetector` and `SchemaFactory` finds nothing outside those two files, in `wappa/` or in `tests/`. The live processors parse with their own models. The WhatsApp alias fallback (`webhooks/factory.py:437-451`, the auditor's 09-9) can never run: it catches `ValueError` from `MessageType("button"|"order"|"unsupported")`, but those are already members (`types.py`, `MessageType.BUTTON`, `ORDER`, `UNSUPPORTED`). `generate_whatsapp_webhook_url` and `generate_whatsapp_verify_url` (`core/events/webhook_factory.py:94-106`) only wrap `generate_webhook_url(PlatformType.WHATSAPP)`, and nothing calls them outside a backlog report. There is also a behaviour consequence. The controller's supported set is built from the whole enum (`webhook_controller.py:53`), so `GET /webhook/inboxes/telegram` passes `_is_supported_platform` (`:71`, `:226-227`) and answers a hub challenge for a Platform with no adapter. Only POST rejects it (`:116`). Two docs present the dead registries as live: `ARCHITECTURE.md:307` lists schema registration as a step for adding a Platform, and `wappa/webhooks/ARCHITECTURE.md:95` says the registry is "pre-loaded at startup".

Deletion test: Deleting all of this removes a few hundred lines and four branch families, and nothing comes back in any caller because there are no callers. The Telegram and Teams enum members are a hypothetical seam with zero adapters.

Proposed fix: Delete `PLATFORM_CAPABILITIES` and its helpers, `PlatformDetector`, `WebhookFactory`/`webhook_factory`, the raising branches, `wappa/webhooks/factory.py`, and the `generate_whatsapp_*` wrappers. Remove the `TELEGRAM` and `TEAMS` enum members. Tests that use `PlatformType.TELEGRAM` as an "unimplemented Platform" fixture need rewriting (`tests/test_inbox_identity.py:19`, `tests/test_inbox_credential_records.py:185`, `tests/test_whatsapp_payload_routing.py:201`, `tests/test_webhook_schema_ownership.py:390`, `tests/test_sse_event_hub.py:194`, `tests/test_platform_messaging_api.py:212`). With a closed enum, those rejection paths are enforced by the type system, so those tests either go or switch to asserting cross-Platform isolation between WhatsApp and Instagram. Build the controller's supported set from the 09-1 table, which also fixes the GET verification gap. Update `ARCHITECTURE.md:307` and `wappa/webhooks/ARCHITECTURE.md:36,95,106,116,173-174`.

ADR conflict: none. Check `docs/public-contract.md:335`, which lists `PlatformType` as public, and record the removed members in CHANGELOG.

### 09-4 WappaApp wires processors with a concrete import and two styles; the callback flag has a WhatsApp name

Files: `wappa/core/wappa_app.py:19`, `wappa/core/wappa_app.py:285-295`, `wappa/core/wappa_app.py:304`, `wappa/processors/whatsapp_processor.py:98`, `wappa/processors/instagram_processor.py:136`, `wappa/processors/base_processor.py:70`, `wappa/core/factory/wappa_builder.py:72`, `wappa/core/factory/wappa_builder.py:368-371`, `wappa/core/factory/wappa_builder.py:484`

Principle: DIP

Severity: low

Breaking + public surfaces: the `set_field_registry` part is not breaking. Renaming `WappaBuilder.mount_whatsapp_callback` is breaking: it is a method on a public class, but `docs/public-contract.md` does not document it, and its only caller is `wappa_app.py:304`.

Evidence: `wappa_app.py` imports the concrete `WhatsAppWebhookProcessor` (`:19`) only to do an isinstance check and call `set_field_registry` (`:287-290`). For Instagram it uses duck typing, `getattr(..., "set_field_registry", None)` (`:291-294`). Both processors define the same method (`whatsapp_processor.py:98`, `instagram_processor.py:136`), but `BaseWebhookProcessor` (`base_processor.py:70`) does not declare it. `mount_whatsapp_callback` and `_whatsapp_callback_mounted` (`wappa_builder.py:72`, `:368-371`, `:484`) record that the shared `/webhook/inboxes/{platform}` route is mounted for every Platform, so the WhatsApp name is a leftover from before multi-Platform.

Deletion test: With `set_field_registry` declared on `BaseWebhookProcessor`, eight lines and the concrete import collapse into a loop over the registered Platforms, and nothing comes back.

Proposed fix: Declare `set_field_registry` as abstract on `BaseWebhookProcessor`. Replace `:285-295` with `for p in PLATFORMS: processor_factory.get_processor(p).set_field_registry(...)` and drop the concrete import. Rename the builder flag and method to `mount_webhook_callback` / `_webhook_callback_mounted` as one clean cut, listed in CHANGELOG.

ADR conflict: none.

## Rejected findings

- 09-5 "Inbound runtime derives SSE identity with a WhatsApp-only branch": the evidence is wrong. `_derive_sse_identity` (`wappa/core/inbound/runtime.py:390-394`) returns `fallback_user_id`, which is the resolved webhook user id, for non-WhatsApp webhooks. So Instagram SSE events do carry the User's identity. Only `bsuid` and `phone` are `None`, and those are WhatsApp identifiers (`derive_identifiers`, `classify_meta_identifier`). Instagram has nothing to put in them. A neutral `user.sse_identity()` would add a method whose extra fields only one adapter fills. That is a hypothetical seam.
- 09-6 "Platform-keyed credential record selection is an if/else on INSTAGRAM": confirmed, but it duplicates 09-1, so it is merged there (`services.py:85-90`, `:118-123`, `:139-143`, `:149`, `:298-304`). The auditor's own fix already said to fold it into the 09-1 table.
- 09-7 "Instagram deauthorize route and WhatsApp-default parameters live in shared modules": a grab bag, rejected part by part. The `/inboxes/instagram/deauthorize` route (`wappa/api/routes/webhooks.py:107-135`) is a Platform-literal endpoint with no branch, sitting in the callback router, which is the composition root for callbacks. Moving it into a per-Platform route-mounting hook would add machinery for one route, so it stays. The `platform=PlatformType.WHATSAPP` defaults on `MediaUploadResult` and its siblings (`wappa/domain/models/media_result.py:26,55,78,149`) only matter to the WhatsApp media handler. Its 33 construction sites are all in `whatsapp_media_handler.py`, and the only other constructor, `media_transfer.py`, passes `platform` explicitly. The cost is cosmetic. The `register_webhook_field` default (`wappa/core/wappa_app.py:501`, `wappa/core/factory/wappa_builder.py:252`, `wappa/core/events/field_registry.py:111`) is the public contract's main use case (`docs/public-contract.md:71` documents `platform=` as the override). Making it required breaks every Host for little gain. The dead `generate_whatsapp_*` aliases are kept as part of 09-3.
- 09-8 "WappaCorePlugin hard-codes Platform display labels": cosmetic. The `labels` dict (`wappa/core/plugins/wappa_core_plugin.py:248-251`) affects only startup log casing and already falls back to `platform.value`. The legacy WhatsApp filter (`:244-245`) is a real routing rule. Once 09-1 lands, the label could come from the table entry, but on its own it is not a finding.
- 09-9 "WebhookSchemaRegistry message-type mapping has a WhatsApp-specific fallback": the mechanism is misread. The fallback (`wappa/webhooks/factory.py:437-451`) can never run, because the three strings are already `MessageType` members, and the module has no runtime callers anyway. Building a per-Platform alias table for it, as the auditor proposed, would add over-engineering to dead code. Its deletion is part of 09-3.

## Checked and legitimate

- `wappa/domain/inbox/identity.py:80-87` `cache_namespace` (`<platform>__<inbox_id>`): Platform-qualified with no per-Platform code. Inbox isolation is Platform-neutral.
- `wappa/core/inbound/webhook_routing.py` and `wappa/core/inbound/instagram_routing.py`: per-Platform payload routers. They are adapter modules and become the `route_payload` entries in the 09-1 table.
- `wappa/processors/whatsapp_processor.py`, `wappa/processors/instagram_processor.py`, `wappa/messaging/whatsapp/**`, `wappa/messaging/instagram/**`: each adapter naming its own Platform is expected.
- `wappa/connections/whatsapp.py:73`, `wappa/connections/instagram.py:226` implementing `IInboxConnector` (`wappa/connections/contract.py:175`): two adapters, a real seam. The Host composes connectors, so the runtime needs no connector registry.
- `wappa/domain/inbox/credentials.py` `Literal[PlatformType.X]` discriminators: the documented growth of the union by one member per Platform (ADR-0011).
- `wappa/messaging/whatsapp/messenger/whatsapp_messenger.py:82-88` `capability(...)`: capability lookup with `ITemplateMessaging` (WhatsApp-only) and `IMediaLibrary` (both Platforms). This is the right pattern for Platform-only extensions.
- `wappa/api/routes/whatsapp_combined.py:128-168`: all route families are mounted under `/api/{platform}` as capability groups (ADR-0009, ADR-0021). The WhatsApp-named module names are historical, not branches.
- `wappa/core/inbound/runtime.py:309` `processor_factory.get_processor(platform)`: a keyed lookup, not a branch.
- `wappa/core/plugins/wappa_core_plugin.py:244-245`: the legacy-mode filter to WhatsApp reflects the real legacy single-Inbox rule.
- `wappa/core/inbound/runtime.py:390-420`: the WhatsApp-only `bsuid`/`phone` fields of SSE identity (see 09-5).
- `wappa/domain/messaging_targets.py:162` `CommentTarget` guard: Comments are a declared Instagram-only capability.

## Interface proposal

This is not a new abstract hierarchy. Four of the five target interfaces already exist and have two adapters each. The missing piece is one composition-root table that the shared runtime looks up instead of branching.

- **PlatformWebhooks**: `BaseWebhookProcessor` (`wappa/processors/base_processor.py:70`), plus `set_field_registry` declared on it (09-4), plus the per-Platform `route_payload(payload, resolver) -> tuple[RoutedWebhookDelivery, ...]` functions that already exist in `wappa/core/inbound/*_routing.py`. Two adapters, so a real seam.
- **SendingMessages**: `IMessenger`, one method per action (ADR-0016). Two adapters. No change.
- **HandlingMedia**: `IMediaLibrary` with `upload(path, family)` and `download(media_id)` (`wappa/domain/interfaces/media_library.py:38-45`), reached through `messenger.capability(IMediaLibrary)`. Both Platforms implement it, so the remaining work is to delete the WhatsApp shortcut (09-2), not to design a new seam. Whether to promote it from capability to core `IMessenger` method is a separate ADR-0016 question, and lookup cost alone does not justify it.
- **ProfileReading**: does not exist. Do not add it now. With at most one Platform able to fill it, it would be a hypothetical seam. When a second Platform can read a User's profile, add it as an `IMessenger` capability, the same way `IConversationContentReader` is added, with one read method returning `ReadResult[UserProfile]`.
- **InboxConnection**: `IInboxConnector` (`wappa/connections/contract.py:175`), two adapters, composed by the Host. It is not part of the runtime table.
- **Platform-only extensions**: `ITemplateMessaging` (WhatsApp, which exists), `ICommentControls` (Instagram, which exists), and Flows and Calls behind the same `capability(kind)` lookup. Shared HTTP dependencies gate them with `requires_capability(kind)`, never with `whatsapp_only(...)` (09-2).

The composition root (`wappa/platforms.py`) holds:

```python
@dataclass(frozen=True)
class PlatformEntry:
    create_processor: Callable[[], BaseWebhookProcessor]
    route_payload: Callable[[dict, IInboxCredentialResolver], Awaitable[tuple[RoutedWebhookDelivery, ...]]]
    build_messenger: Callable[[ResolvedInboxCredentials, MessengerDeps], IMessenger]
    active_record: type[ActiveInboxCredentialRecord]
    inactive_record: type[InactiveInboxCredentialRecord]
    builtin_fields: Callable[[], frozenset[str]]
    display_name: str

PLATFORMS: dict[PlatformType, PlatformEntry]  # whatsapp, instagram; lazy imports inside the callables
```

The table has two entries. Any key missing from it fails loudly and never falls through to WhatsApp. After 09-1 and 09-3, a third Platform touches its adapter packages (`wappa/webhooks/<p>/`, `wappa/processors/<p>_processor.py`, `wappa/core/inbound/<p>_routing.py`, `wappa/messaging/<p>/`, optionally `wappa/connections/<p>.py`), plus one `PlatformType` member, one `InboxCredentialRecord` union member pair in `wappa/domain/inbox/credentials.py`, and one `PLATFORMS` entry. Today it touches 9 sites spread over 6 shared files, plus the dead registries that the docs wrongly present as live.
