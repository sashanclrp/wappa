# DDD docs: ADRs, CONTEXT, ARCHITECTURE, rules, sediment

## Summary

This is the verifier pass on the auditor's 12 findings. I re-opened every cited file:line. Seven findings hold after rescoping, five are rejected, and one is added. The auditor's main proposal was to rewrite 21 ADRs into 7 consolidated ones, and I rejected it. ADRs are an append-only decision log. ADR-0001, 0002, 0005 and 0015 already carry supersession banners that name the replaced symbols, so a rewrite would erase history and create churn with no reader benefit. The doc defects that matter are listed here. (1) Root `ARCHITECTURE.md:294-296` claims that the router, dispatcher and factory resolve registered adapters, but the code has hard-coded WhatsApp/Instagram branches. The checklist further down that file tells the truth. (2) `CONTEXT.md:204` points readers at `owner_id`, which `CONTEXT.md:43` and `:210` forbid. (3) ADR-0021:13 says Templates have no capability interface, yet `ITemplateMessaging` exists and `public-contract.md` documents it. (4) ADR-0007 and ADR-0014 have no banner pointing at the ADRs that changed them. (5) `TEMPLATE_API_GUIDE.md` describes a request shape and event flow the route no longer has. (6) `META_PRODUCTION.md` is a stray personal Postman link. The cross-doc DRY finding and the META-CHANGELOGS relocation are rejected as unsupported or cosmetic.

## Confirmed findings

### 10-06 Root ARCHITECTURE.md claims adapter-registry resolution that the code does not have

- Files: `ARCHITECTURE.md`, `wappa/api/controllers/webhook_controller.py`, `wappa/domain/factories/messenger_factory.py`
- Principle: stale-doc
- Severity: medium
- Breaking + public surfaces: no; none
- Evidence: `ARCHITECTURE.md:294-296` (Multi-Platform Strategy, item 4) says "The router, dispatcher, and factory resolve registered adapter capabilities rather than treating a route name as proof that an adapter is installed." The code hard-codes the Platform set and branches by Platform. See `webhook_controller.py:116` (`if platform_type not in {PlatformType.WHATSAPP, PlatformType.INSTAGRAM}`), `webhook_controller.py:136-140` (`route_instagram_payload if platform_type is PlatformType.INSTAGRAM else route_whatsapp_payload`), `messenger_factory.py:111` (the same hard-coded set), `messenger_factory.py:131` (`if inbox_ref.platform is PlatformType.INSTAGRAM`) and `messenger_factory.py:198` (a literal list). The same file's checklist at `ARCHITECTURE.md:306-312` correctly names these sites as "the Platform branch in ...". So the doc contradicts itself, and item 4 is the false half. Item 2 (`ARCHITECTURE.md:292`) also lists only WhatsApp adapter paths, although Instagram is implemented.
- Deletion test: delete the item 4 sentence and nothing is lost. The checklist already carries the accurate picture, and the false claim is the one place a reader would conclude that the multi-Platform goal is already met.
- Proposed fix: reword item 4 to state today's truth: `PlatformType` is the vocabulary, and the callback controller and Messenger factory each hold one Platform branch, listed in the checklist below as known debt. Add the Instagram paths to item 2. When the code-side audits replace these branches, rewrite the checklist to "implement the adapters and register them in one place". Do not edit the doc toward a registry that does not exist yet. The auditor rated this high as if the doc were the defect. The code branches belong to the code-area audits, and this doc finding is medium.
- ADR conflict: none. ADR-0016 is consistent with the target.

### 10-01 CONTEXT.md Anti-Language maps `tenant` to `owner_id`, which CONTEXT.md forbids

