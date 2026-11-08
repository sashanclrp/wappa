# Instagram scope and connection extensions

Date: 2026-11-03. Status: completed scope session. Product decisions are recorded in the [Instagram PRD](../../platforms/instagram-scope.md); planned contracts are not claims of shipped support.

Implementation handoff: the Instagram PRD series (closed 2026-11-08, in git history),
including DDD improvements and developer skill/setup deliverables. The session's
final answers remain the source decisions; the series owns execution status.

## Purpose and evidence

Produce an improved Instagram PRD with an explicit webhook inventory, outbound
operation inventory, conversation-content boundary, connection extension
contract, and testable acceptance criteria. Resolve dependencies one question at
a time; record the answer before advancing. Do not start another implementation
slice while its scope is being reconsidered here.

Read alongside the [glossary](../../../CONTEXT.md),
[architecture](../../../ARCHITECTURE.md),
[public contract](../../public-contract.md),
[ADR-0022](../../adr/0022-inbox-identity-and-directory.md), and
[ADR-0025](../../adr/0025-messenger-contract.md).
The original draft separates [research](../../platforms/instagram-research.md),
[decisions](../../platforms/instagram-decisions.md),
[roadmap](../../platforms/instagram-design-roadmap.md),
[setup](../../platforms/instagram-setup.md), and
[observed tests](../../verification/261103-instagram-simple-text-test.md).
Provider claims and exact permission/endpoint requirements must be verified
against primary documentation when each inventory row is finalized.

## Confirmed direction from the user

- Wappa owns conversations: private messages, incoming public comments, public
  comment replies, and comment-triggered private replies.
- Publishing posts, Reels, or Stories, managing a content calendar, scheduling
  publication, and retrieving post/account performance analytics are outside
  Wappa's feature scope. These can belong to Symphonai or a separate package.
- That extension must be able to reuse the Instagram connection and future
  Unified Login infrastructure associated with the same Meta app/use case.
  A separate feature package must not imply a separate customer connection.
- Reactions remain excluded from the selected Instagram implementation.
- Preserve the agreed delivery stages: selected Instagram capabilities and
  per-capability tests; full self-service Unified Login tests; Symphonai agent,
  conversation context, isolation, and human takeover tests.
- Conversational Flows belong to consumers. Wappa supplies message/interaction
  transport and examples; WhatsApp Templates remain a distinct Platform feature.

The exclusion of analytics concerns a product feature for measuring content or
account performance. It does not remove message statuses, send outcomes, errors,
or operational diagnostics needed to run conversations.

## Current implementation, verified against code

The initial Instagram adapter supports plain text intake/send, READ status from
seen events, and outbound echoes as system events. Unknown supported-envelope
messaging variants become unsupported system events; this is not general
support for every Instagram webhook envelope. Live text and sequential
two-User routing have been observed; concurrency and multiple Inboxes have not
been established by those live tests.

`IInboxDirectorySource` is the Host's read-only persistence adaptation point.
Wappa owns encrypted credential records, directory resolution, and credential
lifecycle. `IInboxCredentialResolver` is internal;
`ResolvedInboxCredentials` explicitly says it never leaves Wappa. Existing
outbound capabilities do not give an external content/analytics package an
authenticated Instagram access contract. Self-service OAuth remains unbuilt.

Follow-up inspection of Symphonai corrects the initial framing: extension reuse
already exists for WhatsApp through an internal Wappa resolver dependency.
Instagram support and a stable supported extension contract remain to design;
we should evaluate the existing pattern before adding another transport layer.

## Symphonai investigation — 2026-11-03

Inspected the local Symphonai checkout, not deployment secrets or live grants.
Paths below are relative to its `backend/` directory.

