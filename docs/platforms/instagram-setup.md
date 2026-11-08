# Instagram use-case setup in an existing Meta app

Test record: [simple text tests and learnings](../verification/261103-instagram-simple-text-test.md).

WhatsApp counterpart (manual and Embedded Signup): [whatsapp-setup.md](whatsapp-setup.md).

This is observed setup evidence, including later checkpoints below. The implementation series closed on 2026-11-08 with gates A, B and C passed ([live evidence](../verification/261103-instagram-conversations-live-tests.md)); its plan and PRDs are in git history. The portable setup reference ships in the `wappa-apps` skill.


Date: 2026-11-03. Living walkthrough for adding Instagram messaging and content management to a Meta app that already has WhatsApp. Current implementation target: incoming text DM and text echo. This records dashboard observations and documented next steps; it does not claim setup or Wappa Instagram support is complete.

Related: [research](instagram-research.md), [decisions](instagram-decisions.md), [roadmap](instagram-design-roadmap.md).

## Current position

- The Instagram use case has been added and its setup screens inspected.
- The dashboard recommends **API setup with Unified login** and labels Instagram Login legacy. Use Unified Login for this walkthrough.
- The Unified Login configuration is selected and the professional test account is added. The user supplied credentials locally; account access was verified successfully against Graph API.
- Instagram has a separate **Configure webhooks** step with its own Callback URL and Verify token fields.
- Meta GET verification, professional account access, and account subscriptions succeeded. A real incoming text, accepted outbound echo send, outbound echo event, and READ status were verified on 2026-11-03 at 11:24 America/Bogota.
- The initial Wappa text adapter and sibling simple_echo_example are implemented and have been exercised against the live Instagram account. Self-service OAuth onboarding and Symphonai integration are separate later milestones.

## 1. Add the Instagram use case

1. Open the existing Meta app that already contains WhatsApp.
2. Choose **Add more use cases** and the **Business messaging** category.
3. Select **Manage messaging & content on Instagram** and add it.
4. Open its Instagram API setup.

The separate **Engage with customers on Messenger from Meta** option concerns Facebook Page messaging. It is not needed for the first Instagram text example.

## 2. Open Unified Login setup

Choose **API setup with Unified login** in the sidebar. Do not mix credentials or API hosts from the Instagram Login tab into this setup.

The configuration summary in the supplied Unified Login screenshot shows:

| Setting | Observed value |
| --- | --- |
| Login variation | General |
| Access token | System-user access token (SUAT) |
| Expiration | Never (system-user token) |
| Business assets | Instagram account required; ad account optional |
| Permissions displayed | `ads_management`, `ads_read`, `instagram_basic`, `instagram_manage_messages`, `instagram_manage_comments`, `instagram_content_publish` |

These are displayed configuration values, not proof that every listed permission is required for text messaging. Inspect the creation dialog to establish what can be selected. Request the capabilities actually needed; ads, comment management, and publishing are not requirements of our text echo goal.

Meta's Unified Login documentation calls the resulting credential a **Business Integration System User Access Token** and uses `graph.facebook.com`. It also lists a business portfolio as required. Confirm that the intended Business and Creator onboarding paths satisfy this prerequisite. “Never” in the expiration field does not prevent revocation or loss of asset access. [Unified Login overview](https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-unified-login)

## 3. Create a login configuration

Choose **Create new configuration** if no compatible configuration exists. In
the observed walkthrough the user completed the template confirmation dialog
and selected the compatible Unified Login configuration; subsequent checkpoints
below record that result.

Record the dialog's choices before saving: configuration name/ID, login
variation, requested assets, permission selection and token settings. The
observed template's permission list is not proof that every field is editable
or that every permission is needed for the selected Wappa capabilities.

The objective is a configuration for an authorized client to share an Instagram professional account for messaging. Dashboard-generated test tokens may assist controlled testing, but they do not satisfy the self-service login milestone.