- Files: `CONTEXT.md`
- Principle: stale-doc
- Severity: medium
- Breaking + public surfaces: no; none
- Evidence: `CONTEXT.md:204` maps `tenant`/`tenant_id` to "`inbox_id` ... or `owner_id` (if it means a business grouping supplied by the host)". `CONTEXT.md:43` says "`owner_id` Not a Wappa runtime concept ... Wappa does not store, route, or scope by owner_id". `CONTEXT.md:210` lists `Owner` as forbidden Wappa runtime language. `grep -rn owner_id wappa/` returns nothing.
- Deletion test: deleting the `owner_id` clause removes the contradiction, and nothing reappears elsewhere.
- Proposed fix: make `CONTEXT.md:204` read "`inbox_id` if it means the Platform-facing identity; business tenancy is the Host's concern and has no Wappa term". Lines 43 and 210 stay as the single home of the owner rule.
- ADR conflict: none

### 10-13 ADR-0021 says Templates have no capability interface, but `ITemplateMessaging` exists and is public (added by verifier)

- Files: `docs/adr/0021-platform-messaging-http-api.md`, `docs/public-contract.md`, `wappa/domain/interfaces/template_messaging.py`, `wappa/api/ARCHITECTURE.md`
- Principle: stale-doc
- Severity: medium
- Breaking + public surfaces: no; `docs/public-contract.md` (read-only reference)
- Evidence: `0021:13` decision 4 says "Routes with no capability interface yet (Templates, Template info, the WhatsApp Media API, ...) are WhatsApp-only and answer the same 501." `template_messaging.py:28` defines `class ITemplateMessaging(ABC)`, and it landed in the same commit, 5fb127f. `public-contract.md:52` and `:60-62` document `ITemplateMessaging` as the WhatsApp Template capability reached through `messenger.capability()`. `wappa/api/ARCHITECTURE.md:34` lists the gated capabilities without `ITemplateMessaging`, and the template routes (`wappa/api/routes/whatsapp/whatsapp_templates.py:35-60`) depend on `get_inbox_execution_context`, not `requires_capability(ITemplateMessaging)`. The docs disagree about whether Templates are a capability-gated extension, which is exactly the "Platform-only capability as explicit extension" rule under audit.
- Deletion test: not a deletion candidate. Two docs give opposite answers to "is Templates a capability?", and that confusion would reappear in every route a future contributor adds.
- Proposed fix: fix ADR-0021:13 with a dated status note. Templates are the `ITemplateMessaging` capability. Template info, the WhatsApp Media API, limits and validators remain the routes with no capability interface. Hand the gating gap (template routes not using `requires_capability(ITemplateMessaging)`) to the API code audit. Then add `ITemplateMessaging` to `wappa/api/ARCHITECTURE.md:34` once the routes gate on it.
- ADR conflict: ADR-0021

### 10-02 ADR-0007 and ADR-0014 lack the back-pointer banners that their sibling ADRs carry

- Files: `docs/adr/0007-embedded-outbound-route-control.md`, `docs/adr/0014-instagram-text-and-explicit-messenger-targets.md`, `docs/adr/0021-platform-messaging-http-api.md`, `docs/adr/0019-delivery-addresses.md`
- Principle: stale-doc
- Severity: low
- Breaking + public surfaces: no; none
- Evidence: `0007:3` says `**Status:** Accepted` with no note, and `0007:9`, `:31` and `:34` describe and show `create_whatsapp_router(...)`. `0021:13` says "`create_whatsapp_router` is removed (clean cut, no alias)", and `docs/migration/v0.34.0-from-0.33.md:142` confirms this. `0019:3` says it "Amends ADR-0014 (`DirectMessage` held one address)", but `grep 0019 docs/adr/0014*` finds nothing. ADR-0001:3, 0002:3, 0005:3-5 and 0015:3 all use the banner pattern, so these two are the gaps. `0009` does not name the removed symbol (grep), so it needs no banner.
- Deletion test: the decision in 0007 (independent include flags for route groups) is still live under 0021, so 0007 must stay. Only the reader trap needs to go.
- Proposed fix: add a one-line banner to 0007: "`create_whatsapp_router` was replaced by `create_messaging_router` mounted at `/api/{platform}` (ADR-0021); the route-group flags below carry over unchanged." Add one to 0014: "Amended by ADR-0019: targets carry every known Delivery Address." Do not consolidate ADRs.
- ADR conflict: ADR-0007, ADR-0014

