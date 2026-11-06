---
checked_on: 2026-11-06
checked_against:
  - https://developers.facebook.com/docs/graph-api/overview/rate-limiting/
  - https://developers.facebook.com/docs/messenger-platform/overview/rate-limiting
  - https://developers.facebook.com/docs/whatsapp/cloud-api/overview/
  - https://developers.facebook.com/docs/whatsapp/throughput/
  - https://developers.facebook.com/docs/whatsapp/messaging-limits/
  - https://developers.facebook.com/docs/whatsapp/cloud-api/support/error-codes/
---

# Rate limits: Instagram and WhatsApp

What Meta caps, what each error code means, what we saw live, and what Wappa does about it today. The skills teach the Host-facing part (see the [skills PRD](../developer-experience/261103-mid-instagram-app-skills-and-setup.md), item 14). Numbers come from Meta's pages on the date in the header; when one is about six months old, re-check the live page before relying on it.

## Live evidence (Gate A, 2026-11-06)

The Instagram format matrix stopped at 12:30:57 with HTTP 403 `(#4) Application request limit reached` on every Instagram call, a plain text reply included. The `x-app-usage` header read only `call_count: 41`, yet the Graph log showed about 112 Instagram calls since 12:00 plus the comment tests before: about 200 calls in the hour from an app with one daily user (the test account). That matches the Platform formula below. Each format file costs about 4 calls (label text, link send, upload, send by attachment ID), a burst no real conversation produces.

Lessons:

- The Instagram "rejections" of MOV, 3GP, WebM and MKV video links after 12:30:57 were the rate limit, not format verdicts; the rerun decides them.
- A blocked call still counts, so retrying while limited extends the block. Stop sending until the window rolls (about an hour).
- WhatsApp kept working: its limits are per phone number and per portfolio, not the app's Instagram budget.

## Instagram

| Limit | Value | Scope | Error |
| --- | --- | --- | --- |
| Platform rate limit (app-level) | 200 calls per hour × the app's daily users (weekly or monthly users for apps with little daily use) | per app token | `4` (app), `17` (user) |
| Business Use Case (BUC) | 4,800 calls per 24 h × impressions of the professional account's content | per professional account | `80002` |
| Send API: text, links, reactions, stickers | 100 calls per second | per professional account | rate-limit code (`613/2534040` seen in our error table) |
| Send API: audio, video | 10 calls per second | per professional account | same |
| Private Replies on posts and reels | 750 calls per hour | per professional account | same |
| Private Replies on Live comments | 100 calls per second | per professional account | same |
| Conversations API (history reads) | 2 calls per second | per professional account | same |

Headers: `x-app-usage` (percent of the Platform limit: `call_count`, `total_cputime`, `total_time`) and `X-Business-Use-Case-Usage` (`call_count`, `total_cputime`, `total_time`, `type: instagram`, and `estimated_time_to_regain_access` in minutes).

Open verification: Meta does not state that people who DM the business count as the app's "users" for the Platform formula. Today's numbers fit the formula with one user, so a production app with many conversing users should have a proportionally larger budget, but confirm it on a production account by reading `x-app-usage` under real traffic before promising throughput to a Host. Also note that a third-party report lists code `4` with subcode `2207051` as an anti-spam block rather than a quota; check the subcode before retrying.

## WhatsApp (Cloud API)

| Limit | Value | Scope | Error |
| --- | --- | --- | --- |
| Throughput | 80 messages per second by default; automatic upgrade to 1,000 mps (20 mps for a number shared with the WhatsApp Business app) | per business phone number | `130429` "Rate limit hit"; `131057` during the upgrade (up to 1 minute) |
| Throughput upgrade criteria | unlimited messaging limit, 100K+ unique users messaged outside service windows in 24 h, quality YELLOW or better | per phone number | — |
| Pair rate limit | 1 message every 6 s to the same user (about 600 per hour); bursts up to 45 in 6 s, paid back from later quota | per sender and recipient pair | `131056` (other recipients unaffected) |
| Messaging limit | unique users messaged **outside** a customer service window per moving 24 h: 250 for a new portfolio, 2,000 after a scaling path (business verification, or 2,000 delivered high-quality messages in 30 days), then 10K, 100K, unlimited (automatic within 6 h when quality is high and half the limit was used in 7 days) | per business portfolio, shared by all its numbers | `131048` (restricted for spam or quality); `131064` (template misclassification enforcement) |
| Management API (WABA, phone numbers, templates, subscribed apps, assigned users) | 200 requests per hour per app per WABA; 5,000 per hour once the WABA has a registered number | per app and WABA | `80007` (WABA limit), `4` (app limit) |
| Registration | too many register/deregister attempts | per phone number | `133016` |

Read the limit with the `whatsapp_business_manager_messaging_limit` field (`messaging_limit_tier` is deprecated). Meta's guidance for the pair limit is exponential backoff: retry after 4^X seconds, X from 0, plus 1 per failure. For media at high throughput Meta recommends uploading once and sending by Media ID rather than having Meta fetch a URL on every send.

Conversation replies inside the 24-hour customer service window do not count toward the messaging limit; only messages outside it (Templates, in practice) do.

## What Wappa does today

- Instagram: `graph_request` classifies `4` as "application rate limit reached" and `613/2534040` as "rate limit reached", returns `REJECTED` with the code, and (since 2e5fd84) logs Meta's error fields. It does not read `x-app-usage` or `X-Business-Use-Case-Usage`.
- WhatsApp: the status-webhook error model exposes `is_rate_limit_error()` for `130429`; `131056` is listed among non-address rejections, so the BSUID fallback does not retry on it. Send results carry Meta's code; no usage header is read.
- Neither adapter paces sends, retries rate-limited calls, or reports a retry time. `indeterminate` sends are never retried automatically, and that stays.

## Gaps (candidate backlog draft)

1. A distinct rate-limited outcome (or `error_code` family) on `MessageResult` and operation results, with `retry_after` taken from `estimated_time_to_regain_access` or Meta's backoff rule, so a Host can tell "slow down" from "rejected".
2. Usage telemetry: log a warning when `x-app-usage` or `X-Business-Use-Case-Usage` crosses a threshold (for example 80 %), per Inbox.
3. Optional outbound pacing per Inbox in the send pipeline: Instagram 100/s text and 10/s media, WhatsApp throughput and the per-recipient pair limit, opt-in and Host-configurable.
4. The Crons domain (fire with a delay) is the natural home for a Host's retry of a rate-limited send.

## What the skills teach

- Treat a rate-limit code as "wait", not "fix the request": stop that kind of send for the Inbox (or that recipient, for `131056`), retry later, never in a tight loop.
- Instagram: bulk media is the tight path (10/s); private replies on posts cap at 750/h per account; history reads cap at 2/s, so do not read history on every message.
- WhatsApp: one recipient gets about one message per 6 s sustained, so batch a multi-part answer instead of firing many sends; Templates outside the window are bounded by the portfolio's messaging limit tier.
- Development apps have tiny budgets (one test user ≈ 200 Instagram calls per hour): run load-style tests in short families with pauses.
