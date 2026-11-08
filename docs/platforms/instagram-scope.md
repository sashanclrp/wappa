# Instagram conversations and extensible account connection

The implementation series closed on 2026-11-08 with gates A, B and C passed ([live evidence](../verification/261103-instagram-conversations-live-tests.md)); its plan and PRDs are in git history. This file remains the detailed scope specification produced by grilling.

Status: scope agreed on 2026-11-03; implemented and verified live by 2026-11-08. This is the local PRD produced by the completed
[grilling session](../sasha/grilling-sessions/261103-instagram-scope-and-extensions.md).
It supersedes conflicting unselected/deferred rows in the earlier research
worksheet. Research describes provider capabilities; this document selects work.

## Problem and outcome

Consumers need to receive and answer Instagram private and public conversations
through Wappa, without building a second messaging runtime. Symphonai also needs
to reuse the account connection for its own publishing and analytics modules.
Those extra features must not turn Wappa into a content management, analytics,
or business workflow system.

Success has three delivery gates: A completes the selected conversation
capabilities with tests per slice; B verifies self-service Unified Login and
connection lifecycle; C verifies Symphonai agent integration, conversation
context, User/Inbox isolation, human takeover, and connection extension reuse.
Controlled credentials support A; manual customer token copying cannot satisfy B.

## Responsibility boundary

| Concern | Wappa package | Host Application / extension |
| --- | --- | --- |
| Platform access | OAuth/provider protocol primitives, account discovery, scope/subscription operations, canonical credentials, encryption, resolution, invalidation. | Backend routes/UI, authenticated operator and connection intent, durable persistence, Owner/Channel mapping, transaction coordination and readiness state. |
| Credential reuse | Supported, Inbox-qualified access to current credentials for trusted backend adapters; no need to import the internal resolver or decrypt records independently. | Extra provider clients, their lifecycle, endpoint models, publishing/analytics operations, authorization to invoke them. No second independently managed copy of the same connection token. |
| Webhook intake | Exact-body authentication, validation, qualified routing, batch admission, normalization, dispatch, extension registration and bounded operational outcomes. | Choose which events trigger work; extension-owned parsers/handlers for extra fields. |
| Private/public messaging | Selected sends, comment replies, private replies, provider constraints, errors, and honest results. | Response content, AI execution, business rules, durable message history and conversation state. |
| Comment controls | Hide/unhide, delete, enable/disable comments using provider APIs where authorized. | Whether to moderate, operator permissions/confirmation, policy, audit and workflow. No moderation engine in Wappa. |
| Content and media reads | Explicit post/comment/media reads and supported download/stream/bytes capabilities, isolated credentials and honest availability errors. | Choose enrichment, run AI/transcription, maintain a content library or durable snapshots. |
| Human takeover and flows | Typed events, sending, runtime context/cache infrastructure and consumer examples. | Assignment, human inbox/UI, state transitions, form questions, branching, takeover gates and delayed-job coordination. |
| Publishing and analytics | Reusable connection and extension intake infrastructure only. | Posts/Reels/Stories publication, calendars, scheduling, insights, reporting and attribution. |

The key distinction is Platform mechanism versus application policy. A callable
hide-comment operation belongs to the adapter; a rule that decides which
comments to hide belongs to the consumer. Message delivery statuses, errors,
and runtime diagnostics remain Wappa responsibilities despite the exclusion of
content/account analytics.

## Selected webhook inventory

Provider field names are native inputs, not new Platform identities. Retain
separate WhatsApp and Instagram callback URLs. Subscription availability is
verified for the chosen Unified Login setup; API examples alone do not prove
a field can be subscribed or delivered in that setup.

