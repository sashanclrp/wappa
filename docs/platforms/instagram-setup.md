---
checked_on: 2026-11-03
checked_against: supplied Meta dashboard screenshots and Unified Login setup pages; account connection results dated separately
---

# Instagram setup observations

The shipped [Meta app setup guide](../../wappa/cli/skills/wappa-apps/references/meta-app-setup.md) owns the portable setup procedure; [connecting accounts](../../wappa/cli/skills/wappa-apps/references/connecting-accounts.md) owns Host connector usage. This file supplies the dashboard observations and failure evidence behind those guides. Dashboard labels were observed on 2026-11-03, without an external recheck during consolidation on 2026-11-08.

## Dashboard and login configuration

In an existing WhatsApp Meta app, **Add more use cases → Business messaging → Manage messaging & content on Instagram** adds Instagram. **Engage with customers on Messenger from Meta** is a separate Facebook Page use case.

The observed sidebar recommended **API setup with Unified login** and labelled Instagram Login legacy. The selected setup uses `graph.facebook.com` and a Business Integration System User Access Token, with a business portfolio prerequisite. Credentials and hosts from Instagram Login are not interchangeable.

| Configuration preview | Observed value |
| --- | --- |
| Login variation | General |
| Access token | System-user access token (SUAT) |
| Expiration | Never |
| Business assets | Instagram account required; ad account optional |
| Permissions displayed | `ads_management`, `ads_read`, `instagram_basic`, `instagram_manage_messages`, `instagram_manage_comments`, `instagram_content_publish` |

The user chose **Create new configuration → Create from template**; Step 1 became checked, with **Selected** and **Instagram Login Compatible** status. The preview does not establish that every permission is required or editable. Optional permission removal was not recorded. "Never" does not prevent revocation or loss of asset access.

The dashboard refused token generation with **Select a configuration in Step 1 before generating an access token**, despite a **Token generated** modal heading. Select the compatible configuration before using Step 2; the test-token shortcut does not bypass Step 1.

## Controlled test-token path

**Generate access tokens → Add account** invites a real professional account as **Instagram Tester**. The invite is accepted under Instagram web **Settings → Website permissions → Apps and websites → Tester Invites**, followed by Generate token and login. Meta synthetic test users are unsupported in this documented path. A general Tester role is different from Instagram Tester.

The initial selected redirect belonged to an existing WhatsApp connection page. This did not prove an Instagram authorization callback. A login redirect receives authorization returns; a webhook Callback URL receives GET challenges and POST notifications. Controlled dashboard-token testing and self-service onboarding are separate checks.

The November 3 echo example used optional `IG_ACCOUNT_ID` / `IG_ACCESS_TOKEN` settings to seed an encrypted record. They are example settings, not library environment variables. The empty Directory Source allowed GET verification before an account existed; account access and subscription were checked through `app.setup` and `app.setup --subscribe`. Library settings now use `META_WEBHOOK_VERIFY_TOKEN` and `META_WHATSAPP_*`; retired `WP_*` names in the historical test record describe that checkout only.

## Webhook configuration and delivery failures

The dashboard showed a separate **Configure webhooks** step with **Callback URL**, **Verify token**, and **Verify and save**. Wappa uses `/webhook/inboxes/instagram`, separately from WhatsApp. Separate URLs are Wappa's design choice, not a claim that Meta forbids URL reuse. All fields for this Instagram configuration share its callback.

GET verification proves reachability and verify-token matching. POST authentication uses the App Secret over exact bytes. App-level field selection and each account's `POST /{instagram-account-id}/subscribed_apps` are separate requirements. Use the configured Graph version and Unified Login credential for the latter; a stored encrypted record alone proves no notification readiness. The [Instagram reference](instagram.md#native-subscription-fields) owns the field inventory.

On 2026-11-05 the account subscription listed all eight fields, but the app selected only `messages,messaging_seen`. Button templates were accepted, yet taps delivered no webhook. Enabling the other app-level fields restored postbacks.

Another connected account received DMs in Instagram but no app notifications because **Settings → Messages and story replies → Message controls → Connected tools → Allow access to messages** was off. Development-mode accounts also require accepted tester access. Comment/mention checks require Live mode and Advanced Access for comments; the shipped guide records private-account restrictions.

## Evidence and limits

| Date | Observation | What it proves |
| --- | --- | --- |
| 2026-11-03, 11:06 America/Bogota | Meta GET returned HTTP 200 | Public callback and challenge matching |
| 2026-11-03 | Account access check and `messages,messaging_seen` subscription succeeded | Controlled account authorization and account subscription |
| 2026-11-03, 11:24 America/Bogota | Inbound text, accepted text send, business echo and READ observed | First live text exchange; [record](../verification/261103-instagram-simple-text-test.md) |
| 2026-11-05 | Unified Login connected multiple accounts, replay refused, cancellation preserved records, reconnect rotated versions | Self-service core flow; [ledger](../verification/261103-instagram-conversations-live-tests.md#gate-b-results-2026-11-05--closed-b-01-b-02-b-03-b-04-b-06-pass-b-05-b-07-not-applicable-to-unified-login-b-08-not-run) |
| 2026-11-08 | Creator connection passed by user report | Creator account connected; bootstrap requirement not separately established |

Unverified since 2026-11-03: configuration-dialog editability and the exact scope of a Creator Conversations API bootstrap prerequisite. Independent-customer App Review/Advanced Access and actual business-portfolio revocation remain outside the recorded live certification. Unified Login has no per-user deauthorize callback in Wappa; current revocation handling belongs to the connector guide and [ADR-0026](../adr/0026-inbox-connection.md).

Sources: [Unified Login](https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-unified-login), [authentication](https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-unified-login/authentication), [permissions](https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-unified-login/permissions), [get started](https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-unified-login/get-started), [webhook setup](https://developers.facebook.com/documentation/instagram-platform/webhooks/setup).
