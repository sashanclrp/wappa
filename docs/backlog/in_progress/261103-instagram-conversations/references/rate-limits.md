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

## Second block (13:45) and what it adds

After the limit cleared at about 13:29, the image family (16 files) and half the video family used the budget again by 13:45:26. A second Instagram account messaging the same business got `(#4)` on its very first call at 13:46:53: code 4 counts the whole Meta app, not each conversing user or account. The `x-app-usage` header on the last accepted call (13:44:56) read `call_count: 23`, so the header understates the Instagram budget and cannot be the only warning signal. Meta also answered MOV and WebM uploads with HTTP 500 instead of a rejection.

## What Wappa does (since the rate-limit governor)

`wappa.resilience.rate_limits.RateLimitGovernor`, one per process, sits at each adapter's transport: `InstagramGraphClient.request` and `WhatsAppClient` (`post_request`, `get_request`, `delete_request`). Every Meta call goes through it, sends, uploads, comment actions and reads alike, and it decides by Meta's error code, never by HTTP status.

| Kind | Codes | Scope | What happens |
| --- | --- | --- | --- |
| Short | Instagram `613`; WhatsApp `130429`, `131057` | Inbox | sleep and retry inside the call (1 s, 4 s, 16 s), at most 3 retries and 30 s |
| Short | WhatsApp `131056` | Inbox + recipient | same, Meta's 4^X backoff; other recipients unaffected |
| Long | Instagram `4`; WhatsApp `4` | the app on that Platform | block every Inbox: `rate_limited` at once without calling Meta |
| Long | Instagram `17`, `32`, `80002`, `80006`; WhatsApp `80007`, `133016` | Inbox | block that Inbox the same way |

A long block lasts Meta's `estimated_time_to_regain_access` when the `X-Business-Use-Case-Usage` header gives it, else 300 s, doubling on each consecutive block up to an hour; the first accepted call clears the strikes. Retrying a rate limit is safe because Meta did not process the call (an uploaded file is rewound first); `indeterminate` (transport failure, 5xx) is still never retried. Calls are paced per Inbox: Instagram 10/s for audio and video and 100/s otherwise, WhatsApp 80/s. Both usage headers are read on every response and a value over 80 % logs a warning per Inbox, at most once a minute.

Hosts see `OperationOutcome.RATE_LIMITED` and `retry_after` (seconds) on every result type, and the HTTP API answers 429 with `Retry-After`. Waiting is `asyncio.sleep` in the task that sent: each webhook is its own task, so other Users keep being served while one waits. State is in process memory, so with several workers each keeps its own view; a Redis-backed governor is a follow-up if Hosts run many workers.

## Remaining gaps

1. Shared state across worker processes (Redis), so one worker's code 4 blocks the others.
2. A Host-side delayed retry of a `rate_limited` result: the Crons domain is its natural home.
3. Proactive slowing as usage nears 100 % (today the warning only logs), once production numbers show the headers are trustworthy for Instagram.
4. One `MetaGraphClient` for both Platforms: the governor is wired into two transports that duplicate the Graph call, error parsing and logging (architecture-hardening follow-up).

## What the skills teach

- Wappa already waits and retries short limits and blocks long ones; a Host sees `rate_limited` with `retry_after` only when the wait would be long. Treat it as "try later", not "fix the request", and never resend in a loop.
- Instagram: bulk media is the tight path (10/s); private replies on posts cap at 750/h per account; history reads cap at 2/s, so do not read history on every message.
- WhatsApp: one recipient gets about one message per 6 s sustained, so batch a multi-part answer instead of firing many sends; Templates outside the window are bounded by the portfolio's messaging limit tier.
- Development apps have tiny budgets (one test user ≈ 200 Instagram calls per hour): run load-style tests in short families with pauses.
