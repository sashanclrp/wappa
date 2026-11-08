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

Source reference for Meta limits, error codes and the live development-app blocks of 2026-11-06. The shipped [wappa-apps skill](../../wappa/cli/skills/wappa-apps/SKILL.md) derives its Host rate-limit guidance from these observations. Runtime outcomes and retry behavior are authoritative in the [public contract](../public-contract.md#meta-rate-limits) and [ADR-0029](../adr/0029-meta-graph-transport.md). Meta numbers retain the original check date; no external recheck was performed during consolidation.

## Live evidence (2026-11-06)

The Instagram format matrix stopped at 12:30:57 with HTTP 403 `(#4) Application request limit reached` on every Instagram call, a plain text reply included. The `x-app-usage` header read only `call_count: 41`, yet the Graph log showed about 112 Instagram calls since 12:00 plus the comment tests before: about 200 calls in the hour from an app with one daily user, the test account. This initially appeared consistent with the Platform formula below; the second block contradicted that estimate. Each format file costs about 4 calls (label text, link send, upload, send by attachment ID), a burst unlike the conversational checks in this record.

Lessons:

- The Instagram "rejections" of MOV, 3GP, WebM and MKV video links after 12:30:57 were the rate limit, not format verdicts; the rerun in [media results](media-formats.md) supplies the format verdicts.
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

Unverified since 2026-11-06: Meta's definition of an app "user" for this formula and its production relationship to DM traffic. The second block below contradicts scaling the budget by conversing Users; do not promise that throughput. An unsourced third-party report in the original research described `4/2207051` as an anti-spam block; that classification is unverified since 2026-11-06. Check actual code/subcode and current Meta guidance before choosing a retry policy.

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

Instagram calls per 10 minutes before the block (lab log): 12:30 46, 12:40-13:20 2, 13:20 20, 13:30 17, 13:40 47. That is about 85-130 calls in the rolling hour, under the 200 one daily user should give, so the documented formula does not describe this development app, and a person who DMs the business does not add budget the same day. For production, assume the Instagram app budget does not grow with conversations until `x-app-usage` under real traffic proves otherwise.


After the limit cleared at about 13:29, the image family (16 files) and half the video family used the budget again by 13:45:26. A second Instagram account messaging the same business got `(#4)` on its very first call at 13:46:53: code 4 counts the whole Meta app, not each conversing user or account. The `x-app-usage` header on the last accepted call (13:44:56) read `call_count: 23`, so the header understates the Instagram budget and cannot be the only warning signal. Meta also answered MOV and WebM uploads with HTTP 500 instead of a rejection.

## Runtime qualifications

The [public contract](../public-contract.md#meta-rate-limits) specifies the current `RateLimitGovernor` behavior: short-limit retries, long blocks, pacing, usage warnings, `rate_limited` / `retry_after` and HTTP 429. The governor is process-local in `MetaGraphClient`; several workers do not share block state. No Host delayed retry is scheduled automatically. Usage warnings do not proactively slow traffic; the Instagram observations above show why headers alone cannot establish available budget. Indeterminate sends and mutations are never retried.