## 4. Register the login redirect URL

The **Redirect URL** section determines where Meta returns the browser after authorization. The supplied screenshot currently selects an existing WhatsApp-oriented redirect ending in `/settings/symphonai/connect-whatsapp`; that does not establish an Instagram callback implementation.

1. Identify the consumer endpoint/page that will complete Instagram authorization.
2. Register its exact public URL under **Register a new redirect URL** and save it.
3. Select it for the Instagram login configuration.
4. After selecting a compatible configuration and saving a redirect, obtain the generated **Login URL**.

Do not invent a working Instagram redirect route or reuse the WhatsApp callback without inspecting its behavior. Its final path and implementation are pending. A development tunnel URL must still point to the actual consumer callback.

The consumer must bind authorization to the initiating session using validated OAuth state. Meta documents a redirect carrying a code, followed by server-side code exchange. Token storage and connection readiness must be integrated with the existing Wappa Inbox Directory seam when implemented. [Unified Login overview](https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-unified-login)

## 5. Connect an authorized professional account

For the self-service path, use the generated login URL only with the actual
implemented consumer OAuth redirect, complete consent, and verify the selected
professional account and granted permissions. Exchange the returned code
server-side using the selected flow's documented authentication contract. This
path is still pending; the verified controlled echo used dashboard token generation.

Record only non-secret operational evidence: login configuration ID, account ID, granted permission names, token type, and connection/subscription status. Do not put bearer tokens, app secrets, authorization codes, or verify-token values in this document.

The controlled walkthrough used the **Instagram Tester** role and invitation
acceptance described below. Verify current selected-flow requirements before
repeating that path. A controlled tester connection and onboarding independent
customer accounts are different acceptance checks.

## 6. Configure the separate Instagram webhook

Keep the existing WhatsApp callback separate. The chosen callback design is one URL per Platform:

| Platform | Wappa route shape | Status |
| --- | --- | --- |
| WhatsApp | `/webhook/inboxes/whatsapp` | Existing adapter; preserve current setup. |
| Instagram | `/webhook/inboxes/instagram` | GET verification and real text/echo/READ observed; broader capability and self-service gates remain open. |
| Facebook Messenger | `/webhook/inboxes/messenger` | Future adapter/Platform addition. |

The screenshot confirms Instagram's separate configuration fields. Separate URLs are our design choice; this does not mean Meta forbids reusing a URL.

Once a functioning public HTTPS Instagram endpoint exists:

1. Enter its URL in **Callback URL**.
2. Enter the value configured for its GET challenge in **Verify token**.
3. Choose **Verify and save**.
4. After verification, inspect the available fields and subscribe to `messages` for the first text path. Recheck the chosen setup's permission/field matrix; postbacks and other capabilities belong to later scope.

