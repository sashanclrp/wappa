# Sending messages (core interface 2)

Status reviewed 2026-11-06: historical pre-hardening audit. Findings and file:line references below describe the audited baseline. Use the [plan status table](../plan.md#code-reality-2026-11-06) for implemented and remaining work; do not rebuild a resolved finding from this snapshot.


## Summary

Verifier pass over the auditor's eight findings for SendingMessages (`IMessenger`). The contract follows ADR-0025's one method per action, the pipeline has no Platform branches, and Templates, comments and the media library all sit behind `capability()`. Two defects are real and high severity. The neutral contract depends on WhatsApp-owned types: `MessageResult` is imported at runtime from the WhatsApp package by `wappa/domain/results.py`, and `InteractiveHeader`/`ListSection` are WhatsApp wire models in the `IMessenger` signatures. The other confirmed findings are low severity: two hand-kept lists of supported operations plus a qualifier token, two separate `capability()` lookups, WhatsApp-only factory ABCs (plus a dead `MessageBuilder`) sitting in `wappa/domain/`, pipeline wrappers that copy every signature by hand with no parity test, and an optional `mark_as_read` target that Instagram requires. The ISP item (02-8) is rejected as a finding because it recommends no change; it moves to legitimate. Severities for 02-3 and 02-4 drop from medium to low, and one of the auditor's reasons in 02-3 was wrong.

## Confirmed findings

### 02-1 MessageResult is WhatsApp-owned but is the neutral send result of every Platform

- **Files:** `wappa/messaging/whatsapp/models/basic_models.py`, `wappa/domain/results.py`, `wappa/domain/interfaces/messaging_interface.py`, `wappa/domain/interfaces/template_messaging.py`, `wappa/messaging/instagram/messenger.py`, `wappa/messaging/__init__.py`, `wappa/models/__init__.py`, `docs/public-contract.md`
- **Principle:** platform-leak
- **Severity:** high
- **Breaking + public surfaces:** breaking. Affects `wappa.messaging.MessageResult`, `wappa.models.MessageResult`, `docs/public-contract.md` (Messenger section and the line 56 export note), and the HTTP API response schemas that serialize it.
- **Evidence:** `MessageResult` is defined at `basic_models.py:101` and defaults `platform` to `PlatformType.WHATSAPP` (`:108`). It carries WhatsApp evidence: `recipient_bsuid`/`recipient_phone`/`recipient_parent_bsuid` (`:114-122`), a BSUID digit-echo validator (`:141-157`), `api_response: WhatsAppAPIResponse` (`:135`) and the WhatsApp-only `from_api_response` (`:159`). Instagram evidence has to go into a separate excluded `platform_response` field (`:104-106`) because `api_response` is WhatsApp-typed. The neutral layer imports it from the Platform package. `wappa/domain/results.py:22` does this at runtime, not just for type checking, and its docstring (`:3-4`) calls the location "historical". `messaging_interface.py:21` and `template_messaging.py:25` import it under TYPE_CHECKING, and Instagram imports it directly (`instagram/messenger.py:60`). `docs/public-contract.md:56` admits the class "still lives in the WhatsApp basic-models module".
- **Deletion test:** Moving the class into `wappa/domain/results.py` removes the domain-to-WhatsApp import edge. As things stand, that edge shows up again in every neutral consumer (results, both interfaces, the Instagram adapter). Neutral ownership earns its place.
- **Proposed fix:** Define `MessageResult` in `wappa/domain/results.py` next to `CommentResult`/`ControlResult`. Make `platform` required with no WhatsApp default, and keep `platform_response` as the single native-evidence field for every Platform. Move `from_api_response` into a WhatsApp-side helper (for example a function in the WhatsApp messenger package), and type the WhatsApp response as `platform_response`, or keep `api_response` only on a WhatsApp subclass. Before keeping `recipient_bsuid`/`recipient_phone`/`recipient_parent_bsuid` and the echo validator in the neutral type, check them against ADR-0022's neutral User identity. If they are WhatsApp-only Delivery Address evidence, they move with the subclass. Following the clean-cut rule, the WhatsApp module does not re-export it; list the break in CHANGELOG.
- **ADR conflict:** none. The public contract already describes the current location as a leftover.

### 02-2 InteractiveHeader and ListSection are WhatsApp wire models in the neutral IMessenger signature

- **Files:** `wappa/domain/interfaces/messaging_interface.py`, `wappa/messaging/whatsapp/models/interactive_models.py`, `wappa/messaging/instagram/messenger.py`, `wappa/domain/interactive.py`, `docs/public-contract.md`
- **Principle:** platform-leak
- **Severity:** high
- **Breaking + public surfaces:** breaking. Affects the `IMessenger.send_button_message` / `send_list_message` signatures, the `wappa.messaging` exports of `InteractiveHeader`, `HeaderType` and `ListSection` (`wappa/messaging/__init__.py:73-75`), and `docs/public-contract.md:45,56`.
- **Evidence:** `send_button_message` takes `header: InteractiveHeader | None` (`messaging_interface.py:~200`) and `send_list_message` takes `sections: list[ListSection]`, both imported from `wappa.messaging.whatsapp.models.interactive_models` (`:22-25`). In the same contract, `send_list_message`'s header is a plain `str`, so the two interactive headers do not even match each other. Instagram imports the WhatsApp models (`instagram/messenger.py:61-64`) and reverse-engineers them. `_header_kind` unwraps the enum with `getattr(kind, "value", kind)` (`:125-129`). `_header_link` digs `(header.image or {}).get("link")` and errors with "WhatsApp media IDs do not exist on Instagram" (`:132-140`). Video and document headers are rejected at `:~609-612`. The public contract tells Instagram Hosts to build a WhatsApp dict, `InteractiveHeader(type=HeaderType.IMAGE, image={"link": ...})` (`public-contract.md:45`). Neutral values (`ReplyButton`, `UrlButton`, `MessageCard`) already exist in `wappa/domain/interactive.py`, which shows the intended pattern. Only header and list never moved.
- **Deletion test:** A neutral header and list type absorbs the dict-digging translation in Instagram and stops the contract from importing WhatsApp. The WhatsApp wire models stay, as private adapter output. Real variation exists across two adapters, so this is a real seam and not a hypothetical one.
- **Proposed fix:** Add `ButtonHeader` (text, or image by `url` or Platform `media_id`) and neutral `ListSection`/`ListRow` to `wappa/domain/interactive.py`. Use the same header type for both button and list messages. `WhatsAppMessenger` maps them onto its wire models internally, and Instagram reads typed fields. Leave video/document headers out of the neutral type until a second Platform supports them; WhatsApp can expose them later if they are needed. Platform limits (24/10/10 on WhatsApp, 640/80 on Instagram) stay as per-adapter validation, not in the neutral type.
- **ADR conflict:** none. This fits ADR-0025's typed neutral contract values (same pattern as `ContactCard`).

### 02-3 Supported operations are two hand-kept string lists plus a non-method qualifier token

- **Files:** `wappa/domain/interfaces/messaging_interface.py`, `wappa/messaging/whatsapp/messenger/whatsapp_messenger.py`, `wappa/messaging/instagram/messenger.py`
- **Principle:** DRY
- **Severity:** low (auditor: medium)
- **Breaking + public surfaces:** non-breaking. Affects `IMessenger.supported_operations`.
- **Evidence:** The base default is `frozenset({"send_text"})` (`messaging_interface.py:46-48`). WhatsApp re-lists 15 names inline (`whatsapp_messenger.py:91-112`), and Instagram keeps `_OPERATIONS` (`instagram/messenger.py:175-192`) with an extra `"send_text:private_reply"` token (`:178`) that names no method. Both lists match their adapter's overrides today (Instagram overrides exactly the 13 methods listed at `:330-722`), so the cost is drift risk, not a live bug. Correction: the auditor said that callers "can still hit UnsupportedOperationError after checking" because `send_contact_request`/`send_location_request` are missing from Instagram's set, and that is wrong. Missing means unsupported, which is consistent. The real gap is that a listed operation can still reject some arguments, for example an Instagram video header (`:~609`). That is expected per-argument validation, not an LSP violation.
- **Deletion test:** The set is a derived view of which methods an adapter overrides. Deleting the hand-written lists loses nothing if the base derives them, and the qualifier token is the only fact that cannot be derived.
- **Proposed fix:** In `IMessenger.supported_operations`, derive the names from the operation methods whose implementation differs from the base (`getattr(type(self), m) is not getattr(IMessenger, m)`, with `send_text` always included), and union it with an optional class attribute for qualifier tokens like `send_text:private_reply`. Document the token format in the public contract. Delete both inline lists. Do not add a separate typed capability registry here, because that would be over-engineering for one token.
- **ADR conflict:** none.

### 02-4 capability() lookup is implemented twice with different semantics

- **Files:** `wappa/messaging/whatsapp/messenger/whatsapp_messenger.py`, `wappa/messaging/instagram/messenger.py`, `wappa/domain/interfaces/messaging_interface.py`
- **Principle:** DRY
- **Severity:** low (auditor: medium)
- **Breaking + public surfaces:** non-breaking. Affects `IMessenger.capability` / `require_capability`.
- **Evidence:** WhatsApp uses an identity if-chain (`whatsapp_messenger.py:82-88`) and builds a new `WhatsAppMediaLibrary` on every call. Instagram uses a `dict[type, object]` built once (`instagram/messenger.py:223-229`), with an `isinstance` fallback so that asking for the concrete class works (`:249-258`). The same question therefore gets different answers: `capability(WhatsAppMediaLibrary)` returns `None` on WhatsApp, while `capability(InstagramMediaLibrary)` resolves on Instagram. Which capabilities each Platform has is legitimate Platform content. Only the lookup is duplicated.
- **Deletion test:** One base implementation absorbs both lookups, and each adapter only declares a mapping. Every future WhatsApp capability in the target shape (Flows, Calls) would otherwise be one more `if` in the chain.
- **Proposed fix:** Implement `capability()` once in `IMessenger` over a `_capabilities: Mapping[type, object]` that each adapter fills in its constructor, keeping the `isinstance` fallback in that one place. WhatsApp registers `ITemplateMessaging: self` and a single cached `WhatsAppMediaLibrary`. Skip lazy factories: both libraries are cheap to build eagerly.
- **ADR conflict:** none.

### 02-5 MessageFactory / MediaFactory ABCs and MessageBuilder are WhatsApp-only code posing as neutral domain

- **Files:** `wappa/domain/factories/message_factory.py`, `wappa/domain/factories/media_factory.py`, `wappa/domain/factories/__init__.py`, `wappa/domain/builders/message_builder.py`, `wappa/api/dependencies/whatsapp_dependencies.py`, `wappa/api/routes/whatsapp/whatsapp_messages.py`, `wappa/api/routes/whatsapp/whatsapp_media.py`, `wappa/messaging/whatsapp/messenger/whatsapp_messenger.py`
- **Principle:** hypothetical-seam
- **Severity:** low
- **Breaking + public surfaces:** breaking only if `wappa.domain.factories.MessageFactory` is treated as public (it is exported from `wappa/domain/factories/__init__.py:3,6`). Also affects the FastAPI deps `get_whatsapp_message_factory`, `get_whatsapp_media_factory` and `get_message_builder`.
- **Evidence:** Each abstract `MessageFactory` (`message_factory.py:10`) and `MediaFactory` (`media_factory.py:10`) has exactly one subclass, `WhatsAppMessageFactory` (`:36`) and `WhatsAppMediaFactory` (`:70`). Every consumer is WhatsApp: `whatsapp_messenger.py:9-10,78-79` and its payload calls at `:256,299,535-566`, `whatsapp_dependencies.py:21-22,41-43,110-111`, and the WhatsApp routes that annotate with the ABC (`whatsapp_messages.py:25,210`; `whatsapp_media.py:37,539`). Instagram never uses them. The method signatures (`recipient: str`, `message_factory.py:19,44`) are WhatsApp-native. The auditor missed `MessageBuilder` (`message_builder.py:10,27`): it is built only on `MessageFactory`, and its only reference is `get_message_builder` (`whatsapp_dependencies.py:126-134`), which no route or test uses (`rg` finds no other caller).
- **Deletion test:** Deleting the two ABCs brings back no complexity, because nothing is polymorphic over them. Deleting `MessageBuilder` and `get_message_builder` brings back nothing either, since they are dead code. The concrete WhatsApp factories do earn their place, because they hold payload construction and limits.
- **Proposed fix:** Collapse the ABCs into their concrete classes, move both factories under `wappa/messaging/whatsapp/`, and retype the WhatsApp routes against the concrete class. Delete `MessageBuilder`, `wappa/domain/builders/` (if that leaves it empty) and `get_message_builder`. List the removed exports in CHANGELOG.
- **ADR conflict:** none.

### 02-6 MessengerPipeline copies every IMessenger signature by hand with no parity test

- **Files:** `wappa/core/messaging/pipeline.py`, `wappa/domain/interfaces/messaging_interface.py`, `tests/test_one_method_per_action.py`
- **Principle:** DRY
- **Severity:** low
- **Breaking + public surfaces:** non-breaking. No public surfaces.
- **Evidence:** Each wrapper restates its parameters and builds a name-to-value dict in positional order (for example `send_text`, `pipeline.py:276-292`). `_invoke` turns `arguments.values()` into positional `args` (`:230-261`), so correctness depends on dict order matching the adapter's parameter order. `_PipelineTemplates` follows the same pattern. `rg` over `tests/` finds no signature parity test: `test_one_method_per_action.py` checks contract membership (`:75,92`), not signatures. `mark_as_read` bypassing middleware (`:294-302`) is deliberate and documented.
- **Deletion test:** The pipeline earns its place, because without it middleware would move into callers. The copied signatures are boilerplate, but a generated wrapper would cost static typing.
- **Proposed fix:** Keep the explicit wrappers and add one test: for every public operation on `IMessenger` (and `ITemplateMessaging`), `inspect.signature` of the pipeline wrapper equals the interface's (names, order, kinds, defaults). Do not generate the wrappers.
- **ADR conflict:** none.

### 02-7 mark_as_read types target as optional although Instagram requires it

- **Files:** `wappa/domain/interfaces/messaging_interface.py`, `wappa/messaging/instagram/messenger.py`, `wappa/messaging/whatsapp/messenger/whatsapp_messenger.py`, `docs/public-contract.md`
- **Principle:** LSP
- **Severity:** low
- **Breaking + public surfaces:** breaking. Affects `IMessenger.mark_as_read` and `docs/public-contract.md:44`.
- **Evidence:** Both the base and WhatsApp declare `target: DirectMessage | None = None` (`whatsapp_messenger.py:284-295`). WhatsApp only checks `target` against the Inbox when it is given. Instagram raises `ValueError` when `target is None` (`instagram/messenger.py:734-738`), so the subtype has a stronger precondition than the contract states, and only the docs warn about it (`public-contract.md:44`: "`target` required"). ADR-0025 rule 1 already writes the neutral call as `mark_as_read(message_id, typing, target)` (`docs/adr/0016-*.md:10`).
- **Deletion test:** Making `target` required removes the strengthened precondition. WhatsApp loses nothing, and Hosts always have the inbound sender when they mark a message read.
- **Proposed fix:** Make `target: DirectMessage` required and positional-or-keyword in the base, both adapters and the pipeline. WhatsApp keeps its Inbox check. Do not add a `ReadReceipt` value object, because one field does not need a new type. Record the break in CHANGELOG.
- **ADR conflict:** none. This aligns the code with ADR-0025 rule 1.

## Rejected findings

- **02-8 IMessenger ISP split:** Rejected as a finding. The auditor's own conclusion is "no split", which is a confirmation of the current design, not a defect. It moves to Checked and legitimate.
- **02-3 (partial) "callers can still hit UnsupportedOperationError after checking":** Rejected sub-claim. Instagram's set omits `send_contact_request`/`send_location_request`, and those calls raise, which is consistent. The finding stays only as a DRY/drift issue at low severity.
- **02-4 (partial) "callable-as-type casting":** Rejected as a defect on its own. `cast(type, kind)` is a typing workaround for `Callable[..., C]` and has no runtime effect. It is cosmetic and is dropped from the evidence that matters.

## Checked and legitimate

- `IMessenger` stays one facade with no ISP split. It has about 16 operations bound to one Inbox, and splitting it would push 3-4 references into every caller (pipeline, routes, Host). Two real adapters implement it coherently, and the families that genuinely belong to one Platform (Templates, media library, comments, history, content reads) are already capabilities.
- The raising `UnsupportedOperationError` defaults on `IMessenger` are sound under LSP: every method exists and fails explicitly before any I/O.
- `MessengerPipeline._call_raw` routes Template methods through `require_capability(ITemplateMessaging)` (`pipeline.py:222-228`), and `capability()` wraps only Templates so that middleware still sees those sends (`:268-274`). This is Platform-neutral dispatch with no Platform branch.
- `target.resolve(InboxRef(platform=self.platform, inbox_id=self.inbox_id))` in `_invoke` (`pipeline.py:251`) is a neutral Inbox guard, not a Platform branch.
- `wappa/domain/factories/messenger_factory.py`: the Platform selection branch lives in the Messenger composition root, which is the right home for it. The WhatsApp concrete imports at `:17-30` are composition-root wiring. (Residual, outside this area: the composition root sits under `wappa/domain/`, which is a layering wrinkle and not a sending-contract defect.)
- Instagram-only capabilities registered in `instagram/messenger.py:223-229` (comments, content reader, attachments, media library, history) match the target's "explicit capability extensions".
- `wappa/domain/results.py`: `CommentResult`/`ControlResult`/`OperationOutcome`/`message_outcome` are good neutral design. Only `MessageResult`'s location is wrong (02-1).
- `ITemplateMessaging` as a separate WhatsApp capability with `TEMPLATE_METHODS` routing is correct.
- The missing `send_reaction` is already recorded as a core gap in ADR-0025 (`:61`) with a backlog draft. It is not a new finding.

## Interface proposal

SendingMessages stays the single Inbox-bound `IMessenger` facade (ADR-0025, one method per action). This pass adds no new seams. The changes only remove WhatsApp types from the contract and remove duplicate bookkeeping.

- **Neutral types, all under `wappa/domain/`, with no `wappa.messaging.*` import.** `MessageResult` moves to `wappa/domain/results.py` with `success`, `platform` (required), `message_id`, `recipient`, `attempted_recipients`, `error`, `error_code`, `timestamp`, `inbox_id` and `platform_response`. WhatsApp-only evidence and `from_api_response` move to the WhatsApp adapter, and the BSUID fields stay neutral only if ADR-0022 says they are neutral. `ButtonHeader` (text, or image by `url` or `media_id`), `ListSection` and `ListRow` go in `wappa/domain/interactive.py` next to `ReplyButton`, `UrlButton` and `MessageCard`.
- **Methods (unchanged except where marked):** `send_text`, `mark_as_read(message_id, typing, target)` with `target` now required, `send_image`, `send_video`, `send_audio`, `send_document`, `send_sticker`, `send_button_message(buttons, target, body, header: ButtonHeader | None, footer, reply_to_message_id)`, `send_list_message(sections: list[ListSection], target, body, button_text, header: ButtonHeader | None, footer, reply_to_message_id)`, `send_cta_message`, `send_carousel`, `send_contact_request`, `send_contact`, `send_location`, `send_location_request`. `send_reaction(message_id, emoji, target)` is the one known addition, per ADR-0025.
- **Introspection:** `capability(kind)` / `require_capability(kind)` are implemented once in `IMessenger` over a plain `_capabilities: Mapping[type, object]` that adapters fill in their constructors. `supported_operations` is derived from overridden methods plus an optional qualifier-token set (`send_text:private_reply`).
- **Adapters:** WhatsApp registers `ITemplateMessaging` and `IMediaLibrary`, and later Flows and Calls when they exist, not before. Instagram registers its five existing capabilities. Its WhatsApp payload factories become private concrete classes under `wappa/messaging/whatsapp/`, with no neutral ABC.
- **New Platform:** supplies one `IMessenger` subclass, its `_capabilities` mapping and one branch in the `MessengerFactory` composition root. Shared code needs no other edit.
- **Guard rail:** one parity test that the pipeline (and `_PipelineTemplates`) mirrors the `IMessenger` / `ITemplateMessaging` signatures exactly.