| Finding | Source evidence |
| --- | --- |
| Symphonai's own Fernet helpers read `wappa_settings.token_enc_key`, configured through `SYSTEM_TOKEN_ENC_KEY`. | `symphonai/core/crypto.py`, `_build_fernet`, `encrypt_token`, `decrypt_token`. |
| Channel token persistence delegates encryption/versioning to Wappa, then stores the returned context-bound envelope verbatim. | `symphonai/domains/admin/services/channel_onboarding_service.py`, `persist_channel_credential`; `channel_credential_service/`. |
| The directory source maps durable Channel rows into canonical Wappa records without decrypting them. It currently filters WhatsApp in SQL and rejects other Platforms. | `symphonai/services/wappa/inbox_directory_source.py`, `_CHANNEL_RECORD_COLUMNS`, `get_inbox`. |
| Symphonai already obtains plaintext bearer values from Wappa's resolver for its own provider operations. | `symphonai/services/wappa/runtime_inbox.py`, `get_runtime_credential_resolver`, `resolve_template_send_runtime_inbox`, and `credentials.access_token.get_secret_value()`. |
| Symphonai then constructs and closes its own Meta clients outside IMessenger. | `symphonai/services/wappa/template_catalog/orchestrator.py`, `build_meta_template_api_service` and resumable upload builders; `symphonai/services/wappa/meta_chat_block.py`. |
| This is intentional, documented, and covered by existing source tests. | `symphonai/services/wappa/ARCHITECTURE.md`, Runtime Inbox and Credentials; `tests/services/test_wappa_runtime_inbox.py`, bearer-return and unavailable/invalid cases. These tests were read, not executed during this investigation. |
| The same key does not make a Wappa envelope equivalent to Symphonai's bare-token ciphertext. | `tests/domains/admin/test_channel_onboarding_service.py` explicitly checks that decrypting the envelope ciphertext with Symphonai's helper does not return the bare provider token. |

The actual existing extension path is:

```text
Symphonai durable Channel credential (Wappa encrypted envelope)
  -> SymphonaiInboxDirectorySource
  -> Wappa Inbox Directory resolves/decrypts the active credential
  -> Symphonai runtime_inbox adapter extracts the bearer
  -> Symphonai-owned Meta API client performs the extra operation
```

This contradicts Wappa's absolute statement that resolved credentials never
leave Wappa: they do cross into Symphonai's trusted External Service adapters.
It does not mean Symphonai independently decrypts Channel envelopes, or that
the internal resolver is already a supported general extension API. Keep
documented contract and observed consumer behavior distinct until resolved.

Instagram is not wired into this consumer path yet: `WappaRuntimeInbox` carries
`phone_number_id`, its reference is constructed with `InboxRef.whatsapp`, and
the source excludes Instagram. Generalization must use qualified Platform
identity, preserve current-credential resolution, and keep provider operations
in their owning package. Sharing an encryption key alone proves neither a
provider permission grant nor Instagram integration readiness.

## Final answers and ownership decisions

The user answered the grouped inventory and requested closure. These answers
supersede earlier recommendations to defer Live/comments and exclude comment
controls. “Everything” in P1 means all accessible comment sources and public
mention subjects, not every Instagram API capability.

