---
checked_on: 2026-11-03
checked_against: Meta "Instagram API with Unified Login" (authentication, get-started), Instagram webhooks fields/examples, and a live dashboard walkthrough with Graph v26.0
revision: 1
---

# Meta app setup (Unified Login)

Compare the live dashboard with this page when labels differ or this stamp is over six months old; trust the live console and report the drift.

## Contents

- Choose the setup
- Steps
- Known failures
- What each step proves

## Choose the setup

Use **Instagram API with Unified Login** ("API setup with Unified login" under the use case **Manage messaging & content on Instagram**). It needs a business-portfolio-owned app with Facebook Login for Business. Its token is a Business Integration System User access token on `graph.facebook.com`; Instagram Login tokens (`graph.instagram.com`) are a different setup and are not interchangeable. Facebook Page Messenger is another Platform entirely.

## Steps

1. In the Meta app (it may already have WhatsApp), add the use case **Manage messaging & content on Instagram** and open **API setup with Unified login**.
2. Create or select a login configuration (Facebook Login for Business, Instagram-compatible). Record its `config_id` (not a secret). Request only what the app needs: `instagram_basic` + `instagram_manage_messages` for DMs, `instagram_manage_comments` for comments/mentions/controls; publishing/insights scopes only for extensions.
3. Register the app's OAuth redirect URI (for example `https://<host>/connect/instagram/callback`). It is not the webhook URL.
4. Controlled testing: invite the professional account as an **Instagram Tester** and accept the invite in Instagram. Then generate a token from the selected configuration.
5. Run the app (`uv run wappa dev app/main.py --port 8000`) behind HTTPS (for example `ngrok http 8000`).
6. **Configure webhooks**: Callback URL `https://<host>/webhook/inboxes/instagram`, Verify token = `WP_WEBHOOK_VERIFY_TOKEN`, **Verify and save**. Tick the app-level fields: `messages`, `messaging_postbacks`, `messaging_seen`, `messaging_referral`, `comments`, `live_comments`, `mentions` (and `message_edit` if listed).
7. Subscribe each professional account: `POST https://graph.facebook.com/v26.0/<IG_ACCOUNT_ID>/subscribed_apps?subscribed_fields=...` with its token, or `InstagramSubscriptions.subscribe(...)` from `wappa.connections.instagram`. Read back with `subscribed_fields(...)`.
8. Comment and mention webhooks need the app in **Live** mode and Advanced Access for comments. Private accounts emit no comment/mention events.

## Known failures

| Symptom | Fix |
| --- | --- |
| "Select a configuration in Step 1 before generating an access token" | Create/select the configuration first, then generate the token. |
| GET verify 403 | Dashboard verify token differs from `WP_WEBHOOK_VERIFY_TOKEN`; restart after editing `.env`. |
| POST 401 | Wrong `META_APP_SECRET` (Unified Login signs with the Meta app secret). |
| POST 400 "not found" | The account has no active record in your Directory Source. Webhooks never auto-register accounts. |
| DMs arrive, comments never | App not Live, missing Advanced Access, account not subscribed to `comments`, or a private account. |
| `message_edit` subscription rejected | Absent from the Unified Login field table; `subscribe()` reports it per field. Treat edits as unavailable. |

## What each step proves

GET 200 proves connectivity and the verify token only. App-level field selection and account subscription are separate. A provider 200 on a send is acceptance, not delivery; echo and `read` events, and what the recipient sees, are separate evidence.
