# Instagram simple text: goals, tests, evidence, and learnings

Date: 2026-11-03. Evidence from the local Wappa checkout, the sibling
`wappa_examples/simple_echo_example`, Meta dashboard screenshots, server logs,
controlled Graph API checks, and offline tests. Times below are America/Bogota.
No tokens, secrets, raw authorization callbacks, or personal account IDs belong
in this document. Test labels A/B replace the real sender identities.

Related: [setup walkthrough](../platforms/instagram-setup.md), [decisions](../platforms/instagram-decisions.md),
[roadmap](../platforms/instagram-design-roadmap.md), [research](../platforms/instagram-research.md),
[ADR-0025](../adr/0025-messenger-contract.md).

## 1. Goals and scope

| Goal | Definition of success | Current evidence |
| --- | --- | --- |
| Basic text slice | A real Instagram DM enters the universal message handler and send_text echoes it through the correct Inbox. | Verified live. |
| Supporting event lanes | Outbound echoes are system events, seen notifications are READ statuses, and neither triggers another reply. | Verified live. |
| Two senders, one Inbox | Distinct native sender IDs remain distinct through dispatch and their outbound echo events. | Verified sequentially; no concurrent send or stateful flow tested. |
| Self-service connection, milestone B | A customer connects through Meta login; the consumer exchanges the code, discovers assets, persists credentials, and subscribes automatically. | Planned; dashboard token generation is not this milestone. |
| Symphonai agent, milestone C | A configured agent responds through the same Wappa transport with host-owned takeover rules. | Planned; the echo example contains no AI agent. |

The full milestone A acceptance criteria also include broader multi-Inbox and
multi-User validation. This record proves the first live slice and the specific
checks below; it does not declare the whole Instagram roadmap complete.

Feature order remains text → supported message types → conversational
scores/intake → comments → post retrieval. Reactions remain excluded initially.

## 2. Setup under test

- Wappa reported version 0.33.0; Graph API calls and dashboard subscriptions
  used v26.0.
- One Meta app already had WhatsApp; Instagram messaging/content was added as
  a separate use case in that app.
- Instagram used API setup with Unified Login and a configuration created
  from Meta's template, marked Instagram Login Compatible and Selected.
- One public professional Instagram account was connected as an Instagram
  Tester. This does not establish that a Creator-specific flow was tested.
- Local server: `uv run wappa dev app/main.py --port 8000`; public HTTPS
  forwarding through ngrok to that server.
- Callback: `https://<current-tunnel-host>/webhook/inboxes/instagram`; WhatsApp
  keeps its own callback. All selected Instagram fields share this callback.
- Explicit Inbox routing with an encrypted active Instagram record supplied
  through the example's IInboxDirectorySource; memory cache backend.
- Both app-level and account-level selections covered `messages` and
  `messaging_seen`.

The template showed permissions for ads, publishing, comments, and messaging.
No evidence confirms those optional permissions were subsequently removed;
their presence does not make those capabilities part of the text test.

## 3. Test matrix

| ID | Test | Result | Evidence and limit |
| --- | --- | --- | --- |
| ST-01 | Start the example without an Instagram account ID/token. | Pass, local. | Actual Wappa CLI process started with synthetic callback settings and an empty source. No provider send was attempted. |
| ST-02 | Validate GET challenge through the public tunnel. | Pass, live. | Public request returned HTTP 200 and the exact supplied challenge. This checks connectivity and token matching. |
| ST-03 | Meta dashboard Verify and save. | Pass, live at 11:06. | A real Meta GET request reached the callback and returned 200. It does not validate POST signatures by itself. |
| ST-04 | Generate a token before selecting a login configuration. | Expected failure, observed. | Dashboard reported “Select a configuration in Step 1 before generating an access token,” despite the modal heading “Token generated.” |
| ST-05 | Create/select compatible configuration, then acquire the test token. | Pass, setup. | Configuration became Selected; credentials supplied locally later passed an account access check. No secret value was copied into documentation. |
| ST-06 | Verify token/account pair. | Pass, live. | `uv run python -m app.setup` verified returned professional-account identity through graph.facebook.com. |
| ST-07 | Subscribe the account to messages and seen. | Pass, live. | `uv run python -m app.setup --subscribe` returned success. Screenshot separately confirmed the app's selected fields. |
| ST-08 | Send a real text DM to the professional account. | Pass, live at 11:24. | InboundMessageWebhook reached SimpleEchoHandler with the receiving Inbox and native sender ID. |
| ST-09 | Echo the text through send_text. | Pass, live at 11:24. | Native messages POST returned 200, followed by an outbound echo event and a READ notification. No send failure was logged. |
| ST-10 | Prevent business-originated echo from becoming another User message. | Pass for observed exchanges. | MESSAGE_ECHO followed the system lane; no additional automated response chain appeared in the supplied logs. This is not duplicate-callback idempotency. |
| ST-11 | Normalize seen notification. | Pass, live at 11:24:09. | StatusWebhook READ reached process_status with native message reference and scoped recipient identity. |
| ST-12 | Two different senders to the same professional account. | Pass for sequential routing evidence. | A at 11:28:59 and B at 11:29:56 had different IGSIDs; both sends returned 200 and their echo events retained the respective User context. |
| ST-13 | Live simultaneous sends/state isolation. | Pending. | ST-12 messages were about 57 seconds apart; the echo app has no multi-step User state to test. |
| ST-14 | Same person writes to two different registered Instagram Inboxes. | Pending live. | No second professional account was connected during this test. |
| ST-15 | Signature, routing, and target rejection contracts. | Pass, offline. | See the automated coverage below; no malformed requests were deliberately sent to Meta. |

