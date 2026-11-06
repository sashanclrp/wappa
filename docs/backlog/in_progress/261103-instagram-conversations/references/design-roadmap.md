# Instagram integration roadmap

The executable [PRD series](../plan.md)
now owns work order and completion status. This document preserves the capability
sequence and milestone rationale from the design session.

Current selection: [agreed PRD](scope.md). Test record: [simple text tests and learnings](../tests/simple-text-test.md).


Implementation update (2026-11-03): initial Instagram text/seen/echo-system lanes,
explicit Instagram credential records, DirectMessage sends, and the sibling echo
example are implemented locally. CLI GET verification and signed offline echo
have been tested. A real Instagram text exchange, outbound echo event, and READ
status were verified at 11:24 America/Bogota on 2026-11-03. Self-service OAuth
onboarding and Symphonai integration remain pending.
See [setup.md](setup.md#local-implementation-ready-for-callback-verification) and
[ADR-0025](../../../../adr/0025-messenger-contract.md).
Capability inventories below retain the research-stage snapshot; they are not
an assertion that every originally missing foundation remains unimplemented.

Date: 2026-11-03. Delivery order A → B → C is agreed; slice implementation details remain technical design work. No delivery dates are assigned.

Setup walkthrough: [setup.md](setup.md), documenting Unified Login dashboard configuration and pending verification.

Related documents: [research and capability inventory](research.md), [decisions and editable scope](decisions.md). Scope rows marked TBD remain unselected; their appearance in a later stage does not approve them. The initial live text slice is verified. Sequential two-User routing has also been observed live; concurrent/stateful multi-User and multi-Inbox validation plus milestones B/C remain pending.

## Success milestones

Current agreed order: A completes the selected Instagram capability scope, B validates the complete self-service Unified Login experience, and C validates Symphonai agent integration. Controlled account setup can support A; B must remove manual customer token/account copying. Tests accompany every A capability, then exercise the real onboarding and Symphonai paths in B/C. This supersedes the earlier option to demonstrate B/C immediately after text.

### A. Agreed Instagram capability implementation

Complete the selected message-type, conversational-flow example, comment, and
post-retrieval capabilities in the sequence below. “Full Instagram” means this
agreed scope, not every provider API or dashboard subscription. Reactions,
cross-app handover, publishing, content/account insights, and other unselected rows
do not become approved merely through this phrase. Consumer-owned flow logic
remains outside the Wappa runtime. Each slice requires its own offline and live
validation; a successful text echo does not certify the later features.

#### A1. Text echo checkpoint

Status: the first real User-to-Inbox text echo has been verified end to end.
Server logs show inbound Instagram translation/dispatch, HTTP 200 for the native
text send, an outbound MESSAGE_ECHO system event, and a READ status. The local
encrypted active Inbox record was also inspected. This completes the current
basic-text implementation goal; the additional live multi-User/multi-Inbox
checks below remain validation work for the text checkpoint; the remaining capability phases are not yet implemented.

Build a small Wappa consumer that receives an Instagram text DM and echoes its text back to the sender using the universal handler and shared outbound contract.

Acceptance criteria:

- A real person sends text to a connected professional account and receives the same text back.
- Multiple people can message the account without responses or state crossing between Users. Repeat across multiple registered Inboxes to verify account isolation.
- Signed callbacks, Inbox-bound credentials, native sender identity, and the complete inbound/outbound path work together.
- Outbound echoes do not start reply loops; callback redelivery has deliberate handling.
- Existing WhatsApp behavior survives the shared-contract migration.

### B. Self-service professional-account connection

Build a consumer application in which a business or creator selects Connect Instagram, completes the chosen Meta login/consent flow, and returns with a usable connection. Manual per-customer developer-dashboard wiring or token copying does not satisfy this milestone. One-time developer setup of the Meta app remains separate from customer onboarding.

Acceptance criteria:

- Business and Creator account connection paths are verified; any selected-flow prerequisites are completed by the integration.
- Account identity, permissions, encrypted credentials, durable host persistence, Directory refresh, subscriptions, and connection readiness are handled end to end.
- After connecting, the account can run milestone A without manual intervention.
- Cancellation, denied/missing permissions, partial setup failure, reconnect, and credential revocation have explicit behavior.
- Verify the selected flow's access/review requirements and demonstrate onboarding for the intended customer audience. An app-role-only demonstration is insufficient if the audience includes independent customers.

### C. Instagram AI agent through Symphonai

Connect a Symphonai AI agent to an account onboarded through B. Wappa supplies Platform transport and integration entry points; Symphonai owns agent execution, conversation state, business policy, and human takeover.

Acceptance criteria:

- A real Instagram DM reaches the configured Symphonai agent; its generated response reaches the correct User through the correct Inbox.
- Consecutive turns preserve conversation context and isolate different Users and Inboxes.
- Symphonai's human takeover pauses automated responses, including delayed jobs; a human can reply and explicitly resume automation under host policy.
- Provider failures and uncertain send outcomes remain visible without creating reply loops or blind duplicate sends.

The text slice is verified. Complete the remaining agreed capability sequence in A before the full B onboarding and C Symphonai integration tests. No reaction implementation is added to the scope.

## Agreed capability sequence

1. Text DMs first.
2. Expand to supported message types: media and interactive/shared-content variants. Enumerate inbound and outbound support separately; preserve the explicit reaction exclusion and do not assume WhatsApp-only types exist on Instagram.
3. Interactive conversational scores/intake: demonstrate a consumer-owned multi-step flow driven by buttons/quick replies and text answers, using normalized selection payloads and Inbox/User-scoped state. Validate answers, branch, resume, cancel, and complete an intake without cross-User state leakage. A successful button send alone does not satisfy this phase. Native Instagram forms equivalent to WhatsApp Flows are not assumed; web-form intake is a separate integration if selected.
4. Instagram public conversations: regular and Live comment events, replies and public mentions, public replies, comment-triggered private replies, and comment-control API primitives. Consumers own filtering and moderation policy.
5. Post retrieval: explicitly fetch accessible post metadata/content from a Post Reference to enrich conversation context. Handle unavailable content; never hide network reads inside the webhook processor.

This capability sequence is now stage A. Full self-service Unified Login testing follows in stage B; Symphonai integration testing follows in stage C. Continue using controlled account credentials while building and testing A.

The completed scope session additionally selects edit/deletion events, seen/typing primitives, trusted credential reuse and extension field intake. History synchronization is consumer-owned; profile reads and conversation entry configuration remain deferred. Publishing/insights and moderation policy belong to consumers or extensions; comment-control API primitives belong to Wappa. Echo handling, credential lifecycle, and send failure handling are operational foundations to address during the first phase, not optional final add-ons. Cross-app handover remains excluded initially.

## Proposed technical work and milestone mapping

The [PRD](scope.md) is the current scope authority and adds a contract-foundation slice for trusted credential access, extension registration and event/result models. Steps 0-3 below describe the original A1 construction history. Step 2 is infrastructure shared by A and B, not proof that B is complete. Step 4 provides operational checks throughout A. Steps 5-8 complete the remaining agreed capability sequence; individual variants still need explicit scope selection. After A, B adds login UI/callback orchestration and the onboarding acceptance checks above. C then adds the real Symphonai agent and host takeover integration.

| Step | Deliverable | Evidence required before advancing |
| --- | --- | --- |
| 0 | Select one login flow and obtain sanitized real fixtures from a controlled test account. | Actual permissions, account identity, webhook subscription, Creator requirements, and human escalation route checked. |
| 1 | Native identity, typed targets, shared results/capabilities, and clean WA migration. | Existing WA behavior retained; cross-Inbox targets rejected; caches/SSE/events/templates migrate together. |
| 2 | Instagram credential variant and connection/bootstrap adapter through the existing Directory. | Encryption/source/refresh/revocation tests; subscription failure/retry; no webhook auto-enrollment. |
| 3 | Complete incoming text -> universal handler -> send_text hello slice. | Signed real callback, pure processor fixtures, mocked outgoing HTTP, correct account/IGSID routing, and real controlled hello exchange. |
| 4 | Operational conversation behavior, validated throughout stage A. | Echoes do not retrigger automation; duplicate callbacks have explicit host/runtime handling; token failures and ambiguous send outcomes preserved. Host takeover is validated in C. |
| 5 | Expand supported message types: selected media, interactive, and shared-content variants. | Separate inbound/outbound capability coverage and controlled live examples; reaction implementation remains excluded initially. |
| 6 | Consumer-owned interactive score/intake example. | Selection payload drives the next step; validated text answers, branching, resume/cancel, stale/repeated selections, and concurrent User isolation tested. |
| 7 | Regular/Live comments, replies, public mentions, comment controls, public replies and text PrivateReply. | Typed sources and filtering, qualified references, controls, burst handling, eligibility/expiry errors, public versus private results and follow-up DM tested. |
| 8 | Separate post reader. | Available caption/media/permalink/child content translated honestly; permissions and unavailable content handled; processor remains pure. |

Testing starts at step 0 and accompanies every step. Unit/HTTP tests stay offline using sanitized fixtures; explicit controlled live checks verify provider behavior and access restrictions. Never infer that a successful hello proves every media type or webhook works. Registration and callback verification tests must cover malformed or invalid signatures before directory access, unknown/inactive Inboxes, mixed-account batches, credential isolation, and same-person interactions with multiple Inboxes.

## Connection flow to design and verify

Use separate Platform callback URLs through the existing `/webhook/inboxes/{platform}` contract: WhatsApp and Instagram now in scope, Facebook Messenger later when its adapter exists. The dashboard walkthrough superseded the shared `meta-messenger` proposal. Verify generated URLs, GET/POST behavior, signature-first admission, payload/Platform mismatch rejection, and setup instructions. Complete the Meta app setup walkthrough before implementing Wappa callback/text support and the consumer example at `../wappa_examples/simple_echo_example` (relative to the Wappa repository root).

Reuse the Inbox Directory/source seam from ADR-0022. InboxCredentialService and the CredentialRecord union now support WhatsApp and Instagram; retain their Platform-discriminated variants and validation. Symphonai's durable source and credential-access adapter still require Instagram migration. Do not manufacture a WA record or an artificial WABA relationship.

Separate three operations: Meta's GET callback verification (application endpoint), account authorization/subscription (connection setup), and resolving an already-known Inbox from an incoming POST (runtime intake). An incoming message must not authorize or create an Inbox.

Proposed connection flow: host starts selected Meta login/consent flow; adapter validates granted scopes and professional-account identity; Wappa builds the encrypted Instagram record; host commits its durable connection; host calls source-driven `refresh_inbox(InboxRef)`; account subscriptions and required bootstrap complete; host marks connection ready after verification. Pending connections may need credentials before subscription succeeds, so readiness is host connection state, not an assumption that directory presence proves onboarding complete. Failures and retries must preserve that distinction. Authorization callback format depends on the selected login flow; no WA registration payload is assumed reusable. Token refresh/revocation updates the durable source and directory through the same versioned mutation discipline.

## Migration impact

The breaking migration touches `IMessenger`, WhatsApp implementation, new Instagram implementation, MessengerFactory, processors, credential variants, User/Inbox models, MessageResult, SendInvocation/pipeline, SSE/PubSub/API events, REST request/response models, CLI templates, generated examples, tests, and host callers such as Symphonai. Template transport, expiry and background factories must be audited as independent public paths. Do not change only the send_text signature and leave mixed contracts elsewhere.

Existing [messaging architecture](../../../../../wappa/messaging/ARCHITECTURE.md) and [deferred-split decision](../../../../tech-requests/006-defer-messenger-split.md) permit revisiting the seam when a real second Platform demonstrates pressure. This research identifies that pressure, but does not resolve every split. Once the design is selected, update the canonical glossary, architecture, public contract, and any warranted ADR together with implementation.

## Candidate verification scenarios

1. IG DM `hello` -> normalized InboundMessageWebhook -> unchanged host logic -> IG text response to the same Inbox-scoped address.
2. WA text/buttons/lists/media/Templates -> explicit DirectMessage targets -> existing provider behavior preserved.
3. IG comment -> IncomingCommentWebhook with correct comment/Post References -> explicit public reply.
4. IG comment -> PrivateReply text -> recipient answers -> ordinary incoming DM flow.
5. Wrong-Inbox target or non-IG PrivateReply -> deterministic rejection before I/O.
6. Unsupported content/target combination -> explicit rejection, no alternative delivery or visibility substitution.
7. Echo/control/deletion event -> correct typed handling, no accidental automated text reply.
8. Post enrichment failure -> explicit read failure; processor remains pure and does not invent post metadata or guarantee downloadable bytes.
9. Batch/duplicate/uncertain-send behavior -> deliberate policy consistent with admission and private-reply constraints.

## Host takeover integration

Inspect Symphonai's existing takeover implementation before proposing changes. Verify that its ownership policy can connect to Wappa's current handler, outbound middleware, and event-streaming seams. Test all automated send paths, including delayed jobs and concurrent ownership changes. Add a Wappa extension point only for a demonstrated gap; agent assignment and workflow remain host responsibilities.
