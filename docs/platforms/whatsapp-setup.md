---
checked_on: 2026-11-05
checked_against: supplied Meta dashboard screenshots and controlled test-number setup; Embedded Signup documentation
---

# WhatsApp setup observations

The shipped [Meta app setup guide](../../wappa/cli/skills/wappa-apps/references/meta-app-setup.md) owns manual setup and the [connector guide](../../wappa/cli/skills/wappa-apps/references/connecting-accounts.md) owns Embedded Signup usage. This file retains dashboard and lab observations behind those guides. [Instagram setup](instagram-setup.md) covers the other use case in the same Meta app; the [live ledger](../verification/261103-instagram-conversations-live-tests.md) records parity results.

## Dashboard labels observed on 2026-11-05

Open **Use cases → Connect on WhatsApp → Customize**. These use-case pages replaced the older API Setup / Configuration navigation in the observed dashboard.

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


Unverified since 2026-11-05: inner pages of Step 2, Partner Tools and Embedded Signup Builder were not inspected. The labels above come from screenshots, not proof of every inner dialog or external-customer approval.

## Manual test-number findings

- **Messaging account ID** was confirmed as the WABA ID by `GET /{id}/phone_numbers`, which returned the expected test number. **Phone number ID** identifies the Inbox; it is not the display phone number.
- The Step 1 token was a `USER` token with `whatsapp_business_management` and `whatsapp_business_messaging`, valid for 24 hours. The shipped guide explains System User tokens for longer use.
- A test number supports up to five allow-listed phones and no Coexistence. The WhatsApp Business MCP used in the session hid test numbers and could not send from them; direct account subscription with the Step 1 token succeeded.
- The test WABA initially listed only Meta's `WA DevX Webhook Events 1P App`. `POST /{waba}/subscribed_apps` added the Wappa app. App callback configuration alone did not subscribe the WABA.
- The app callback was set to `/webhook/inboxes/whatsapp` and Meta GET verification passed. The MCP's `fields` argument replaced the entire field list, so the previous selection had to be retained explicitly.
- The resulting 13-field selection was `messages`, `message_template_status_update`, `smb_message_echoes`, `account_alerts`, `account_review_update`, `account_update`, `calls`, `message_template_quality_update`, `phone_number_name_update`, `phone_number_quality_update`, `security`, `history`, `smb_app_state_sync`. Selection is not proof of built-in handling for every field; see [ADR-0023](../adr/0023-inbound-webhooks.md).
- Another demo WABA was already subscribed to the app, so its traffic also followed the changed callback. Inspect all subscribed accounts before changing an app-level callback.
- First `/help` intake resolved the Inbox, but a reply addressed to its BSUID failed `131030`: the test allow-list held the phone, and the webhook also carried the allowed `wa_id`. The resulting address-selection rule uses every known Delivery Address, phone first, with fallback only for address rejection. See [ADR-0022](../adr/0022-inbox-identity-and-directory.md). Later round trips and media/interactive parity passed on 2026-11-05 and 2026-11-06 in the live ledger.

The conversations lab's manual bootstrap uses `WA_PHONE_ID`, `WA_BID`, `WA_ACCESS_TOKEN` to seed encrypted records in its `records/` Directory Source, as `IG_ACCOUNT_ID` / `IG_ACCESS_TOKEN` do for Instagram. These are lab settings. Library explicit mode rejects the legacy single-Inbox `META_WHATSAPP_*` bundle; retired `WP_*` names in the original test notes describe the older checkout. `SYSTEM_TOKEN_ENC_KEY` must stay stable to read existing records.

## Embedded Signup boundaries

The lab exposes `/connect/whatsapp/start`, `/connect/whatsapp/callback` and `/connect/accounts`, guarded by its operator credential. `WA_LOGIN_CONFIG_ID` is its Embedded Signup configuration; `PUBLIC_BASE_URL` selects its public redirect host. These are Host routes and settings, not library HTTP endpoints. The connector guide owns the begin/complete/activate, persist-then-refresh and revocation sequence.

`WhatsAppConnector.complete` discovers WABA IDs through `debug_token` → `granular_scopes` → `whatsapp_business_management.target_ids`, then `GET /{waba}/phone_numbers`. Activation subscribes the WABA and returns an encrypted record for each ready Inbox.

- Wappa does not call `/{phone_number_id}/register`. Coexistence and numbers registered inside Embedded Signup already have registration; a brand-new unregistered number needs a Host registration step with its two-step PIN.
- A redirect flow includes the same `redirect_uri` in code exchange. A JavaScript SDK popup uses `MetaLoginConfig(redirect_uri=None)` and posts its code to the backend. `FB.login` uses `config_id`, `response_type: "code"`, `override_default_response_type: true`; the `WA_EMBEDDED_SIGNUP` message event also supplies `phone_number_id` and `waba_id`.
- `DELETE /{waba}/subscribed_apps` affects every number in that WABA. Disconnect only when no other active Inbox shares it.
- Coexistence offboard/reconnect signals use `process_inbox_connection`; the lab only logged that lane during the recorded run.

Unverified since 2026-11-05: a live WhatsApp Embedded Signup completion, Coexistence Business-app echo and `history` synchronization. The test number cannot establish those results. The recorded Embedded Signup path used fake Meta responses; Instagram's successful Unified Login checks do not certify it.

Sources: [Get started](https://developers.facebook.com/documentation/business-messaging/whatsapp/get-started), [webhooks](https://developers.facebook.com/documentation/business-messaging/whatsapp/webhooks/create-webhook-endpoint), [Embedded Signup](https://developers.facebook.com/documentation/business-messaging/whatsapp/embedded-signup/overview), [Coexistence onboarding](https://developers.facebook.com/documentation/business-messaging/whatsapp/embedded-signup/onboarding-business-app-users).