GET verification must validate the verify token and return the supplied challenge. POST callbacks must authenticate the exact body bytes before parsing or resolving an Inbox. The verify token is not the POST signature secret. Current Wappa Meta configuration retains WhatsApp-specific verify-token naming; do not introduce an undocumented Instagram environment variable during setup. [Webhook setup](https://developers.facebook.com/documentation/instagram-platform/webhooks/setup)

**Login redirect URL and webhook Callback URL are different endpoints:** the first receives the user's authorization return; the second receives Meta verification requests and event notifications.

## 7. Enable notifications for the connected account

Saving the app's callback and choosing fields does not complete account-level subscription. For Unified Login, Meta documents subscribing each shared Instagram professional account through:

```text
POST https://graph.facebook.com/{configured-version}/{instagram-account-id}/subscribed_apps
subscribed_fields=messages
credential: Business Integration System User Access Token
```

The version must match the selected application configuration. Do not use an Instagram User token or `graph.instagram.com` for this Unified Login operation. Verify the account subscription response and connection readiness; a stored token alone does not prove events will arrive. [Account subscriptions](https://developers.facebook.com/documentation/instagram-platform/webhooks/setup#enable-subscriptions)

## 8. Verify text end to end

The dashboard and webhook setup documentation state the app must be published/Live to receive notifications for app users. Verify access/review requirements for the intended test audience separately; publishing does not prove every permission is approved.

After implementation and configuration, verify:

- Successful GET callback verification and account-level subscription.
- A real person sends a text DM to the connected account.
- A signed Instagram callback reaches the Instagram endpoint and resolves the correct Inbox and sender.
- The consumer receives the universal message and echoes its text through the Inbox-bound Messenger.
- The person receives the text; outbound echo events do not start a response loop.
- A second person's messages and another registered account remain isolated.

Target consumer example: `../wappa_examples/simple_echo_example`, relative to the Wappa repository root. Its local implementation/startup instructions are recorded below.

## Remaining setup evidence to collect

- Create new configuration dialog, selected options, and resulting configuration ID.
- Actual Instagram login redirect route and successful authorization/code exchange.
- Complete token/test-account section and any Creator-specific readiness prerequisite.
- Verified Instagram callback, available field selection, and account subscription result.
- Real text DM and response evidence.

Primary references: [Unified Login](https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-unified-login), [authentication](https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-unified-login/authentication), [permissions](https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-unified-login/permissions), [webhook setup](https://developers.facebook.com/documentation/instagram-platform/webhooks/setup), [fields and permissions](https://developers.facebook.com/documentation/instagram-platform/webhooks/fields). Dashboard labels are recorded from the user's screenshots; unvisited dialogs and untested operations remain pending.

## Local implementation ready for callback verification

The sibling example at `../wappa_examples/simple_echo_example` now starts with
an empty Inbox source so GET verification does not require an Instagram account
ID/token. From that example directory:

```bash
uv sync
cp -n .env.example .env
uv run python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
```

Set META_APP_SECRET, WP_WEBHOOK_VERIFY_TOKEN, and SYSTEM_TOKEN_ENC_KEY in `.env`.
Remove legacy WP_ACCESS_TOKEN/WP_PHONE_ID/WP_BID settings for this explicit-mode
example. Keep the generated encryption key stable. Then:

```bash
uv run wappa dev app/main.py --port 8000
```

Expose port 8000 over HTTPS and use
`https://YOUR-TUNNEL-HOST/webhook/inboxes/instagram` in Meta. Set the same GET
verify token and choose Verify and save. A local smoke test launched the actual
Wappa CLI and obtained HTTP 200 with the exact challenge. This proves local
startup/GET behavior, not Meta delivery.

For real echoes, the consumer needs an authorized Inbox record. The example's
optional IG_ACCOUNT_ID/IG_ACCESS_TOKEN pair bootstraps that record locally; these
are example settings, not mandatory Wappa variables. Once written, the server can
load the encrypted record without the IG pair; retain its encryption key. Its `python -m app.setup`
checks account access; `python -m app.setup --subscribe` explicitly subscribes
to messages and messaging_seen after callback verification. No OAuth login UI or
callback is implemented by this controlled test example.

Startup guidance now prints an Instagram Webhook URL in explicit mode alongside
the installed WhatsApp callback. After changing library code, restart the
example's `wappa dev` process if its watcher only watches the example directory;
the local callback still needs its public HTTPS tunnel prefix in Meta.

## Verified callback and next controlled-account step

Meta's actual GET verification returned HTTP 200 on 2026-11-03. This confirms
callback reachability and matching verify token, not account authorization or
message delivery. Do not record the query string's verify-token value here.

The current [Unified Login get-started guide](https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-unified-login/get-started#step-2-generate-a-test-access-token)
explicitly documents a dashboard test-token path: Generate access tokens → Add
account → invite the professional account as Instagram Tester → accept under
Instagram web Settings → Website permissions → Apps and websites → Tester
Invites → Generate token and complete login. A real professional account is
required; Meta synthetic test users are not supported. Keep the generated token
local; it is shown only once. The account ID should be taken from the connected
account evidence, not inferred from the token.

For this first controlled echo, first create/select a compatible Step 1 configuration,
then use that dashboard test path before building the consumer OAuth callback UI. Set the example's IG_ACCOUNT_ID/IG_ACCESS_TOKEN,
restart its server, run `uv run python -m app.setup` to verify access through
`graph.facebook.com`, then `uv run python -m app.setup --subscribe` to explicitly
subscribe the account. A failing check must be resolved as an account/token/
permission problem; do not silently switch to the legacy Instagram Login host.
The full login configuration and callback flow remain milestone B.

## Dashboard-confirmed prerequisite: configuration before test token

The professional test account was added successfully, but Generate token displayed
“Select a configuration in Step 1 before generating an access token.” The modal
heading “Token generated” is not evidence of a token when that error is present.
The correct order is Step 1 Create new configuration → select/use a compatible
configuration → Step 2 Generate token. The dashboard test-token shortcut does not
bypass Step 1. Inspect the creation dialog next; do not invent an OAuth redirect
route or replace the already verified webhook callback to work around this error.
Keep the example's optional account ID/token pair unset until both are available.

## Configuration created and selected

The user completed Create from template. Step 1 now has a green check and the
Unified Login configuration is Selected with Instagram Login Compatible status.
The configuration preview and any later permission edits should be recorded
separately; creation alone does not prove that optional permissions were removed.
Retry Step 2 Generate token for the connected professional account next.

The screenshot still selects an older WhatsApp-oriented redirect URL. Do not use
that generated Login URL to test the future consumer OAuth flow. The immediate
controlled echo uses the dashboard test-token path; a real Instagram OAuth
redirect must be implemented and registered before self-service login testing.
No OAuth callback endpoint is implied by the webhook verification endpoint.

## Live account checkpoint

On 2026-11-03, the user populated the example's account ID/token pair locally.
`uv run python -m app.setup` successfully verified professional account access.
`uv run python -m app.setup --subscribe` subsequently verified access again and
received success subscribing the account to `messages,messaging_seen`.
No credentials or authorization response bodies are recorded in this document.
Restart the running server to load the updated .env/source record, then send a
real text DM from another Instagram account. Receipt and outbound echo remain
unverified until that exchange is observed.

## Live text exchange verified

At 11:24 America/Bogota on 2026-11-03, the user sent a real text DM and supplied
logs showing the complete first slice. The local runtime logfile corroborates
inbound dispatch, echo-system dispatch, and read-status handling. The host's
persisted record is an active Instagram record with an encrypted token envelope.
No IDs, text payload, token, or raw HTTP response is copied here.

| Observed behavior | Evidence |
| --- | --- |
| Incoming text | InboundMessageWebhook dispatched to SimpleEchoHandler. |
| Outbound text | Native POST to the professional account's messages endpoint returned HTTP 200; no send failure logged. |
| Business echo | SystemWebhook MESSAGE_ECHO dispatched without triggering another text reply. |
| Seen | StatusWebhook READ dispatched to process_status with the native message reference. |

For this slice, retain only the selected app/account subscriptions `messages`
and `messaging_seen`. The messages feed also produced the observed outbound
echo. The other dashboard fields are provider capabilities, not implementations
of corresponding Wappa handlers. Their selection remains in decisions.md.
Postbacks belong to the interactive-flow phase; comments/live comments/public
mentions to the comment/content phase; edit lifecycle needs explicit mapping;
reactions and cross-app handover remain excluded initially. Referral and story
insights are additional optional scope. All subscribed fields for this
Instagram configuration use its existing callback URL, not a URL per field.

This evidence proves one connected account and one real User exchange. Repeat
with another User and another Inbox before claiming broader live isolation
coverage. Callback redelivery, host takeover, and OAuth onboarding retain their
separate documented boundaries.