| ID | User decision | Resulting requirement |
| --- | --- | --- |
| C1 | Agree; formalize and harden existing Symphonai dependency. | Supported current-credential access for trusted backend extension adapters; do not require an extra Wappa HTTP client layer. |
| C2 | Agree; Wappa is a package used by Symphonai's backend. | Host owns persistence/business relations; Wappa supplies reusable protocol/runtime/credential functionality. |
| C3 | Agree. | Optional extension permissions supported independently of required conversation readiness. |
| W1 | Agree. | Incoming text/media/shared-content/story message families, verified individually. |
| W2 | Agree; SRP, Liskov substitution and dependency injection required. | Typed selection/action contracts, explicit capabilities and honest unsupported operations; no business workflow engine. |
| W3 | Agree; asked where edits/deletions go. | Distinct message-update lane, not delivery status. Target design is `process_message_update` with edited/deleted kinds. |
| W4 | Agree; exclude reactions, cross-app handover and other unselected fields. | No default subscription/behavior for those fields; safe incidental-event outcomes. Referrals selected. |
| S1 | Agree. | Supported media and interactive send families; native limitations and inbound/outbound matrices remain explicit. |
| S2 | Agree. | Seen/typing primitives included. |
| S3 | Agree. | No silent content/visibility substitution. |
| P1 | Expand now, with typed filtering. | Regular/Live comments, replies and accessible placements included. Consumers decide which to act on; media-caption mentions remain distinct from actual comments. |
| P2 | Agree. | Dedicated `reply_comment` on Messenger facade. |
| P3 | Agree; thoroughly document breaking change. | Instagram-only PrivateReply text target; recipient-to-target migration and new contract details in migration docs/CHANGELOG when implemented. |
| P4 | Include methods, exclude consumer policy. | Wappa provides hide/unhide/delete and enable/disable commenting primitives; consumer owns moderation rules, tooling and authority. |
| R1 | Agree; include media bytes for AI use. | Explicit post/comment reads and supported media download/stream/bytes access; consumer owns AI and enrichment timing. Not every reference exposes accessible bytes. |
| R2 | Host manages conversations. | No Wappa conversation-history synchronization/store; profile reader remains deferred. |
| X1 | Agree. | Publishing, calendars, scheduling and content/account analytics belong to extensions/Host. |
| X2 | Wappa processes the callback. | Same authenticated Instagram callback admits registered extension fields; extension owns parser/handler schemas and application behavior. |

## Connection reuse: required scenario

1. A professional account connects for conversations through the Host's
   Wappa-backed Unified Login flow.
2. Symphonai enables a separately owned publishing or analytics module for that
   account, under the same Meta app/use case.
3. The module reuses account identity and connection lifecycle, without reading
   Wappa's private directory implementation or manually copying a token.
4. Additional permissions or account grants, if required, are obtained through
   an explicit authorization extension. Same app and same account do not prove
   that the original grant authorizes every future feature.
5. Reconnect and credential changes do not leave the module using an obsolete
   copied token. Revocation prevents subsequent work after the lifecycle update
   is applied; treatment of already in-flight calls must be specified.

Whether one authorization/token can serve all selected operations is a provider
verification item, not an assumption. Subscription ownership, partial consent,
permission removal, and publishing-only extension notifications need explicit
contracts. Extension field registration through Wappa intake is now selected; exact API names and lifecycle semantics are implementation design work.

## Handler clarification and closure

`StatusWebhook` and `process_status` currently describe sent/delivered/read/failed
message delivery. Code inspection confirms that edit/deletion are not existing
status variants. The planned `process_message_update(MessageUpdateWebhook)`
keeps content changes separate and avoids misclassifying an edit as a new User
message. This is the technical resolution to W3, not an implemented method.

The target `process_comment` receives typed actual comments with distinct source,
placement, parent/thread and available author evidence. Media-only public mention
notifications carry no comment, so the target `process_mention` handles typed
public mentions without fake comments. Quick replies retain structured evidence
inside incoming messages; standalone postbacks use the target
`process_interaction` hook. The PRD distinguishes these target contracts from
current handler methods.

“Wappa processes extension webhooks” means Wappa authenticates and admits them,
then dispatches to the extension-owned registered parser/handler contract. It
does not mean Wappa implements analytics or publishing workflows. There is no
need for a second Instagram callback in this design; no claim is made that Meta
forbids every alternative callback topology.

The final ownership principle is: Wappa provides Platform mechanisms and
integration contracts; consumers own application policy and durable business
state. Content reads and moderation controls fit the mechanism side. Content
calendars, moderation rules, AI and analytics fit the consumer side.

Product scope is complete. The [PRD](../../platforms/instagram-scope.md)
is the current selection; [ADR-0025](../../adr/0025-messenger-contract.md)
records the boundary trade-off. Implementation must resolve endpoint-specific
limits, exact exported types and subscription discrepancies without treating
those technical checks as completed provider support. No new implementation or
release was performed as part of closing this session.
