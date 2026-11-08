---
checked_on: 2026-11-06
checked_against: Meta "Instagram API with Unified Login" (authentication, get-started), Instagram webhooks fields/examples, WhatsApp Cloud API get-started, webhooks and Embedded Signup pages, and live dashboard walkthroughs (2026-11-03 Instagram, 2026-11-05 WhatsApp) with Graph v26.0
revision: 2
---

# Meta app setup for WhatsApp and Instagram

Compare the live dashboard with this page when labels differ or this stamp is over six months old; trust the live console and report the drift.

## Contents

- One app for both Platforms
- WhatsApp: steps
- Instagram: choose the setup
- Instagram: steps
- Known failures
- What each step proves

## One app for both Platforms

One Meta app serves both Platforms: Wappa authenticates every webhook POST with one `META_APP_SECRET`, and `META_WEBHOOK_VERIFY_TOKEN` answers both GET challenges. Each Platform has its own callback: `/webhook/inboxes/whatsapp` and `/webhook/inboxes/instagram`. Webhook callbacks are per app, not per account: every subscribed WABA or Instagram account delivers to the same URL, so check what is subscribed before changing it. Run in explicit Inbox routing (`SYSTEM_INBOX_ROUTING_MODE=explicit` plus `SYSTEM_TOKEN_ENC_KEY`) with your `IInboxDirectorySource`; Instagram works only there. Webhooks never register an account: each connected account needs an active record in your Directory Source (`wappa-host-integration`). For customers connecting their own accounts, see `connecting-accounts.md`; the steps below are the one-time app setup and the manual path for your own accounts.

## WhatsApp: steps

Meta's dashboard: the app → **Use cases** → **Connect on WhatsApp** → **Customize**.

1. **Pick a number.** *Step 1. Try it out* gives a test number on a test WABA. It can message only up to five allow-listed phones, and doesn't support Coexistence. A real number is added in *Step 2. Production setup* (verify by SMS, then register with a two-step PIN).
2. **Collect the IDs.** The Phone number ID becomes the Inbox (`InboxRef.whatsapp(phone_number_id)`); the WhatsApp Business Account ID (labelled **Messaging account ID**) is the Platform Account (`PlatformAccountRef.whatsapp(waba_id)`). For a lasting token, create a System User in Business Settings with the app and the WABA assigned, and generate a token with `business_management`, `whatsapp_business_messaging` and `whatsapp_business_management`. The Step 1 token expires after 24 hours. Store it only through your Directory Source; in explicit mode Wappa refuses the legacy `META_WHATSAPP_ACCESS_TOKEN`, `META_WHATSAPP_PHONE_NUMBER_ID` and `META_WHATSAPP_BUSINESS_ACCOUNT_ID` variables.
3. **Configure the webhook** (app level, *Step 2*): Callback URL `https://<host>/webhook/inboxes/whatsapp`, the same verify token. Meta calls the URL while saving, so the server and tunnel must be up. Fields: `messages` is required. Coexistence numbers add `smb_message_echoes`, `history` and `smb_app_state_sync`. Optional fields: `account_update`, `calls`, `message_template_status_update`, `message_template_quality_update`, `phone_number_quality_update`, `security`.
4. **Subscribe the WABA to the app** (account level): `POST https://graph.facebook.com/v26.0/<WABA_ID>/subscribed_apps` with a token that manages the WABA. The app-level callback alone delivers nothing, and a test WABA is not subscribed by default. `WhatsAppConnector.activate` does this for connected accounts.
5. **Self-service (Embedded Signup)**, only to onboard other businesses' numbers: *Become Tech Provider*, business verification, Advanced Access for both WhatsApp permissions, then **Embedded Signup Builder** → a Facebook Login for Business configuration (System User token, WhatsApp accounts) whose **Configuration ID** is your `config_id`.
6. **Smoke test.** Send a message from an allow-listed phone. The log shows the Inbox resolved, and the reply goes out.

## Instagram: choose the setup

Use **Instagram API with Unified Login** ("API setup with Unified login" under the use case **Manage messaging & content on Instagram**). It needs a business-portfolio-owned app with Facebook Login for Business. Its token is a Business Integration System User access token on `graph.facebook.com`; Instagram Login tokens (`graph.instagram.com`) are a different setup and are not interchangeable. Facebook Page Messenger is another Platform entirely.

## Instagram: steps

1. In the Meta app (it may already have WhatsApp), add the use case **Manage messaging & content on Instagram** and open **API setup with Unified login**.
2. Create or select a login configuration (Facebook Login for Business, Instagram-compatible). Record its `config_id` (not a secret). Request only what the app needs: `instagram_basic` + `instagram_manage_messages` for DMs, `instagram_manage_comments` for comments/mentions/controls; publishing/insights scopes only for extensions.
3. Register the app's OAuth redirect URI (for example `https://<host>/connect/instagram/callback`). It is not the webhook URL.
4. Controlled testing: invite the professional account as an **Instagram Tester** and accept the invite in Instagram. Then generate a token from the selected configuration.
5. Run the app (`uv run wappa dev app/main.py --port 8000`) behind HTTPS (for example `ngrok http 8000`).
6. **Configure webhooks**: Callback URL `https://<host>/webhook/inboxes/instagram`, Verify token = `META_WEBHOOK_VERIFY_TOKEN`, **Verify and save**. Tick the app-level fields: `messages`, `messaging_postbacks`, `messaging_seen`, `messaging_referral`, `comments`, `live_comments`, `mentions` (and `message_edit` if listed).
7. Subscribe each professional account: `POST https://graph.facebook.com/v26.0/<IG_ACCOUNT_ID>/subscribed_apps?subscribed_fields=...` with its token, or `InstagramSubscriptions.subscribe(...)` from `wappa.connections.instagram`. Read back with `subscribed_fields(...)`.
8. Comment and mention webhooks need the app in **Live** mode and Advanced Access for comments. Private accounts emit no comment/mention events.

## Known failures

| Symptom | Fix |
| --- | --- |
| WhatsApp reply fails `131030` on the test number | The recipient isn't on the Step 1 allow-list. Add the phone and confirm Meta's code. |
| WhatsApp webhooks never arrive | The WABA isn't subscribed to the app (`GET /<WABA_ID>/subscribed_apps`), or `messages` isn't ticked. |
| Startup fails with `InboxConfigurationError` | `META_WHATSAPP_*` variables are set in explicit mode. Remove them; credentials come from the Directory Source. |
| Startup reports a renamed environment variable | Remove the retired key, even if empty, and use the replacement named in the error; see the upgrade checklist in `wappa-host-integration`. |
| "Select a configuration in Step 1 before generating an access token" | Create/select the configuration first, then generate the token. |
| GET verify 403 | Dashboard verify token differs from `META_WEBHOOK_VERIFY_TOKEN`; restart after editing `.env`. |
| POST 401 | Wrong `META_APP_SECRET` (Unified Login signs with the Meta app secret). |
| POST 400 "not found" | The account has no active record in your Directory Source. Webhooks never auto-register accounts. |
| DMs arrive, comments never | App not Live, missing Advanced Access, account not subscribed to `comments`, or a private account. |
| `message_edit` subscription rejected | Absent from the Unified Login field table; `subscribe()` reports it per field. Treat edits as unavailable. |

## What each step proves

GET 200 proves connectivity and the verify token only. App-level field selection and account subscription are separate. A provider 200 on a send is acceptance, not delivery; echo and `read` events, and what the recipient sees, are separate evidence.
