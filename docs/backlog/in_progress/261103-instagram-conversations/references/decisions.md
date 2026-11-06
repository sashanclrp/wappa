# Instagram integration decisions

Date: 2026-11-03. Scope session complete; implementation is pending beyond the
verified text/seen/echo slice. The [PRD](scope.md) is the current selected scope.
The [implementation series](../plan.md)
tracks ownership, order and execution gates, including DDD and developer skills.
The [completed grilling session](../../../../sasha/grilling-sessions/261103-instagram-scope-and-extensions.md)
records the user's grouped answers and Symphonai investigation.

Related documents: [research](research.md), [roadmap](design-roadmap.md),
[setup](setup.md), [tests](../tests/simple-text-test.md),
[ADR-0025](../../../../adr/0025-messenger-contract.md),
[ADR-0025](../../../../adr/0025-messenger-contract.md).
Earlier research-stage TBD worksheets and public-reply alternatives are
superseded by the decisions below; research inventories are not implementation
status or permission to build every provider feature.

## Ownership

Wappa supplies reusable Platform operations and runtime contracts to the Host's
backend. The Host owns business policy and durable business state. This selects
both conversation transport and comment-control primitives without selecting a
moderation engine. Publishing, calendars, scheduled publication, content/account
analytics, conversation history, AI, and human assignment remain consumer-owned.
Operational message status/error diagnostics remain Wappa responsibilities.

## Agreed scope

| Domain | Selected decision |
| --- | --- |
| Connection | Formalize and harden existing Symphonai credential reuse with a narrow supported trusted-backend capability, qualified by Inbox Reference. |
| Persistence | Host persists Wappa-produced encrypted records, owns business attribution and commit; Wappa owns envelope format, encryption, directory resolution and invalidation. |
| Consent | Reusable Unified Login setup supports required conversation permissions and optional extension scopes/grants; distinguish feature readiness. |
| Incoming messages | Text, image/audio/video/supported files, shared content and story-related variants, validated independently. |
| Selections | Typed quick-reply evidence and standalone interactions; consumer-owned Conversational Flows. |
| Message lifecycle | Seen statuses, echoes, referrals, edits/deletions where available. Content changes are distinct from delivery statuses. |
| Private sends | Text, supported media, Quick Replies, Button Messages, Message Cards and Message Carousels, plus explicit seen/typing primitives. |
| Public conversations | All accessible regular/Live comments, replies and supplied placements; public mentions included without pretending media-only mentions are comments. |
| Public reply | Dedicated `reply_comment` on Messenger facade, returning comment evidence. |
| Private reply | `send_text(target=PrivateReply(comment_ref=...))`, initially Instagram-only and text-only; native eligibility applies. |
| Comment controls | Hide/unhide/delete comments and enable/disable comments on media. Consumer chooses whether/when to execute them. |
| Reads | Focused post/comment/child-media reads and supported media bytes/download/stream access, callable independently of dispatch. No network enrichment inside processors. |
| Platform Extensions | Wappa authenticates/admit/dispatches registered extension fields through the Instagram callback; extension owns schemas, handlers and extra provider operations. |
| Exclusions | Reaction behavior, cross-app handover, unselected events, publishing/analytics implementations, host workflow/history engines. |

Every message family needs a Platform × operation × target × options matrix.
Provider constraints and access permissions are not interchangeable with
implementation support. No silent substitute, no visibility inference, no
fabricated native identity or resource result, no blind uncertain-send retry.

## Event lanes and filtering

Keep `process_status` for delivery/read/failure evidence. Planned
`process_message_update` handles edits/deletions; `process_comment` handles
actual comments; `process_mention` handles public comment/media mentions;
`process_interaction` handles standalone postbacks. These are target contracts,
not methods already added by this session. A quick-reply message retains its
structured selection evidence without becoming a second automation trigger.

Comments expose typed source, available placement, Comment/Post References,
parent evidence and available author/content/time. Consumers filter or gate
processing themselves. Missing evidence remains absent; processors do not
invent top-level classification, a DM User or downloadable media bytes.