## 4. First exchange: observed sequence

At 11:24:04 the callback admitted an incoming text and created an
InboundMessageWebhook. The shared runtime bound the Inbox, native User ID,
Messenger, and handler. SimpleEchoHandler called send_text with a DirectMessage
target. The native send returned HTTP 200 at 11:24:07.

At 11:24:08 an outbound echo became SystemWebhook MESSAGE_ECHO and ran the
system handler without another text send. At 11:24:09 a seen notification became
StatusWebhook READ and ran the status handler.

The callback's own 200 acknowledgement precedes completion of the background
send. It means admission, not that the User has received the outgoing text.
Likewise, a native API 200 is acceptance; later echo/read evidence and the
conversation establish subsequent behavior.

## 5. Two-sender test: procedure and results

Procedure used:

1. Sender A sends `isolation-A-01` to the connected professional account.
2. Sender B uses a different Instagram account to send `isolation-B-01`.
3. Compare native sender IDs, dispatch identity, send outcomes, and outbound
   echo identity. Inspect the recipient chats to verify which text each saw.

| Sender | Incoming | Native send accepted | Outbound echo |
| --- | --- | --- | --- |
| A | 11:28:59, `isolation-A-01` | 11:29:00, HTTP 200 | 11:29:02, system lane with A's User context |
| B | 11:29:56, `isolation-B-01` | 11:29:57, HTTP 200 | 11:29:59, system lane with B's User context |

Both targeted the same professional-account Inbox; their native sender IDs
were different. The user reported DONE after the procedure. The supplied log
excerpt independently proves separate identities, accepted sends, and separate
echo contexts. It does not contain recipient-chat screenshots, a pair of new
READ events, or a simultaneous execution window. Do not claim those observations
from this excerpt.

## 6. Offline regression coverage

[test_instagram_text.py](../../tests/test_instagram_text.py) covers:

- Signed HTTP callback → actual routing/processor/handler → mocked native
  text request, including two senders and exact text/Unicode preservation.
- GET challenge without credential lookup; unsigned POST rejected before
  lookup; malformed Platform/recipient scope rejected.
- Native identity retained without filling WA phone/BSUID fields.
- Seen, echo, deletion, quick-reply, and attachment notifications avoid the
  ordinary text lane where they do not belong.
- Unregistered later-account routing failure and cross-Inbox target rejection.
- Unsupported send operations and oversized text rejected without HTTP calls.
- Provider rejection, 5xx, malformed success, and timeout outcomes bounded
  without automatic retries or credential leakage in results.
- Encrypted Instagram record roundtrip, rotation, source resolution, and
  deactivation.

[test_platform_event_logging.py](../../tests/test_platform_event_logging.py)
covers native Instagram identity, WA BSUID/phone fallback, account-only events,
omission of absent identity, and native message/recipient references in status
logs. Existing Inbox routing tests cover callback startup guidance and preserve
the no-legacy-fallback rule.

These are offline tests. They do not substitute for Meta permissions, App
Review, actual account authorization, live media support, or cross-account
production certification. The final check results are recorded below after
the logging change is validated.

## 7. Logging findings and fixes

Observed problems:

- Startup originally advertised only WhatsApp even though Instagram was
  installed; the banner was hard-coded.
- Default system logging printed `wa_id: None, user_id: None` for Instagram
  echoes, despite valid native identity on the Universal Model.
- The example logged failures but no clear send-success record.
- Default handlers and the example repeated similar status/system messages.
- SYSTEM_LOG_LEVEL=DEBUG also exposed verbose httpcore connection traces;
  those traces are transport diagnostics, not evidence of missing fields.

Changes:

- Startup lists installed Platform callback URLs, constrained by routing mode.
- Default system logs use Platform, Inbox, and available User identity; empty
  WA-only fields are omitted rather than filled with fabricated values.
- Default status logs identify Platform, native Message ID, and available
  recipient.
- The example emits `Echo accepted` with Platform, recipient, inbound Message
  ID, and outbound Message ID. Acceptance is not labeled delivery.
