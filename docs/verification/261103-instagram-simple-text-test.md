# Instagram simple text: goals, tests, evidence, and learnings

Date: 2026-11-03. Evidence from the local Wappa checkout, the sibling `wappa_examples/simple_echo_example`, Meta dashboard screenshots, server logs, controlled Graph API checks, and offline tests. Times below are America/Bogota. No tokens, secrets, raw authorization callbacks, or personal account IDs belong in this document. Test labels A/B replace the real sender identities.

Historical verification of the initial text echo, seen/echo lanes and sequential two-sender routing on 2026-11-03. This records Wappa 0.33.0 behavior, including names later changed; it is not a current API or environment reference. Later connection, state-isolation and Host integration results are in the [conversations ledger](261103-instagram-conversations-live-tests.md). Current behavior belongs to the [Instagram reference](../platforms/instagram.md).

## Setup under test

- Wappa reported version 0.33.0; Graph API calls and dashboard subscriptions used v26.0.
- One Meta app already had WhatsApp; Instagram messaging/content was added as a separate use case in that app.
- Instagram used API setup with Unified Login and a configuration created from Meta's template, marked Instagram Login Compatible and Selected.
- One public professional Instagram account was connected as an Instagram Tester. This does not establish that a Creator-specific flow was tested.
- Local server: `uv run wappa dev app/main.py --port 8000`; public HTTPS forwarding through ngrok to that server.
- Callback: `https://<current-tunnel-host>/webhook/inboxes/instagram`; WhatsApp keeps its own callback. All selected Instagram fields share this callback.
- Explicit Inbox routing with an encrypted active Instagram record supplied through the example's IInboxDirectorySource; memory cache backend.
- Both app-level and account-level selections covered `messages` and `messaging_seen`.

The template showed permissions for ads, publishing, comments, and messaging. No evidence confirms those optional permissions were subsequently removed; their presence does not make those capabilities part of the text test.

## Test matrix

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

## First exchange: observed sequence

At 11:24:04 the callback admitted an incoming text and created an InboundMessageWebhook. The shared runtime bound the Inbox, native User ID, Messenger, and handler. SimpleEchoHandler called send_text with a DirectMessage target. The native send returned HTTP 200 at 11:24:07.

At 11:24:08 an outbound echo became SystemWebhook MESSAGE_ECHO and ran the system handler without another text send. At 11:24:09 a seen notification became StatusWebhook READ and ran the status handler.

The callback's own 200 acknowledgement precedes completion of the background send. It means admission, not that the User has received the outgoing text. Likewise, a native API 200 is acceptance; later echo/read evidence and the conversation establish subsequent behavior.

## Two-sender test: procedure and results

Procedure used:

1. Sender A sends `isolation-A-01` to the connected professional account.
2. Sender B uses a different Instagram account to send `isolation-B-01`.
3. Compare native sender IDs, dispatch identity, send outcomes, and outbound echo identity. Inspect the recipient chats to verify which text each saw.

| Sender | Incoming | Native send accepted | Outbound echo |
| --- | --- | --- | --- |
| A | 11:28:59, `isolation-A-01` | 11:29:00, HTTP 200 | 11:29:02, system lane with A's User context |
| B | 11:29:56, `isolation-B-01` | 11:29:57, HTTP 200 | 11:29:59, system lane with B's User context |

Both targeted the same professional-account Inbox; their native sender IDs were different. The user reported DONE after the procedure. The supplied log excerpt independently proves separate identities, accepted sends, and separate echo contexts. It does not contain recipient-chat screenshots, a pair of new READ events, or a simultaneous execution window. Do not claim those observations from this excerpt.

## Offline regression coverage

[test_instagram_text.py](../../tests/test_instagram_text.py) covers:

- Signed HTTP callback → actual routing/processor/handler → mocked native text request, including two senders and exact text/Unicode preservation.
- GET challenge without credential lookup; unsigned POST rejected before lookup; malformed Platform/recipient scope rejected.
- Native identity retained without filling WA phone/BSUID fields.
- Seen, echo, deletion, quick-reply, and attachment notifications avoid the ordinary text lane where they do not belong.
- Unregistered later-account routing failure and cross-Inbox target rejection.
- Unsupported send operations and oversized text rejected without HTTP calls.
- Provider rejection, 5xx, malformed success, and timeout outcomes bounded without automatic retries or credential leakage in results.
- Encrypted Instagram record roundtrip, rotation, source resolution, and deactivation.

[test_platform_event_logging.py](../../tests/test_platform_event_logging.py) covers native Instagram identity, WA BSUID/phone fallback, account-only events, omission of absent identity, and native message/recipient references in status logs. Existing Inbox routing tests cover callback startup guidance and preserve the no-legacy-fallback rule.

These are offline tests. They do not substitute for Meta permissions, App Review, actual account authorization, live media support, or cross-account production certification. The final offline results after the logging change are recorded below.

## Logging findings and fixes

Observed problems:

- Startup originally advertised only WhatsApp even though Instagram was installed; the banner was hard-coded.
- Default system logging printed `wa_id: None, user_id: None` for Instagram echoes, despite valid native identity on the Universal Model.
- The example logged failures but no clear send-success record.
- Default handlers and the example repeated similar status/system messages.
- SYSTEM_LOG_LEVEL=DEBUG also exposed verbose httpcore connection traces; those traces are transport diagnostics, not evidence of missing fields.

Changes:

- Startup lists installed Platform callback URLs, constrained by routing mode.
- Default system logs use Platform, Inbox, and available User identity; empty WA-only fields are omitted rather than filled with fabricated values.
- Default status logs identify Platform, native Message ID, and available recipient.
- The example emits `Echo accepted` with Platform, recipient, inbound Message ID, and outbound Message ID. Acceptance is not labeled delivery.
- Example-specific status/system observations are DEBUG messages; the shared default handlers remain the normal INFO records.

The earlier live log excerpts predate these logging improvements. Validation of the formatting is offline unless a new live run is explicitly recorded. For quieter manual testing, use SYSTEM_LOG_LEVEL=INFO and restart; no framework HTTP logger suppression or new environment setting was introduced.

## Final local verification after logging improvements

- `uv run pytest -q`: **1063 passed, 1 skipped**, 23.55 seconds.
- `uv run ruff check .`: passed.
- `uv run mypy wappa`: passed, 360 source files.
- `uv run mypy ../wappa_examples/simple_echo_example/app`: passed, 5 source files.
- Changed-source formatting, draft Markdown link checks, and `git diff --check`: passed.

These results were obtained after the shared logging and echo-result logging changes. The two-sender live evidence above was collected before those changes; restart/reload the example to inspect the new formatting on subsequent traffic.