### 10-10 TEMPLATE_API_GUIDE.md documents a request shape and event flow the Template route no longer has

- Files: `TEMPLATE_API_GUIDE.md`, `wappa/api/routes/whatsapp/whatsapp_templates.py`, `wappa/messaging/template_transport.py`
- Principle: stale-doc
- Severity: low
- Breaking + public surfaces: no; none (root doc, tracked, no inbound links)
- Evidence: `TEMPLATE_API_GUIDE.md:9-16` shows the flow `Messenger.send_media_template()` -> `@dispatch_message_event` -> `APIMessageEvent`. `:96` documents `recipient` as a string, and `:141` documents a `state_config` field. The live route `whatsapp_templates.py:45-52` takes a `MediaTemplateTransportRequest`, returns `TemplateTransportResult` through `context.template_transport(app).send()`, and carries no `@dispatch_message_event`. In `template_transport.py:109-139`, recipients are typed objects (`PhoneNumberTemplateRecipient`, `BsuidTemplateRecipient`), and `state_config` appears nowhere in that module. A grep of `.md`/`.py`/`.toml` finds no inbound links. The auditor called it "unlinked"; it is also wrong, not merely misplaced.
- Deletion test: delete it, and the caller-visible Template transport surface is still documented in `docs/public-contract.md:52`, `:62` and `:136-145` and in ADR-0006. No complexity reappears.
- Proposed fix: `git rm TEMPLATE_API_GUIDE.md`. If a Template how-to is wanted, write it fresh from `template_transport.py` under `docs/` and link it from `public-contract.md`. Do not move the stale text.
- ADR conflict: none

### 10-05 CONTEXT-MAP.md omits API, External Webhooks and Connections

- Files: `CONTEXT-MAP.md`, `ARCHITECTURE.md`, `wappa/connections/contract.py`
- Principle: stale-doc
- Severity: low
- Breaking + public surfaces: no; none
- Evidence: the contexts table in `CONTEXT-MAP.md:7-16` has eight rows (Root, Webhooks, Messaging, Persistence, SSE, Expiry, Plugins, CLI). `wappa/api/ARCHITECTURE.md` and `wappa/core/external_webhooks/ARCHITECTURE.md` exist, and the root `ARCHITECTURE.md:339-349` "Deeper Architecture Docs" table lists both. `wappa/connections/` (1243 lines across 5 files) appears in neither table; its only doc home is the Instagram adapter table at `ARCHITECTURE.md:328-331`. The auditor said connection and external-webhook terms "live nowhere". That is false: root `CONTEXT.md:106` defines Inbox Connector, and `:120-127` defines External Webhook Source, Webhook ID, External Event and Signature Verifier.
- Deletion test: the map exists to locate each context's docs, and three contexts cannot be found from it.
- Proposed fix: add three rows to `CONTEXT-MAP.md`. API (`wappa/api/`) and External Webhooks (`wappa/core/external_webhooks/`) point to the root CONTEXT.md and their existing ARCHITECTURE.md. Connections (`wappa/connections/`) points to the root CONTEXT.md and ADR-0017. Add a Connections row to `ARCHITECTURE.md:339-349`. Do not create new per-context CONTEXT.md files. The terms already live in root CONTEXT.md, and extra glossaries would duplicate them. Write a `wappa/connections/ARCHITECTURE.md` only if a third connector or a non-Meta Login arrives.
- ADR conflict: none

### 10-07 Root ARCHITECTURE.md "Key Architectural Decisions" is a partial, stale ADR digest