- Example-specific status/system observations are DEBUG messages; the shared
  default handlers remain the normal INFO records.

The earlier live log excerpts predate these logging improvements. Validation
of the formatting is offline unless a new live run is explicitly recorded.
For quieter manual testing, use SYSTEM_LOG_LEVEL=INFO and restart; no framework
HTTP logger suppression or new environment setting was introduced.

## 8. Setup and architecture learnings

1. One Meta app can expose separate callback configuration for different use
   cases. Callback grouping is distinct from Platform identity; this project
   selected separate WhatsApp/Instagram/Messenger URLs.
2. Login redirect and webhook Callback URL are different contracts. A verified
   webhook does not implement OAuth code exchange.
3. Unified Login requires a selected compatible configuration even for the
   dashboard's test-token path. Complete/select that before Generate token.
4. The dashboard's role is Instagram Tester, distinct from the general Tester
   role. This controlled setup used a public professional account.
5. App field selection and authorized account subscription are separate.
   Success on one does not prove the other.
6. WP_WEBHOOK_VERIFY_TOKEN is Wappa's existing canonical GET-token variable;
   WHATSAPP_WEBHOOK_VERIFY_TOKEN is unused. META_APP_SECRET authenticates POST
   bytes and is not interchangeable with the GET token.
7. Explicit mode uses the Directory/source authority. WP_ACCESS_TOKEN,
   WP_PHONE_ID, and WP_BID must not be active in this example. Wappa requires
   no global IG_ACCOUNT_ID variable; the optional IG pair belongs to the
   example bootstrap, and its encrypted record can later supply the source.
8. .env changes may not trigger the Python reloader. Restart after configuring
   credentials. Library changes may also require a restart when the watcher
   only watches the example directory.
9. IGSID is scoped identity, not a phone number or WA BSUID. Keep InboxRef with
   targets and scope identity by Inbox.
10. The processor stays pure. Credential resolution, context assembly, HTTP,
    account registration, and content retrieval do not belong in parsing.
11. An outbound echo is not a new incoming User message. Preventing that loop
    is different from idempotently handling webhook redelivery.
12. Subscription availability is not implemented feature support. Keep reactions
    and cross-app handover excluded initially; additional fields require their
    own schemas, mappings, tests, and scope decisions.
13. Keep the vocabulary distinct: WhatsApp Template, Interactive Message,
    Conversational Flow, and Application Scaffold name different concepts.

## 9. Inputs for a future setup/test skill

This is evidence for a later skill, not an executable skill or approval to
implement the remaining roadmap. A future skill should encode:

- Preconditions: selected login setup, compatible configuration, authorized
  professional account, HTTPS callback, role/access requirements, and the
  chosen Inbox credential authority.
- Ordered gates: build/start → public challenge → Meta verification → selected
  configuration → token acquisition/account check → account subscription →
  restart → real DM → echo-system behavior → seen → multi-User checks.
- Secret handling: inspect configuration readiness without printing values;
  keep tokens/codes and raw verification URLs out of artifacts.
- Evidence rules: distinguish callback acknowledgement, send acceptance,
  outbound echo, read receipt, and what the recipient actually observed.
- Failure branches grounded in this session: missing config, wrong role,
  duplicate/obsolete env names, stale process configuration, and app versus
  account subscription mismatch.
- Ownership: Wappa owns Platform transport/runtime; the consumer owns login
  UI/callback orchestration, durable connection state, business idempotency,
  conversational flows, and human takeover policy.
- Stop conditions: report a missing credential/consent/provider prerequisite;
  do not manufacture credentials, use signature bypasses, or replace live
  evidence with a synthetic callback while claiming a live pass.

Pending follow-up tests remain explicit: truly overlapping senders, stateful
flow isolation, a second Inbox, retry/idempotency behavior, Creator onboarding,
full self-service login, and Symphonai agent/takeover integration.

## 10. Final local verification after logging improvements

- `uv run pytest -q`: **1063 passed, 1 skipped**, 23.55 seconds.
- `uv run ruff check .`: passed.
- `uv run mypy wappa`: passed, 360 source files.
- `uv run mypy ../wappa_examples/simple_echo_example/app`: passed, 5 source files.
- Changed-source formatting, draft Markdown link checks, and
  `git diff --check`: passed.

These results were obtained after the shared logging and echo-result logging
changes. The two-sender live evidence above was collected before those changes;
restart/reload the example to inspect the new formatting on subsequent traffic.

## Delivery-order clarification

After the initial text tests, the user selected completion of the agreed
Instagram capability scope first, the full self-service Unified Login experience
second, and Symphonai integration third. The initial echo is checkpoint A1
within the broader stage A. Test evidence recorded above is unchanged; it does
not establish completion of later message types, comments, or content retrieval.
See the current [roadmap](../platforms/instagram-design-roadmap.md#success-milestones).
