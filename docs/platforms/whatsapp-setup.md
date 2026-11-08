# WhatsApp setup for the conversations example

Date: 2026-11-05. This is a living walkthrough for connecting a WhatsApp number to the same Meta app that already serves Instagram (`Wappa | CRM`, app `955553977072789`, business portfolio **Mimeia** `795750330207550`). It is the WhatsApp counterpart of the [Instagram setup](instagram-setup.md) and feeds the parity checks P-01..P-10 in the [live test plan](../verification/261103-instagram-conversations-live-tests.md).

There are two ways to get a WhatsApp Inbox into Wappa:

| Path | Who connects the number | Where the credential comes from | Wappa surface |
| --- | --- | --- | --- |
| **A. Manual** (operator, your own WABA) | You, in the Meta dashboard | Dashboard token or System User token, pasted into `.env` | `WA_PHONE_ID` / `WA_BID` / `WA_ACCESS_TOKEN` seed an encrypted Inbox record |
| **B. Embedded Signup** (self-service, client's WABA) | The number's owner, in a Meta popup or redirect | Code exchange for a Business Integration System User token | `wappa.connections.WhatsAppConnector` + the example's `/connect/whatsapp/*` routes |

Both paths end in the same place: an encrypted `InboxCredentialRecord` in the Host's Inbox Directory, an app subscription on the WABA, and webhooks arriving at `/webhook/inboxes/whatsapp`.

Never paste tokens, app secrets, verify-token values or authorization codes into this document or into chat.

## The dashboard you will see (2026 layout)

Meta replaced the old "WhatsApp → API Setup / Configuration" pages with a use case. Open the app → **Use cases** → **Connect on WhatsApp** → **Customize**. The sidebar has:

| Section | Item | Used for |
| --- | --- | --- |
| Overview | | Use-case summary |
| Basic setup | **Step 1. Try it out** | Test number, its Phone number ID, WABA ID, temporary token, the "To" allow-list, test send (former *API Setup*) |
| | **Step 2. Production setup** | Add a real number, webhook Callback URL and Verify token, field subscriptions (former *Configuration*) |
| | **Step 3. Business verification** | Business portfolio verification (needed for higher limits and for Path B with external clients) |
| | Next steps | Links only |
| Become a Partner | **Become Tech Provider** | Required before onboarding other businesses' WABAs (Path B) |
| | Partner Tools | Partner-level settings |
| | **Embedded Signup Builder** | Creates the Facebook Login for Business configuration (`config_id`) and shows the sample code (Path B) |
| | Partner Solutions / Migrate customers | Not used here |
| Other tools | Tools / Permissions and features / Resources | Permission status (`whatsapp_business_messaging`, `whatsapp_business_management`) |

Labels are taken from the user's screenshot of 2026-11-05. Inner pages of Step 2, Partner Tools and Embedded Signup Builder were not inspected yet; record what they show when you reach them.

## Shared prerequisites (both paths)

1. **One Meta app for both Platforms.** Wappa authenticates every POST webhook with one `META_APP_SECRET`. The WhatsApp number must therefore send its events to the same app as Instagram. A second app would need its own secret, which the example does not support.
2. **Webhook callback is per app, not per number.** Every WABA subscribed to the app delivers to the same callback URL. Changing it redirects every subscribed number. Check which WABAs are subscribed before changing it (the WhatsApp Business MCP's `whatsapp_biz_onboarding_status` lists them).
3. **The example runs in explicit Inbox Routing mode** with a JSON Inbox Directory (`SYSTEM_TOKEN_ENC_KEY` must stay stable).
4. **App published** (Live) so production numbers deliver real webhooks. `Wappa | CRM` is published.

## Path A — manual registration (operator-owned WABA)

### A1. Pick the number

- **Test number (fastest):** *Step 1. Try it out*. Meta gives every app a public test number on a test WABA. It can only message recipients on its **"To" allow-list** (up to five), and it does **not** support Coexistence, so P-10 (Business-app echo) cannot be tested on it. The WhatsApp Business MCP deliberately hides test numbers and cannot send from them.
- **Real number:** *Step 2. Production setup* → add phone number → verify by SMS/voice → register (two-step PIN). The MCP can do this flow: `whatsapp_biz_add_phone_number` → `whatsapp_biz_send_verification_code` → `whatsapp_biz_verify_phone_number` → `whatsapp_biz_register_phone_number`. A Coexistence number (already on the WhatsApp Business app) is connected through Embedded Signup instead (Path B), not added here.

### A2. Collect the three values

From the same page as the number:

| `.env` key | Dashboard label | Notes |
| --- | --- | --- |
| `WA_PHONE_ID` | Phone number ID | Becomes `inbox_id` (`InboxRef.whatsapp(phone_number_id)`). Not the display phone number. |
| `WA_BID` | WhatsApp Business Account ID — the 2026 dashboard labels it **Messaging account ID** | The Platform Account (`PlatformAccountRef.whatsapp(waba_id)`). Must be numeric. Verified 2026-11-05: the Messaging account ID of the test account answers `GET /{id}/phone_numbers` with the test number, so it is the WABA ID Wappa needs. |
| `WA_ACCESS_TOKEN` | Temporary access token (Step 1) **or** a System User token | The temporary token expires after 24 h; good enough for a live test session. For anything longer, generate a System User token (below). |

**System User token (permanent).** Business Settings → System Users (the MCP's `whatsapp_biz_system_user_token` returns the deep link) → choose or create a system user → assign the app (*Manage app*) and the WABA (*Manage WhatsApp Business accounts*) with full control → **Generate token** with `business_management`, `whatsapp_business_messaging`, `whatsapp_business_management`. It is shown once; paste it straight into `.env`.

Put the three values in `wappa_examples/instagram_conversations_example/.env` as `WA_*`. Do **not** use Wappa's legacy `WP_PHONE_ID` / `WP_BID` / `WP_ACCESS_TOKEN` names here: the example runs in explicit Inbox routing, and Wappa refuses to start if those legacy variables are present (`InboxConfigurationError`, observed 2026-11-05). `WP_*` are only for legacy single-Inbox apps. All three must be set together or the example refuses to start. On startup `_bootstrap` encrypts them into the Inbox Directory (`records/`), the same way `IG_ACCOUNT_ID` / `IG_ACCESS_TOKEN` seed Instagram.

### A3. Configure the webhook (app level)

*Step 2. Production setup* → Webhook, or the MCP's `whatsapp_biz_configure_webhooks`:

| Field | Value |
| --- | --- |
| Callback URL | `https://<tunnel-or-host>/webhook/inboxes/whatsapp` |
| Verify token | Same value as `WP_WEBHOOK_VERIFY_TOKEN` (shared with Instagram) |
| Fields | `messages` (required). Coexistence numbers add `smb_message_echoes`, `history`, `smb_app_state_sync`. Optional: `account_update`, `message_template_status_update`, `message_template_quality_update`, `phone_number_quality_update`, `security`, `calls`. |

Meta verifies the URL while saving, so the server and tunnel must be up. Check it first:

```bash
curl -s "https://<tunnel>/webhook/inboxes/whatsapp?hub.mode=subscribe&hub.verify_token=$WP_WEBHOOK_VERIFY_TOKEN&hub.challenge=4242"
# → 4242
```

With the MCP, passing `fields` **replaces** the whole field list; read the current list from `whatsapp_biz_onboarding_status` first and include it.

Wappa routes each field to one lane (ADR-0025): `messages` → message/status/update lanes; `smb_message_echoes` → `OutboundEchoWebhook` (origin `BUSINESS_APP`); `history` → `HistorySyncWebhook`; `smb_app_state_sync` → `SystemWebhook` with `ContactSync`; `account_update` offboard/reconnect → `InboxConnectionWebhook`.

### A4. Subscribe the WABA to the app (account level)

The app-level callback alone delivers nothing; each WABA must subscribe the app: `POST /{waba_id}/subscribed_apps` with a token that manages the WABA, or the MCP's `whatsapp_biz_subscribe_webhook`. **The test account is NOT subscribed to your app by default.** On 2026-11-05 its `subscribed_apps` listed only Meta's `WA DevX Webhook Events 1P App` (the dashboard's built-in webhook viewer). Subscribe yours with the Step 1 token, then list again to confirm:

```bash
curl -s -X POST "https://graph.facebook.com/v26.0/$WA_BID/subscribed_apps" -H "Authorization: Bearer $WA_ACCESS_TOKEN"   # {"success":true}
curl -s "https://graph.facebook.com/v26.0/$WA_BID/subscribed_apps" -H "Authorization: Bearer $WA_ACCESS_TOKEN"
```

### A5. Allow-list, restart, smoke test

1. Test number only: add your personal phone to the **To** list in *Step 1. Try it out* and confirm the code Meta sends.
2. Restart the example server so it seeds the WhatsApp Inbox.
3. From your phone send `/help` to the number. The log should show the inbound webhook resolved to `InboxRef(whatsapp, <phone_number_id>)` and the help reply sent.
4. Run P-01..P-09 from the live test plan with the same commands used on Instagram.

### Observed 2026-11-05 (Path A, test number)

Done through the WhatsApp Business MCP on business **Mimeia**, app `Wappa | CRM`:

- App-level callback set to the ngrok tunnel `/webhook/inboxes/whatsapp`; Meta's verification passed while saving.
- Fields replaced with 13: the previous 11 (`messages`, `message_template_status_update`, `smb_message_echoes`, `account_alerts`, `account_review_update`, `account_update`, `calls`, `message_template_quality_update`, `phone_number_name_update`, `phone_number_quality_update`, `security`) plus `history` and `smb_app_state_sync`.
- The demo WABA **BigView** is subscribed to this app, so its events now reach the tunnel too (accepted by the user: demo traffic).
- Test number `+1 555-188-9071` (`phone_number_id` 1014417365082534) on *Test WhatsApp Business Account* (Messaging account ID 1831186907601026). `.env` values set; Step 1 token is a USER token with `whatsapp_business_management` + `whatsapp_business_messaging`, valid 24 h.
- `POST /{waba}/subscribed_apps` returned success; the account now lists `Wappa | CRM` next to Meta's viewer app.
- First inbound `/help` reached Wappa and resolved the Inbox; the reply to the BSUID was rejected with `131030` (test allow-lists hold phones; the webhook also carried the allowed `wa_id`). Fixed in Wappa by ADR-0022: replies carry every Delivery Address and WhatsApp sends to the phone first, falling back on address rejections only.
- Pending: `/help` round trip after the fix, then P-01..P-09.

## Path B — Embedded Signup (self-service, no `.env`)

Use this when the number's owner connects their own WABA (including Coexistence numbers already on the WhatsApp Business app). Nobody copies IDs or tokens; Wappa discovers them.

### B1. One-time app setup

1. **Become Tech Provider** (*Become a Partner*). Needed to onboard WABAs owned by other business portfolios. Your own portfolio's WABAs can be tested before that.
2. **Business verification** (*Step 3*) for the portfolio that owns the app.
3. **Advanced access** for `whatsapp_business_messaging` and `whatsapp_business_management` (*Other tools → Permissions and features*) before onboarding external clients.
4. **Embedded Signup Builder** → create a *Facebook Login for Business* configuration for WhatsApp Embedded Signup. Token type: System User access token. Assets: WhatsApp accounts. Permissions: `whatsapp_business_messaging`, `whatsapp_business_management` (add `business_management` only if the Host needs it). Copy the **Configuration ID**.
5. **Redirect URI.** In the Facebook Login for Business settings, add `https://<host>/connect/whatsapp/callback` to *Valid OAuth Redirect URIs*. Must match exactly, including the tunnel host.
6. Webhook callback and fields as in A3 (once per app; already done above).

### B2. Example configuration

In the example `.env` (no `WP_*` needed for this path):

| Key | Value |
| --- | --- |
| `META_APP_ID` | `955553977072789` |
| `WA_LOGIN_CONFIG_ID` | The Embedded Signup configuration ID from B1.4 |
| `PUBLIC_BASE_URL` | The public HTTPS base, e.g. the ngrok URL |
| `CONNECT_OPERATOR_TOKEN` | A random secret that guards the operator routes |
| `META_APP_SECRET`, `SYSTEM_TOKEN_ENC_KEY` | Already set for Instagram |

### B3. What happens when someone connects

1. Operator opens `https://<host>/connect/whatsapp/start?token=<CONNECT_OPERATOR_TOKEN>`. The route binds a one-use OAuth `state` to an HttpOnly cookie and redirects to Meta's Business Login dialog with `config_id` and `extras={"sessionInfoVersion":"3"}`.
2. The owner logs in, picks or creates the business portfolio, picks or creates the WABA and phone number (or chooses *connect existing WhatsApp Business app* for Coexistence), and approves.
3. Meta redirects to `/connect/whatsapp/callback?code&state`. `WhatsAppConnector.complete` validates the state, exchanges the code for a Business Integration System User token, reads `/debug_token` to find the shared WABA IDs (from `granular_scopes` → `whatsapp_business_management.target_ids`) and checks that both required scopes were granted.
4. For each WABA it lists `GET /{waba}/phone_numbers`; each number becomes one discovered Inbox (`inbox_id = phone_number_id`, Platform Account = WABA).
5. For each ready Inbox, `activate` calls `POST /{waba}/subscribed_apps` and builds the encrypted record; the Host commits it and refreshes the directory. The page lists the connected numbers and `webhooks=True/False`. No token is ever shown.
6. Check `https://<host>/connect/accounts?token=<CONNECT_OPERATOR_TOKEN>`: the new `whatsapp:<phone_number_id>` Inbox should be `active: true`.
7. Send `/help` from a phone to the connected number.

### B4. Boundaries and known gaps

- Wappa's connector does **not** call `/{phone_number_id}/register`. Coexistence numbers and numbers registered inside the Embedded Signup flow are already registered; a brand-new number that comes back unregistered needs a register step the Host must add (two-step PIN).
- Wappa's connector exchanges the code **without** `redirect_uri` only when configured with `MetaLoginConfig(redirect_uri=None)` (JS SDK popup flow). The example uses the redirect flow, so the same `redirect_uri` is sent on exchange. A Host that embeds the JS SDK popup (`FB.login` with `config_id`, `response_type: "code"`, `override_default_response_type: true`) should use `redirect_uri=None` and post the `code` to its backend; the popup's `WA_EMBEDDED_SIGNUP` message event also carries `phone_number_id` and `waba_id` directly.
- **Disconnect** is per WABA (`DELETE /{waba}/subscribed_apps`): it stops every number in that WABA, so a Host calls it only when no other active Inbox shares the WABA.
- **Offboarding** from the owner's side (Coexistence `account_update` → `ACCOUNT_OFFBOARDED`/`RECONNECTED`) arrives as `InboxConnectionWebhook`; the example does not handle that lane yet (only logged).
- Gate B for WhatsApp is **optional** in the PRD; Instagram's connect flow is the required Gate B run. This path is tested only against faked Meta responses so far.

## Remaining evidence to collect

- Test-number `/help` round trip and P-01..P-09 (Path A).
- Inner pages of *Step 2. Production setup* and *Embedded Signup Builder*: field names, configuration ID, redirect settings.
- One Embedded Signup completion on an own-portfolio WABA (Path B), with `/connect/accounts` showing the Inbox active and a `/help` round trip.
- A Coexistence number for P-10 on WhatsApp (Business-app echo → `OutboundEchoWebhook` origin `BUSINESS_APP`) and a `history` sync.

References: [Get started](https://developers.facebook.com/documentation/business-messaging/whatsapp/get-started), [Webhooks](https://developers.facebook.com/documentation/business-messaging/whatsapp/webhooks/create-webhook-endpoint), [Embedded Signup](https://developers.facebook.com/documentation/business-messaging/whatsapp/embedded-signup/overview), [Coexistence onboarding](https://developers.facebook.com/documentation/business-messaging/whatsapp/embedded-signup/onboarding-business-app-users). Dashboard labels come from the user's screenshot; pages not yet opened are marked pending.