- Files: `ARCHITECTURE.md`
- Principle: DRY
- Severity: low
- Breaking + public surfaces: no; none
- Evidence: `ARCHITECTURE.md:351-363` lists ADR-0001, 0005, 0007, 0008, 0009, 0010, 0011, 0012 and 0016 as "Notable". It omits 0017 (Inbox Connector), 0019, 0020 and 0021, which are the multi-Platform decisions. It points readers at ADR-0001 ("replaces tenant_id") and ADR-0007, whose route shape and router name are superseded (10-02). `CONTEXT-MAP.md:123-127` already points at `docs/adr/` without a digest.
- Deletion test: replace the bullets with the one-line pointer and nothing is lost. The ADR filenames are already their titles. A hand-curated digest drifts every time an ADR lands.
- Proposed fix: cut the section to "Recorded decisions live in `docs/adr/`." Keep the trailing logging paragraph (`:365`) under a more fitting heading. Do not add a `docs/adr/README.md` index; that would be a third copy to keep in sync.
- ADR conflict: none

### 10-09 META_PRODUCTION.md is a stray personal Postman share link

- Files: `META_PRODUCTION.md`
- Principle: stale-doc
- Severity: low
- Breaking + public surfaces: no; none
- Evidence: the whole file is `1) Step 3 - https://candyfliprec.postman.co/workspace/My-Workspace~.../request/...?action=share&source=copy-link&creator=...`. `git ls-files` shows it is tracked. A grep of `.md`/`.py`/`.toml` finds no inbound links.
- Deletion test: delete it and nothing is lost; it also stops publishing a personal workspace link with the package repo.
- Proposed fix: `git rm META_PRODUCTION.md`.
- ADR conflict: none

## Rejected findings

- 10-03 ADR-0001 and ADR-0002 are historical bodies that name removed symbols. Rejected. Both already carry banners naming exactly those symbols and their replacements: `0001:3` names `InboxCredentialsService` -> Inbox Directory (ADR-0011), and `0002:3` names `IInboxCredentialStore` -> `IInboxCredentialResolver` + Inbox Directory. That is the correct ADR pattern for an append-only log. Merging 0001, 0011, 0020 and part of 0014 into a new "identity and directory" ADR rewrites history, invalidates every existing link, and adds no information that the banners and CONTEXT.md:204-210 do not already give.
- 10-04 ADR-0015 mixes three decisions and should split. Rejected. `0015:3` has a dated status note scoping exactly what ADR-0016 superseded, and the live parts (`InboxCredentialAccess`, extension-field registration) are accurately described as live. Splitting an accepted ADR into others is doc churn. The auditor's own deletion test concedes that the live part "must move", which is relocation, not removal of complexity.
- 10-08 Callback-authentication and Inbox Directory rules are restated in 4-5 docs. Rejected as unsupported. The evidence is a keyword grep with no file:line and no contradiction between copies. AGENTS.md deliberately layers a glossary term (CONTEXT.md), a mechanism (context ARCHITECTURE.md) and a caller surface (public-contract.md). A term appearing in each layer is the design, not duplication. Re-raise only with a concrete pair of copies that disagree.
- 10-11 META-CHANGELOGS.md misplaced at root with a confusing name. Rejected as cosmetic. It is linked from `CHANGELOG.md:547` and `:649`, is accurate, and its header names what it is. Moving it costs link edits and changes no reader's understanding.
- 10-12 ADR-0005 and ADR-0012 split; merge into one inbound ADR. Rejected. `0005:3-5` already scopes the supersession precisely: the Inbox-identity assumption is superseded and the verifier and registry remain accepted. Same reasoning as 10-03. The cluster mapping in the auditor's interface proposal can serve as reading guidance, not as a rewrite plan.

## Checked and legitimate