## Connection extension relationship

Symphonai already resolves a bearer through Wappa's internal resolver in
`services/wappa/runtime_inbox.py`, then builds its own Meta clients for extra
WhatsApp operations. Formalize this relationship, rather than forcing those
operations into IMessenger or a mandatory Wappa-managed HTTP client. Exact
public capability names and failure types remain engineering design work.

The current Symphonai Directory Source and runtime adapter exclude Instagram
or assume WhatsApp phone identity. They must migrate to qualified references.
Sharing `SYSTEM_TOKEN_ENC_KEY` does not make bare Fernet token ciphertext equal
to Wappa's context-bound envelopes. Hosts persist canonical records; Wappa
resolves/decrypts them; trusted extension adapters may receive current
credentials without independently decrypting or durably copying plaintext.
Host authorization applies before access. Extensions own extra client lifecycle.

Registered extension fields use the same signature-first, qualified and
all-or-nothing admission boundary. Parsers are pure; extension business work
runs after admission. Built-in field conflicts are rejected. Wappa supplies
subscription mechanics; the Host composes enabled core/extension requirements.
Analytics/publishing notifications do not become core conversation schemas.

## Callbacks and credential authorities

Keep separate `/webhook/inboxes/whatsapp` and
`/webhook/inboxes/instagram` callback URLs. Messenger is future work. Do not
introduce a shared `meta-messenger` Platform or `/meta` route. The supplied Meta
dashboard verified a separate Instagram setup; do not generalize that into a
claim about every possible provider configuration.

One Wappa application binds one Meta Application Configuration. Authenticate
POST exact bytes with the App Secret before parsing/lookup/scheduling. GET uses
the configured verification token only. Inbox authority stays exactly legacy
or explicit, with no automatic precedence/fallback; Instagram uses explicit.
No authorization, credential creation or registration from an incoming message.

## Targets, results and migration

All recipient-based IMessenger sends use explicit DirectMessage targets, with
no string alias or recipient keyword compatibility layer. PrivateReply extends
this contract only when implemented. Validate the bound Inbox before I/O;
private and public destinations remain explicit. Dedicated public replies
return comments rather than misleading DM message IDs.

Keep optional capabilities discoverable and reject unsupported operations
honestly. Preserve SRP, dependency injection and substitutability; capabilities
must honor their advertised contract. Interface segregation follows actual
responsibilities instead of forcing comment reads/controls into every Messenger.
Migration documentation and CHANGELOG must enumerate breaking sends, middleware,
models, handlers and consumer changes when they land. See the
[migration guide](../../../../migration/instagram-conversation-contracts.md).

## Vocabulary and human takeover

WhatsApp Template means the approved WhatsApp Platform feature. Instagram
provider wire terms map to Interactive Messages, Button Messages, Quick Replies,
Message Cards or Message Carousels. Conversational Flows are host-owned;
Application Scaffolds are generated code. Neither is an Instagram Template.

Use a single-app human escalation path. Wappa provides events, sends and runtime
infrastructure. Symphonai owns queue, assignment, UI and coordinated automation
pause/resume across immediate and delayed sends. Do not add a mandatory human
business model or `escalate_to_human` method to IMessenger. Cross-app handover
and HUMAN_AGENT policy permissions are distinct from consumer assignment.

## Delivery and remaining verification

A completes selected capabilities with tests per slice: text baseline, media
and interactions, host conversational example, all selected public conversation
sources/controls, then focused content reads. B tests full self-service Unified
Login. C tests Symphonai agent/context/isolation/takeover and extension reuse.

Scope is closed. Exact schema/export names, provider constraints, account/grant
requirements and subscription discrepancies are engineering verification items.
In particular `message_edit` is documented in examples/dashboard but missing
from the current Unified Login field table; verify before claiming support.
The [PRD](scope.md) carries acceptance criteria and evidence limitations.