| Native field / variant | Selection and normalized behavior | Evidence / limitation |
| --- | --- | --- |
| `messages`: plain text | Implement; existing live baseline -> `process_message`. | Text already verified in [test record](../verification/261103-instagram-simple-text-test.md). |
| `messages`: images, audio, video, supported files, shared posts, story replies/mentions and other selected supported attachments | Implement inbound families separately from sends; preserve native references and available content -> `process_message`. | [Messaging guide](https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/messaging-api/) is a starting inventory; verify each family with Unified Login fixtures and live tests. |
| Quick-reply selection inside a message | Implement structured selection evidence on the inbound message; no loss of text or action payload. | One native event must not produce two automation triggers. |
| `messaging_postbacks` | Implement typed interaction dispatch; proposed `process_interaction`. | A standalone postback is not fabricated User text. |
| `messaging_seen` | Implement -> `process_status`; preserve native message/recipient evidence. | Existing READ path observed live. |
| `messages` with outbound/self echo | Implement -> `process_system_webhook`; never a new User message. | Existing MESSAGE_ECHO path observed live. |
| `message_edit` | Selected -> proposed `process_message_update`, kind `edited`, message reference, replacement content and available revision evidence. | Appears in dashboard and [examples](https://developers.facebook.com/documentation/instagram-platform/webhooks/examples), but is absent from the current Unified Login field/permission table; verify actual subscription/access before promising support. |
| `messages` with `is_deleted` | Implement -> proposed `process_message_update`, kind `deleted`; no invented deleted content. | [Examples](https://developers.facebook.com/documentation/instagram-platform/webhooks/examples) document the deletion variant. |
| `messaging_referral` and referral evidence in messages | Implement typed entry context; preserve whether standalone or attached. | Attached context does not create a duplicate inbound message. Standalone context uses a system event with typed detail. |
| `comments` | Implement accessible post/Reel comments, replies, and all supplied supported placement variants -> `process_comment`. | [Comment guide](https://developers.facebook.com/documentation/instagram-platform/comment-moderation) and examples; availability does not imply access to every ad or private post. |
| `live_comments` | Implement -> `process_comment`, distinguish Live source. | Verify Live-specific references, bursts, and reply eligibility separately. |
| `mentions` of account in a comment or media caption | Implement public mention intake. Comment mention -> typed mention with Comment Reference when supplied; media-caption mention must not fabricate a comment. Proposed `process_mention` handles both mention subjects. | [Examples](https://developers.facebook.com/documentation/instagram-platform/webhooks/examples) distinguish media-only versus comment mentions. Story mentions delivered as DMs remain message events. |
| `message_reactions` | Exclude behavior and default subscription. | Authenticated incidental notifications receive an explicit ignored/unsupported outcome, never an automated reply. |
| `messaging_handover`, `standby`, cross-app control | Exclude behavior and default subscription. | Single-app host takeover is separate. |
| `story_insights` and extra publishing/analytics fields | Extension-owned schemas and behavior; implement reusable authenticated intake registration. | Do not enable by default. Registration cannot create a provider field that does not exist or grant missing permissions. |
| Other fields such as opt-ins, feedback or policy-specific notifications | Not selected unless required for connection correctness or independently registered by an extension. | “Other events” is not blanket approval; make subscription and ignored-event behavior explicit. |

Current [Meta field/permission documentation](https://developers.facebook.com/documentation/instagram-platform/webhooks/fields)
lists Unified Login `comments`, `live_comments`, `mentions`, `messages`,
`messaging_postbacks`, `messaging_referral`, `messaging_seen`, reactions, and
Story insights. Only selected conversation fields enter the default subscription.
Public comment updates/deletions are normalized only when actual provider
notifications expose them; a moderation API operation does not prove that a
matching webhook exists.

## Handler and event contract

These are target contracts, not methods already implemented today:

| Hook | Responsibility |
| --- | --- |
| `process_message(InboundMessageWebhook)` | New User messages, including quick-reply messages with structured selection evidence. |
| `process_interaction(InteractionWebhook)` | Standalone action/postback events. |
| `process_message_update(MessageUpdateWebhook)` | Edits/deletions of an existing message; discriminated update kinds. |
| `process_status(StatusWebhook)` | Delivery/read/failure evidence; never text edits or deletions. |
| `process_comment(IncomingCommentWebhook)` | Actual public comments/replies, including Live and accessible placement variants. |
| `process_mention(MentionWebhook)` | Public account mention evidence with explicit comment/media subject. |
| `process_system_webhook(SystemWebhook)` | Echoes, standalone referral context and other supported runtime/control facts. |
| Extension-registered handler | Authenticated extension fields without forcing their domain into conversation schemas. |

Comment events expose orthogonal typed dimensions: source (`comments` versus
`live_comments`), available media placement/type, event kind, Comment/Post
References, optional parent Comment Reference, author evidence and available
text/time. Preserve `unknown`/absence when Meta omits a fact; missing parent
evidence is not proof of a top-level comment. A comment reference is not its
content. A public author ID does not automatically authorize ordinary DM sending.

Consumers filter typed events in their handler or injected policy. The default
runtime must not silently discard Live, self-authored, or other selected comment
types according to Wappa-invented business policy. It must avoid automatic echo
loops and offer enough evidence for the consumer to recognize its own actions.
No required host policy interface or global comment business gate is introduced.

## Selected outbound and read capabilities

| Capability | Destination / contract | Scope |
| --- | --- | --- |
| Text | `send_text(target=DirectMessage(...))` | Ordinary private delivery. |
| Image/audio/video/supported file | Corresponding Messenger operation with DirectMessage. | Verify MIME, size, source, caption and reply options per operation; no assumption of WhatsApp parity. |
| Quick Replies, Button Messages, Message Cards, Message Carousels | Messenger facade with typed interactive content and DirectMessage. | Preserve native action semantics and normalized inbound selections. No “Instagram Templates” domain. |
| Seen and typing actions | Explicit optional capability with native recipient/message constraints. | Do not overload text sends or imply delivery status. |
| Public comment reply | `reply_comment(comment_ref=..., text=...)` on Messenger facade. | Result identifies a comment, never a fabricated DM Message ID. |
| Comment-triggered private reply | `send_text(target=PrivateReply(comment_ref=...))`. | Strict Instagram-only target initially; text first. No inferred destination or arbitrary media/private-reply combinations. |
| Hide/unhide and delete comment | Dedicated comment-control operations. | Validate qualified references, permissions/provider restrictions and operation support; policy remains host-owned. |
| Enable/disable comments on media | Dedicated comment-control operation on a Post Reference. | Affects the selected media; not a setting on one comment. |
| Post/comment reads and child media/replies | Focused read capability separate from pure processors. | Available caption, permalink, types, comments, media references and children with pagination where applicable. No historical conversation sync or content-calendar ingestion. |
| Media download/stream/bytes | Explicit media capability that consumers may feed into AI. | Do not attach Meta credentials to arbitrary attachment URLs. Account for missing/deleted/inaccessible media, expired URLs, MIME/size limits and supported refresh paths. |

The [comment API](https://developers.facebook.com/documentation/instagram-platform/comment-moderation)
documents public replies, hide/unhide, deletion and comment enable/disable
controls on authorized media. Native endpoint translation belongs behind focused
adapters; keeping public replies on Messenger does not require putting all
read/control operations in IMessenger.

Private replies must validate supported eligibility and expose provider refusal,
expiry and uncertain-send results honestly. See [Meta Private Replies](https://developers.facebook.com/documentation/instagram-platform/private-replies).
For every operation validate Platform × operation × target × content/options.
Wrong-Inbox references fail before I/O. Unsupported combinations fail explicitly;
never silently change message family or public/private visibility.

## Connection and extension contract

Formalize Symphonai's existing trusted-backend credential reuse, rather than
requiring Wappa to own clients for publishing and analytics. Introduce a narrow
supported capability to resolve the current active Inbox's credential and
version using `InboxRef`; exact public names are implementation design details.
The Host authorizes the caller. Possessing an Inbox ID does not grant access.
Do not promote the entire internal resolver/directory API into the public seam.

Wappa retains envelope creation, encryption/context binding, directory resolution
and invalidation. Hosts persist records returned by Wappa and coordinate commit
then refresh. Extensions receive credentials only inside trusted server-side
adapters, never browser responses, AI arguments, logs or durable plaintext.
Extensions own their clients and their closure; they resolve current credentials
per operation, not a permanent token snapshot. Define failure semantics for
inactive/unknown credentials and unavailable resolution. Already started calls
are not retroactively canceled by directory eviction.

Optional extension permissions/account grants are supplied through reusable
connection setup. Required conversation readiness is distinct from optional
feature readiness. Preserve cancellation, missing permission, partial setup,
reconnect, permission removal and revocation as explicit outcomes. One shared
key is not proof that ciphertext formats or provider grants are interchangeable.
Bind OAuth completion to the initiating authenticated connection intent, validate
state and redirect configuration, and prevent reuse of one-use codes/handoffs.
Test concurrent connection attempts and cross-account completion. The Host
owns the operator session and durable intent; Wappa's provider helpers must not
select an Owner from an untrusted callback or log returned credentials.

The Instagram callback admits extension events through the same signature-first
and qualified admission boundary. Register field parsing/handling with explicit
ownership, conflict detection, isolation, and safe error behavior. Reject
collisions with built-in fields; no generic raw-payload broadcast. Parsers are
pure and bounded; dispatchers run work with the admitted context. Define mixed
batch behavior so parsing/admission failure cannot partially schedule deliveries.
The extension never bypasses Meta authentication or establishes an Inbox from
untrusted payload data. Wappa owns subscription mechanics; the Host composes
the requested field set from core capabilities and enabled extensions.

## Architecture and invariants

- Strategy/Adapter owns Platform differences. Factory/Builder assembles
  dependencies. Shared event consumers operate on typed universal facts.
- Respect SRP: processors translate, routing resolves admission, capabilities
  perform provider I/O, handlers execute consumer policy. Inject dependencies.
- Respect substitutability through explicit operation/target capabilities,
  honest results and documented unsupported-operation behavior; no dummy
  implementations or promised operation that silently does nothing.
- Share selection and identity value objects without pretending all Platforms
  support identical methods, content or eligibility. Optional capabilities
  remain discoverable and are segregated when responsibilities justify it.
- All cross-Platform identity uses Inbox Reference. Public comments and media
  may lack User context; never fabricate a DM User to satisfy dispatch/cache.
- Keep admission signature-first, batched and scoped. Preserve existing WA
  credential authority and callback behavior.
- Expose accepted/rejected/indeterminate provider outcomes and resource kinds.
  Acceptance is not delivery; never blindly retry uncertain sends or destructive
  comment mutations. Durable business idempotency remains consumer-owned.

## Delivery and validation

| Gate / slice | Acceptance evidence |
| --- | --- |
| A0 — contract foundations | Supported credential extension seam, qualified references, typed events and results, operation/target matrix; WA regression coverage. |
| A1 — text | Retain verified echo/seen/echo-system baseline; add pending concurrent/stateful and multi-Inbox isolation checks. |
| A2 — media and interactive messaging | Test each supported incoming/outgoing family independently; bytes retrieval, inaccessible media, source isolation, native selections and unsupported combinations. Images remain the next message slice. |
| A3 — conversational example | Host-owned intake branches, validates, resumes/cancels and handles repeated/stale actions without User/Inbox state crossing. |
| A4 — public conversations | Regular/Live comments, replies and mentions distinguishable; public/private replies, comment controls and host filtering; unknown/missing metadata, burst load, own actions and private-reply eligibility covered. |
| A5 — content reads | Authorized post/comment/children retrieval and bytes path where exposed; expired/inaccessible/deleted resources and pagination tested; processor performs no network I/O. |
| B — Unified Login | Business/Creator audience verified; account discovery, encrypted durable persistence, subscriptions, readiness, optional permission denial, cancellation, partial failure, reconnect and revocation; independent-customer access requirements verified. No manual ID/token copying. |
| C — Symphonai | Real agent replies/context; concurrent User/Inbox isolation; human takeover across delayed sends; existing credential adapter/source migrated for Instagram; an extension obtains supported authenticated access without a second token store. Publishing/analytics implementations remain outside this PRD. |

Every slice requires offline boundary/contract tests and controlled live checks.
Tests must cover invalid signatures before resolution, unknown/inactive Inboxes,
mixed-account batches, malformed events and supported extension routing.
Record evidence under this draft's `tests/` directory; distinguish intended,
implemented, offline-verified and live-verified support. A hello exchange is not
proof of all message types, public events or OAuth readiness.

## Migration and release requirements

The recipient-to-target migration is intentionally breaking across Messenger
implementations, caller code, middleware, serialized events, examples and mocks.
Document each affected operation and before/after examples, including
`DirectMessage` and the future Instagram-only `PrivateReply`. No string alias or
compatibility fallback. Independent WhatsApp HTTP/Template inputs retain their
documented adapter contracts unless deliberately changed.

New update/comment/interaction/mention hooks, result/resource kinds, extension
registration and credential access must be documented with public imports,
defaults, capability discovery, migration steps and safe handling of absent
evidence. Update canonical docs and CHANGELOG when each contract is implemented;
never list planned methods as shipped. No version bump or release is part of
this scope-definition task.

## Remaining engineering verification

Product scope is closed. Endpoint/source limits, exact public names, hook schema
fields, grant reuse and subscription permissions still require technical design
and provider verification during each slice. In particular resolve the
`message_edit` Unified Login documentation discrepancy with fixtures/live access;
report unsupported provider behavior rather than adding a login fallback or
claiming completed support. These checks do not reopen publishing/analytics as
Wappa product domains.