- `wappa/api/controllers/webhook_controller.py:52` builds `supported_platforms` from `PlatformType`. That is a vocabulary check in the HTTP adapter, and fine. The hard-coded adapter sets at `:116` and `:136-140` are code debt for the code-side audits; this area only flags that the doc misdescribes them (10-06).
- The checklist at `ARCHITECTURE.md:298-313` ("Adding a new platform") is accurate against the code. Every file it names exists, and it honestly labels the Platform branches. It is the target-state backlog for the code audits, not a doc defect.
- The supersession banners on ADR-0001, 0002, 0005 and 0015 follow the right pattern and are accurate.
- `CONTEXT.md:205-211` Anti-Language rows (`TenantBase`, `TenantCredentialsService`, `IInboxCredentialStore`, `auto` routing mode, `Owner`) are the right single home for forbidden legacy symbols. Only the `owner_id` clause in row 204 is wrong (10-01).
- Root `CONTEXT.md:106` and `:120-127` already define the connection and external-webhook vocabulary, so no new per-context glossaries are needed.
- ADR-0003, 0004, 0008 and 0013 (HTTP client lifecycle, shutdown drain, Redis boolean encoding, SSE hub) are Platform-neutral and name no removed symbols.
- The Instagram adapter table at `ARCHITECTURE.md:317-331` matches the files on disk, including `wappa/connections/whatsapp.py`.
- `docs/public-contract.md:60-62` correctly documents the capability mechanism (`messenger.capability(kind)` / `require_capability(kind)`) and `IMediaLibrary` as one upload-and-download seam on both Platforms.

## Interface proposal

Docs need no new structure. They need to tell the truth about the five interfaces and the capability extensions, and to name the two that are not settled yet. Keep the 21 ADRs as an append-only log. New decisions get new ADRs, and changed ones get one-line banners.

Here is where each of the user's five interfaces is documented today, and the gap:

1. PlatformWebhooks: `wappa/webhooks/ARCHITECTURE.md` plus ADR-0010 and ADR-0018. Gap: the callback controller's Platform branch (10-06). Once the code audits settle the shape, record it in one new ADR, "inbound adapter registration".
2. SendingMessages (`IMessenger`, one method per action): ADR-0016, `wappa/messaging/ARCHITECTURE.md` and `docs/public-contract.md`. No gap beyond the Messenger factory branch (10-06).
3. HandlingMedia: `IMediaLibrary` (`wappa/domain/interfaces/media_library.py:38-45`, two methods, two adapters) is already the one seam for upload and download, documented in `public-contract.md:62`. `IMediaHandler` (`wappa/domain/interfaces/media_interface.py:30`, 15 members, one adapter: `wappa/messaging/whatsapp/handlers/whatsapp_media_handler.py:25`) is a hypothetical seam behind the WhatsApp Media API routes. The code audit should decide whether it becomes an internal WhatsApp detail. Docs should name only `IMediaLibrary` as the Platform-neutral media interface.
4. ProfileReading: no CONTEXT.md term, no interface and no ADR. Before code, add a CONTEXT.md term (for example "User Profile Read": read a User's profile within an Inbox, returning `ReadResult`) and one ADR. That ADR decides whether it is a core `IMessenger` method (only if both Platforms support it reasonably, per ADR-0016) or a capability. Write no interface until a second Platform's API is checked against the first.
5. InboxConnection: `IInboxConnector` in ADR-0017, defined at `CONTEXT.md:106`, with two adapters (`wappa/connections/whatsapp.py`, `instagram.py`). Gap: it is missing from CONTEXT-MAP and from the deeper-docs table (10-05).

Platform-only capability extensions are already documented once, as the capability mechanism in `public-contract.md:60-62`: `ICommentControls` and `IConversationContentReader` (Instagram), and `ITemplateMessaging` (WhatsApp). Fix the ADR-0021 contradiction about Templates (10-13). Flows and Calls have no capability interface yet. Each one gets a capability class and a public-contract row when it ships, not a pre-built empty seam.
