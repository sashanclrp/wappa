# Live test plan: gates A, B and C

Runbook for the live checks. Record results in the matrix ([capability-matrix.md](../platforms/instagram-capability-matrix.md)) and below, keeping the same evidence rules as [simple-text-test.md](261103-instagram-simple-text-test.md): callback acknowledgement, provider acceptance, echo/read and what the recipient actually saw are different facts. Never paste tokens, codes or personal IDs.

## Current status (2026-11-08)

**Gate A passed (closed 2026-11-06)** after the hardening, on both Platforms: every command, the WhatsApp "not available" guard, the rate-limit governor live, and the full format matrix (every family by link and upload, rendering observed on the phone; results and the per-Platform "cannot process" lists in [`references/media-formats.md`](../platforms/media-formats.md)). See the 2026-11-06 rows in the Results log. Gate B passed, B-08 included (2026-11-08); independent-customer access and actual revocation remain limitations. Gate C passed (closed 2026-11-08) on Symphonai with Wappa 0.34.8, and A-11 and B-08 passed the same day (user-run; see the 2026-11-08 results). The deauthorize experiments below are historical; architecture hardening removed that unsupported route for Unified Login.

## 0. Prepare (once)

First, check each Instagram account under test: "Allow access to messages" must be on (Settings → Messages and story replies → Message controls → Connected tools), the account must be professional (Business or Creator), and while the app is in development mode the account must have an accepted tester role. Without these, Instagram delivers DMs to the inbox but to no app, and no webhook arrives.

```bash
cd ../wappa_examples/instagram_conversations_example   # from the wappa repo
uv sync
# .env was copied from simple_echo_example; set PUBLIC_BASE_URL to your tunnel
uv run wappa dev app/main.py --port 8000
ngrok http 8000
uv run python -m app.setup --subscribe   # core + comments + mentions, then message_edit separately
```

In Meta → Instagram → API setup with Unified login → Configure webhooks, tick the same fields (`messages`, `messaging_postbacks`, `messaging_seen`, `messaging_referral`, `message_edit`, `comments`, `live_comments`, `mentions`). App-level field selection and account subscription are separate steps. Comment and mention events need the app to be Live, with Advanced Access for comments.

Status on 2026-11-03: account access was verified and `--subscribe` was run. A read-back shows all eight fields subscribed: `messages, messaging_postbacks, messaging_seen, messaging_referral, comments, live_comments, mentions, message_edit`. That proves the subscription only. Delivery of each field still has to be observed live.

## Gate A: conversations

| ID | Step (DM the account from a tester) | Expect |
| --- | --- | --- |
| A-01 | `hello` | text echo + hint |
| A-02 | `/help` | quick replies; tap one → `process_message` once (no duplicate interaction) |
| A-03 | `/image`, `/audio`, `/video`, `/file` | each family arrives (sample assets via PUBLIC_BASE_URL) |
| A-04 | `/image-upload` | upload path accepted, or an explicit provider code is recorded (verifies `message_attachments` for IG IDs) |
| A-05 | send a photo, voice note, video and PDF | "Downloaded N bytes (mime)" + echo of the same media |
| A-06 | share a post/Reel; reply to a story; mention the account in a story | share/story types and IDs reported; post read when an ID is supplied |
| A-07 | `/buttons` (tap Ping), `/cta`, `/card`, `/carousel` (tap Choose) | each tap arrives in `process_message` with `get_interactive_selection()` (ADR-0025) |
| A-08 | `/read` | thread marked seen, then typing dots for about 3 s (`mark_as_read(typing=True)`) |
| A-09 | edit a sent message; unsend a message | `✏️ edited` / `deleted` logs (edit depends on A-00 field outcome) |
| A-10 | **Form Score:** `/form` → name → service (quick reply) → budget (button) → email (try an invalid one first) → confirm card | validation re-prompts, branch on "Other", submission recorded |
| A-11 | during the form: `/form` (resume), tap an old button (stale), `cancel`, restart; confirm twice | resume / stale / cancel / "already submitted" |
| A-12 | two testers run `/form` at the same time | no answer crosses Users (check the summaries) |
| A-13 | the same tester runs `/form` on a second connected account | separate state per Inbox |
| A-14 | comment `#reply` on a disposable post you own | public reply under the comment; our reply ignored (no loop) |
| A-15 | comment `#dm` → answer the DM → `hello` | private reply, then a normal DM follow-up works |
| A-16 | comment `#hidecycle`, `#delete`, `#lock` / `#unlock`, `#read` | controls return accepted; read logs comment, replies and media |
| A-17 | mention the account in a caption and in a comment | `📣 mention` with media/comment subject + read |
| A-18 | Live broadcast: comment, `#dm` during Live | Live source; public reply/hide expected to be refused by Meta (documented) |
| A-19 | `/post <media_id>`, `/comments <media_id>` | post/children/caption; paginated comments |

## Parity: one method, WhatsApp and Instagram (ADR-0025)

Run each command on both Platforms against the same server and code. Expect the same flow, with each Platform's native rendering. WhatsApp number setup (test number via `.env`, or Embedded Signup): [whatsapp-setup.md](../platforms/whatsapp-setup.md).

| ID | Command | WhatsApp renders | Instagram renders | Same handler result |
| --- | --- | --- | --- | --- |
| P-01 | `/form` (full run) | list for service, reply buttons for budget, image + buttons for confirm | quick replies, button template, the image as its own attachment then the button template | submission saved under the Inbox's own Redis keys |
| P-02 | `/quick` | list menu | quick replies | "You selected color:… via list_reply / quick_reply" |
| P-03 | `/buttons`, tap Ping | reply buttons | postback buttons | "You selected ping via button_reply" |
| P-04 | `/card`, `/carousel` (tap Choose) | image header + button; media carousel | the image as its own attachment then the button template; intro text + carousel | "You selected plan:…" |
| P-05 | `/cta` | URL button | `web_url` button | link opens; no webhook |
| P-06 | `/image` `/audio` `/video` `/file` `/image-upload` | media by URL; `/image-upload` = `IMediaLibrary.upload` to the Media API, then `send_image` by Media ID | media by URL; `/image-upload` = `IMediaLibrary.upload` to `message_attachments`, then `send_image` by attachment_id | accepted |
| P-07 | send a photo / voice note / PDF | `IMediaLibrary.download` by Media ID, echo by ID | `IMediaLibrary.download` by CDN URL, echo by URL | "Downloaded N bytes" + echo |
| P-08 | `/read` | blue ticks + typing | seen + typing | success=True |
| P-09 | `/post x`, `/comments x` | "not available on whatsapp" | post / comments read | capability-gated |
| P-10 | Owner replies by hand from the phone app (WhatsApp Business app / Instagram app) | `process_outbound_echo`, `origin=business_app`, typed text | same | one echo lane |
| P-11 | Bot sends `/help`; check logs | no `OutboundEchoWebhook` (Coexistence never echoes API sends) | echo dropped (`Dropped echo of Wappa's own send` debug log); record whether the raw echo carries `app_id` and whether its `mid` equals the send's `message_id` | fixed own-send filter |
| P-12 | React ❤️ to a bot message, then remove it | `InboundMessageWebhook(REACTION)` add + removal | same, `InstagramReactionMessage` | one reaction shape |
| P-13 | Edit a sent message (WhatsApp edit / Instagram edit) | `process_message_update` EDITED, typed text | same | one update lane |
| P-14 | Inbox connection lane (offline under Unified Login) | — | Not run live: Unified Login issues business-owned `SYSTEM_USER` tokens (no expiry), removing a person's integration revokes nothing and Meta sends no deauthorize. Wappa removed the Instagram deauthorize route and `deauthorization_event` on 2026-11-06 (architecture hardening H-28), so this lane has no Instagram emitter; WhatsApp `account_offboarded` keeps it covered. A callback would apply only to an Instagram Login grant, which the adapter does not support | one connection lane |

## WhatsApp inbound rerun (every interactive and webhook)

Added 2026-11-05 after a live `list_reply` without `description` was answered 400. Run against the test number after a server restart. For every row: no `Response 400`, no `ValidationError`, and the expected handler line. Record any `META_SCHEMA_DRIFT` line verbatim (field names only).

| ID | Do | Expect |
| --- | --- | --- |
| W-01 | `/quick`, tap a row (rows have no description) | `list_reply` → "You selected color:…" |
| W-02 | `/buttons`, tap Ping | `button_reply` → "You selected ping" |
| W-03 | `/form` full run, plus the "Other" branch and an invalid email | list → buttons → card buttons; re-prompt on bad email; submission in DB2 `whatsapp__<pnid>:df:form_submissions:…` |
| W-04 | `/card`, `/carousel`, tap a card button | `button_reply` with the card payload |
| W-05 | `/ask-location`, share a location | location message |
| W-06 | `/ask-contact`, share a contact; `/contact` | contacts message; `ContactCard` sent |
| W-07 | Send text, photo with caption, voice note, video, PDF, sticker | one `InboundMessageWebhook` per type; media download + echo |
| W-08 | Send a location and a contact unprompted | location / contacts message |
| W-09 | Reply (swipe) to a bot message; forward a message to the bot | `context.id` present; forwarded flag set |
| W-10 | React ❤️ to a bot message, then remove it | REACTION add, then removal |
| W-11 | Edit a sent text; delete one for everyone | `process_message_update` EDITED / REVOKED |
| W-12 | `/read` and any bot send | statuses sent → delivered → read, 200 on `pricing` |
| W-13 | Send something WhatsApp marks unsupported (a poll or event, if the client allows) | `UNSUPPORTED` with Meta's 131051 error, 200 |
| W-14 | Any other `field=` system event seen in the log (`account_update`, `user_preferences`…) | 200; typed event or `SystemWebhook(UNSUPPORTED_EVENT)` |

Not reachable from a test number: Coexistence echoes and history (P-10 WhatsApp), Flow replies (`nfm_reply`, covered by unit tests), calls.

### Templates through the capability (ADR-0025)

Sent with `messenger.capability(ITemplateMessaging)` to the `DirectMessage` target (phone first, ADR-0022). Meta sample Templates, `en_US`.

| ID | Do | Expect |
| --- | --- | --- |
| T-01 | `/template order` | `jaspers_market_order_confirmation_v1` (utility, `/messages`) with your profile name, the last 6 chars of your message ID and today's date; ✅ in log, then sent/delivered statuses |
| T-02 | `/template hello` | `hello_world` (utility, `/messages`) |
| T-03 | `/template plain` | `jaspers_market_plain_text_v1` (marketing, default route = Marketing Messages API). Record the result: a test number may not be onboarded to that API |
| T-04 | `/template plain-cloud` | same Template forced to `/messages` (`cloud_messages_fallback`) |
| T-05 | `/template order` on Instagram | "/template works only on WhatsApp: instagram has no Templates." No send |

## Gate B: self-service Unified Login

Set `META_APP_ID`, `IG_LOGIN_CONFIG_ID` and `CONNECT_OPERATOR_TOKEN`, and register `https://<tunnel>/connect/instagram/callback` as a valid OAuth redirect URI. Leave the **Deauthorize callback URL** unset (Wappa mounts no deauthorize route; Unified Login grants never trigger it) and register the **Data Deletion Request URL** as `https://<tunnel>/connect/instagram/data-deletion` (host-owned; returns a confirmation code). The app no longer has its own `/connect/instagram/deauthorize`.

| ID | Step | Expect |
| --- | --- | --- |
| B-01 | open `/connect/instagram/start?token=…`, log in (Facebook or Instagram), share accounts | the callback page lists accounts, readiness and per-field subscription outcomes; no token shown |
| B-02 | DM the newly connected account | handled without copying any ID or token |
| B-03 | reload the callback URL | 400 (one-use state) |
| B-04 | start, then cancel the dialog | "Connection cancelled", nothing changed |
| B-05 | deselect messaging permission during consent | account reported "missing instagram_manage_messages", not connected |
| B-06 | connect again | record rotated (`credential_version` +1), Messenger evicted |
| B-07 | revocation | not applicable to Unified Login: no per-user deauthorize fires for business-owned `SYSTEM_USER` tokens; revocation is a business-portfolio action (system user or app/asset removal). Revocation is the Host's job: deactivate the record, refresh the directory, call `connector.disconnect`; later webhooks for that Inbox are rejected |
| B-08 | Creator account | record whether a bootstrap is needed |

App-role-only testing doesn't satisfy an independent-customer audience. App Review/Advanced Access is an external gate.

## Gate C: Symphonai

Implemented on the Symphonai branch `feat/instagram-wappa-adoption`. The branch temporarily points `backend/pyproject.toml` at the local editable Wappa (`[tool.uv.sources]`), so replace that with the released Wappa version before merging.

- `SymphonaiInboxDirectorySource` and the channel credential lifecycle serve Instagram Owner Channels.
- `runtime_inbox` resolves through `InboxCredentialAccess` and adds `resolve_runtime_credential(inbox_ref)` for extensions.
- Every send path uses `target=` (`services/wappa/targets.py`, `ScoreDependencies.user_target`, `require_user_target()`).
- Inbound and delayed agent runs call `messenger.mark_as_read(message_id, target=direct_target(...))`, which is Platform-neutral (Instagram: `mark_seen`, then `typing_on` when asked), so they no longer abort on Instagram and need no Platform branch.
- Operator (human) sends accept Instagram text.
- Open: Symphonai still reads `webhook.user` with `getattr` to fill its Chat record; replace those reads with `messenger.resolve_platform_user_profile(webhook.user)` (Wappa H-26) and persist the `PlatformUserProfile` fields, so Instagram Chats get the User's name, username and picture.
- The cache middleware records `send_carousel` like the other interactive sends; `mark_as_read` and `IMediaLibrary` calls are not cached as messages.

| ID | Step | Expect |
| --- | --- | --- |
| C-01 | Create an Instagram Owner Channel (`channel='instagram'`, `external_inbox_id` = `external_account_id` = IG account ID) and store its credential through `ChannelCredentialService.set_active_token`, then refresh after commit | `symphonai doctor`/directory resolves `instagram:<id>` |
| C-02 | DM the account | Agent reply arrives in the same thread; Conversation and history appear in the operator UI |
| C-03 | Two testers at once; the same tester on two IG accounts | Separate Conversations, no crossed context |
| C-04 | Operator takes over, then replies (text) from the UI | Agent and delayed jobs paused; human text delivered; resume per policy |
| C-05 | Extension: `resolve_runtime_credential(InboxRef(instagram, id))` → Graph read; rotate token; deactivate | New version used next call; deactivated raises `RuntimeInboxInvalid` |

Not covered: Instagram operator media (WhatsApp media IDs have no IG equivalent), frontend changes, and Symphonai-side comment/mention handling. Symphonai's `MasterEventHandler` inherits Wappa's no-op defaults for comments, which is host policy to add.

## Developer skills evidence

Current set (2026-11-06, commit 49ca1f0): shipped `wappa-apps`, `wappa-conversational-scores`, `wappa-state-and-storage`, `wappa-host-integration`; maintainer `wappa-develop` and `bump-version`.

- Lint: `lint_skill.py --professional` reports 0 errors and 0 warnings for all six skills; `--lanes .` reports 0/0.
- Deterministic tests: `tests/test_shipped_skills.py` (was `test_instagram_skills.py`). Every taught import and `self.messenger` / `self.whatsapp` / `self.instagram` method exists, no code block uses `recipient=`, frontmatter names match folders, every reference is linked and every named sibling skill ships, the isolation example runs, and emission never overwrites. `tests/test_doc_claims.py` compiles every Python block and resolves every backticked path in the skills.
- Fresh-agent evaluation (Claude Opus 5.5, Claude Code subagents, 2026-11-06), each restricted to the skill folders: (1) comments plus DMs with a video-header button menu on both Platforms, the WebM/WebP/OGG asset question, and a long text with name greeting; (2) a 14-service lead intake with Redis state, Postgres leads and confirmation-ID tracking; (3) a multi-tenant SaaS: connecting accounts, a CRM webhook, bearer auth, live dashboard events and a 24-hour window guard. Every core assertion held: no Platform branch for shared actions, comment logic in `process_comment`, `InteractiveHeader.of_video`, the unified media kit with renditions for voice notes, one `send_text` for the long policy, lists split to fit 10 rows / 20 characters, commit-then-`refresh_inbox`, a context resolver for the CRM, and Messenger middleware for the window. Their reported gaps were fixed in the same commit (the `wappa_parts` dict shape, `StatusWebhook` fields and Instagram's read watermark, an app skeleton, extra limits, the revoke order and token, registering Messenger middleware from a plugin). The agents' code was not executed; other models and harnesses were not evaluated, and the skill picker was not visually checked.
- The skills' scheduled-work sections follow the scheduling lane from ADR-0030; re-run the fresh-agent evaluation for them, since it predates that change.

## Results log

Reading the logs: see `../wappa_examples/instagram_conversations_example/README.md` → Reading the logs

| Date | ID | Result | Evidence and limits |
| --- | --- | --- | --- |
| 2026-11-03 | setup | pass (read-only) | `app.setup`: access verified via `InboxCredentialAccess`; subscribed `messages, messaging_seen` |
| 2026-11-03 | A-19 (library) | pass | reader read a REELS video and a 10-child carousel, comments with pagination, and `not_found` for an unknown ID (`100/33`) |
| 2026-11-03 | subscribe | pass (subscription only) | `app.setup --subscribe`, then a read-back: all 8 fields subscribed, `message_edit` included. Delivery not yet observed |
| 2026-11-03 | C (offline) | pass (unit/contract) | Symphonai `-m "not real"` suite: 6 failed, 9877 passed. The 5 `test_installed_packages` failures come from the temporary local Wappa path, and the business-rules count is from unrelated RBAC commit `73d8138a`. Live C-01…C-05 not run |
| 2026-11-05 | A-01/A-02 | pass | Text and quick-reply taps arrived on `messages` (04:32–04:34); echo and READ status events also arrived |
| 2026-11-05 | A-10 (partial) | blocked at budget | "Start form" quick reply, name, and "Chatbot" service quick reply all handled. Budget button template accepted by Meta (200). Tapping "< $1K" produced **no webhook delivery at all**, so `messaging_postbacks` is likely not ticked at the app-level webhook config, even though the account-level subscription lists it |
| 2026-11-05 | setup (app fields) | fixed | The app-level Instagram webhook had only `messages, messaging_seen`, so postbacks were dropped. After the user enabled the remaining fields in the dashboard, postbacks were delivered. Account-level and app-level subscriptions are separate gates |
| 2026-11-05 | A-07 (postback) / A-10 | pass (happy path) | 04:42:17 budget postback, then `InteractionWebhook` and the email prompt. 04:42:27 email text, then the summary card (accepted). 04:42:40 confirm postback, then the confirmation text. The email was masked in the logs. Not yet exercised: the invalid-email re-prompt and the "Other" branch |
| 2026-11-05 | A-10 ("Other" branch, Redis) | pass | With `CACHE_BACKEND=redis`: service "other", then the details step, then budget "medium", email and confirm (09:47–09:49 UTC). State is in DB1 `instagram__<inbox>:state:form_intake:<user>` (hash, `step=done`, TTL 1800 s). The submission is in DB2 `instagram__<inbox>:df:form_submissions:pkid:<user>` (hash, about 24 h). Keys are Platform- and Inbox-qualified. Free text after `done` falls through to the other handlers |
| 2026-11-05 | W-01 (fix) / W-03 / P-01 (WhatsApp) | pass (happy path) | After the restart at 12:57 (directory cache cleared): list tap `form:service:branding` with no `description` handled at 12:59:01, then budget buttons, email, the image-header summary card, and confirm at 12:59:20. Every send went `to` the phone (ADR-0022). Submission in DB2 `whatsapp__1014417365082534:df:form_submissions:pkid:CO.…` and state in DB1 `whatsapp__1014417365082534:state:form_intake:CO.…`. No 4xx, `ValidationError` or `META_SCHEMA_DRIFT` since the restart. Not yet exercised: the "Other" branch and the invalid-email re-prompt |
| 2026-11-05 | W-04 / P-04 `/carousel` (WhatsApp) | fail → fixed → pass (13:04:55 and 13:17:31 accepted) | 13:01:50: Meta 400, code 100, "`interactive.action.cards.N` missing `type`". Quick-reply cards carried no `type`; Meta's examples set `"type": "cta_url"` on every card. Fixed in `_wa_cards` with a test. Rerun after a restart |
| 2026-11-05 | W-03 ("Other" + invalid email, WhatsApp) | pass | 13:00:28–13:01:08: "Other", then free-text details, budget, an invalid email ("Abc") re-prompted, then valid email and confirm |
| 2026-11-05 | W-01 / W-02 / W-04 `/quick` `/buttons` `/card` | pass | 13:01:12–13:01:43: `lab:color:blue` (list without description), `lab:ping`, `lab:plan:pro` |
| 2026-11-05 | stale tap after the fix | expected | 13:02:35: Meta redelivered the 12:52 "Chatbot" tap that had been answered 400 (message timestamp 12:52:14). That form was already done, so the stale-action guard replied "already submitted or expired". Retries of rejected webhooks can arrive minutes later and out of order |
| 2026-11-05 | W-04 `/carousel` (WhatsApp) rerun | pass (send) | 13:04:54 accepted with `type: cta_url` on every card. Card tap not yet recorded |
| 2026-11-05 | P-05 `/cta` | pass (send) | 13:06:39 |
| 2026-11-05 | W-05 `/ask-location` | pass | 13:07:11: pin with `latitude`/`longitude` only (no name/address for a dropped pin) and `context.id` = the request message. All fields reach `WhatsAppLocationMessage`; no drift |
| 2026-11-05 | W-06 `/ask-contact` | pass | 13:07:21: `contacts[0]` with name parts, phone + `wa_id`, base64 `vcard`, `origin=contact_request`, no `context`. All reach `ContactInfo`; no drift. The lab now replies with a summary of both |
| 2026-11-05 | `/location`, `/contact` | pass (send) | 13:07:39, 13:08:20 |
| 2026-11-05 | `/sticker` (WhatsApp) | fail → fixed → pass (WebP rendition rerun) | 13:08:29 PNG link accepted (200), then status `failed` 131053 "Unsupported Sticker mime type image/png". `send_sticker` now takes renditions and WhatsApp picks `.webp` (non-WebP raises before the call); the lab sends `[sample.webp, sample.png]` |
| 2026-11-05 | Instagram card echo | fixed | `META_SCHEMA_DRIFT field=InstagramAttachmentPayload.generic` on the echo of a card; now modelled |
| 2026-11-05 | `/sticker` (WhatsApp) rerun | pass | 13:16:28: `send_sticker([webp, png])` picked `sample.webp`; accepted, then sent, delivered and read (no 131053) |
| 2026-11-05 | W-04 carousel tap | fail → fixed → pass (15:01:50) | 13:17:36: the tap arrived as `type: button`, `button.payload = lab:plan:team`, not `interactive`. `get_interactive_selection()` ignored it, so the lab echoed "Choose". Wappa now treats `button` taps as selections |
| 2026-11-05 | token | expired → renewed | 14:23:48 sends failed with code 190 (token expired at 14:00); after the restart at 14:25 every send was accepted |
| 2026-11-05 | W-07 inbound media (WhatsApp) | pass | Photo with caption "Bonjour" (14:25), voice note (14:29, echoed back as a voice note with `is_voice`), PDF (14:30), sticker (14:30), video (14:33): each downloaded through `IMediaLibrary` and echoed by media ID. The PDF echo showed "Untitled" because the lab did not pass `filename`; fixed in the lab |
| 2026-11-05 | W-09 reply / forward | pass | Swipe reply "Hello" carried `context.from`. 15:05:14 forwarded "Que haces mi bebé" arrived with `context.forwarded: true` → `was_forwarded()` true; the lab now prefixes its echo with "↪️ forwarded" |
| 2026-11-05 | W-10 reaction | pass | ❤️ at 14:30:52, removal at 14:30:59 (`reaction` without `emoji`), both `InboundMessageWebhook(REACTION)` |
| 2026-11-05 | W-11 edit / delete | not deliverable | The WhatsApp app could not edit a message sent to the business. Delete-for-everyone produced no webhook from Meta, so there is nothing to handle |
| 2026-11-05 | W-12 `/read` | pass | 14:31:33 `mark_as_read(typing=True)` accepted; statuses sent, delivered and read with `pricing.subtype` (200) |
| 2026-11-05 | W-13 unsupported | pass | 15:04:23 a poll arrived as `type: unsupported`, `unsupported.type: poll_creation`, error 131051 → `InboundMessageWebhook` with the unsupported message, 200. The lab had no reply for it (silent); it now answers "I can't read that kind of message yet (poll_creation)" |
| 2026-11-05 | Block 2 health | pass | No 4xx, `ValidationError` or `META_SCHEMA_DRIFT` after 14:25 |
| 2026-11-05 | P-06 media sends (WhatsApp) | pass | 14:35–14:36: `/image` by URL, `/image-upload` (Media API upload, send by ID), `/audio`, `/voice` (OGG/Opus `is_voice` → voice note), `/file`, `/video`, all accepted |
| 2026-11-05 | document echo filename | pass | 14:36:24 inbound PDF echoed with its original `filename` |
| 2026-11-05 | T-01 `/template order` | pass | 14:36:44 `jaspers_market_order_confirmation_v1` (utility) accepted with the User's name, order code and date |
| 2026-11-05 | T-02 `/template hello` | pass | 14:36:54 `hello_world` accepted |
| 2026-11-05 | T-03 `/template plain` | pass | 14:37:01 `jaspers_market_plain_text_v1` (marketing, default route) accepted |
| 2026-11-05 | T-04 `/template plain-cloud` | pass | 14:37:10 same Template forced to `/messages`, accepted |
| 2026-11-05 | `played` status | fail → fixed → pass (14:58:21 and 15:02:13 `StatusWebhook` PLAYED, 200) | 14:35:58–14:36:27: five status webhooks with `status: played` (voice note played) answered 400 and were dropped by Meta. Fixed: `played` is a `StatusWebhook`; unknown statuses → `UNSUPPORTED_EVENT` + drift |
| 2026-11-05 | `account_update` | expected | 14:34:40 `META_SCHEMA_DRIFT field=webhook field 'account_update'`, answered 200 |
| 2026-11-05 | Block 4 Instagram DMs (14:45–14:52) | pass | `/help`, `/whoami`, `/form` (Other → free text, invalid email re-asked, summary card, Confirm), `/quick`, `/buttons`, `/card`, `/carousel` (tap → Choose), `/cta`, `/image`, `/image-upload`, `/audio`, `/video`, `/file`, `/sticker` (PNG rendition), `/location`, `/contact`, `/read`: each accepted, every echo and `read` status received. Inbound photo, voice note and video downloaded and echoed. `/ask-location`, `/ask-contact`, `/template order` answered as unsupported / WhatsApp-only. React, unreact and edit arrived (two reactions, one `MessageUpdateWebhook`) |
| 2026-11-05 | `/voice` on Instagram | fail → fixed → pass (14:56:24, M4A rendition accepted) | 14:47:50 the OGG voice note was rejected by Meta with `100/2534080` (Instagram has no OGG) and the lab only logged a warning. Fixed: `send_audio` picks a rendition per Platform; `/voice` sends `[sample.ogg, sample.m4a]` with `is_voice=True` in one call (WhatsApp → OGG voice note, Instagram → M4A). The lab now tells the User when a send fails |
| 2026-11-05 | Block 4 step 7: `#reply` comment | pass | 14:58:45 comment 18119612149800748 on media 18009504445779229 → public reply accepted (17990522349082034); its own comment webhook at 14:58:51 was ignored as "our own comment" |
| 2026-11-05 | Block 4 step 7: `#dm` comment | pass | 14:59:24 comment 18102082481556071 → private reply accepted, DM echo at 14:59:27 |
| 2026-11-05 | Block 4 step 7: @mention | pass | 15:03:28 `MentionWebhook` (subject comment, media 17875407990014025, comment 18115429729865536) → `get_mentioned_comment` 200, text "@candyflipfest". The lab only logs mentions: the author has no DM thread, so there is nothing to reply to |
| 2026-11-05 | `/post`, `/comments` (Instagram) | pass | 15:00:40 `get_post(18009504445779229)` 200 → reply; 15:00:55 `list_comments(limit=5)` 200 → reply |
| 2026-11-05 | Carousel card tap (WhatsApp) | pass | 15:01:50 tap arrived as `button` 'Choose' (selection, not text) → reply |
| 2026-11-05 | Voice note echo + `played` (WhatsApp) | pass | 15:01:59 inbound voice note → echoed as a voice note 15:02:01 → played 15:02:13 |
| 2026-11-06 | Gate A rerun after hardening (both Platforms) | pass | 09:08–12:07: text, `/help`, every media send, media in (WhatsApp image, video, document; Instagram image, video, voice), `/quick`, `/buttons`, `/card`, `/card-video`, `/cta`, `/carousel`, `/carousel-video`, `/location`, `/contact`, `/whoami`, Instagram `/read`, WhatsApp `/ask-location`, `/ask-contact`, `/template order`, `/form` (12:06 WhatsApp, 12:07 Instagram) accepted |
| 2026-11-06 | `/carousel` mixed header kinds (WhatsApp) | fail → fixed → pass | Meta 131009 "same structure for all cards" for image + video cards. `check_carousel` now refuses mixed header kinds when built (3226ea4); the lab sends `/carousel` (images) and `/carousel-video` |
| 2026-11-06 | `/contact` (WhatsApp) | fail → fixed → pass (10:29:34) | Meta 131009 "ContactName should have atleast one optional value". `ContactName.first_name` is required and `formatted_name` is built from the parts (057422a) |
| 2026-11-06 | Comment controls (Instagram) | pass | 12:19–12:22 on media 17985939194362301: `#reply`, `#dm`, `#both`, `#hide`, `#hidecycle`, `#read` (comment found, media found), `#lock` (comments disabled), `#delete` accepted; the bot's own replies were ignored. `#unlock` not exercised through Wappa (comments re-enabled in the app) |
| 2026-11-06 | @mention (Instagram) | pass | 12:23:05 comment mention on media 18041598575646756, `get_mentioned_comment` returned the text |
| 2026-11-06 | `/post`, `/comments` (Instagram) | pass (send) | 12:26:36 and 12:26:47 on media 17985939194362301. WhatsApp "not available" guard not yet rerun |
| 2026-11-06 | Concurrency | pass | `/formats image` dispatch ran 46.8 s; its webhook answered 200 in 19.6 ms, and status webhooks for the same User were handled in 3–5 ms during the run. A first WhatsApp `/formats video` never reached the server (no webhook POST between 12:28:19 and 12:30:02) |
| 2026-11-06 | Format matrix image + video (first run) | partial | Results in `references/media-formats.md`; rerun pending after 2e5fd84 (code= visible, Instagram rejection reasons logged) and ef05128 (WhatsApp `.3gp` video as `video/3gpp`). WhatsApp HEIC link failed 6 min later: 131053, Meta could not fetch the URL (503). Instagram video links other than MP4 answered 403 |
| 2026-11-06 | `/post 123`, `/comments 123` (WhatsApp guard) | pass | 12:36:46 and 12:36:52: "Post/comment reads: not available on whatsapp" |
| 2026-11-06 | Rate-limit governor (Instagram, live) | pass | Usage warnings at 80–98% (`x-app-usage`), then code 4 → app-scope block 300 s; later calls refused locally (`rate_limited`, `retry_after`) without calling Meta; the lab aborted the run (FORMAT_ABORT). Meta's own window is about an hour, so slices of about five calls 10–15 min apart |
| 2026-11-06 | MetaGraphClient (both Platforms) | pass | WhatsApp core commands and the WhatsApp `/formats video` re-check (15:01–15:02) through the shared transport: HEVC, MOV, MKV, WebM VP8/VP9 refused before I/O on link and upload; the lab's `link-raw` lane failed by status 131053 as expected |
| 2026-11-06 | Format matrix, Instagram (every family) | pass → hardened | Image, sticker, document, card, video, audio and voice by link and upload. Hardened from the results: WebP uploads refused (965c3d2); video uploads only H.264 MP4 (b6625a8); audio and video URLs Instagram cannot play (MP3, OGG, WebM audio; MOV, MKV, 3GP video) refused before I/O instead of shared as link text, as WhatsApp does |

### Echo filter evidence (2026-11-05, 08:06)

- `/help` from the test user → Wappa sent a generic-template card (Send API 200 at 08:06:16.275) → echo arrived 08:06:17.135 with keys `mid`, `is_echo`, `attachments` only (no `app_id`, no `metadata`) → `registry hit after 0.0s` → dropped. P-11 pass; Send API `message_id` == echo `mid` confirmed.
- "Manual test" typed in the Instagram app (business account) → echo 08:07:00.609, keys `mid`, `is_echo`, `text` only → registry miss after 1 s + 2 s → `process_outbound_echo origin=business_app type=text text='Manual test'` at 08:07:03.621. P-10 (Instagram) pass.
- Decision: no Platform evidence distinguishes the two, so the filter is registry-only; the `app_id` branch and `META_APP_ID` were removed.


### Gate B results (2026-11-05) — closed: B-01, B-02, B-03, B-04, B-06 pass; B-05, B-07 not applicable to Unified Login; B-08 not run

| Date | Step | Result | Evidence |
|---|---|---|---|
| 2026-11-05 | `/connect/instagram/start` redirect | pass | 302 to the Facebook Login for Business dialog with `config_id`, `state` and `redirect_uri=<PUBLIC_BASE_URL>/connect/instagram/callback`; `/connect/accounts` with a wrong token → 401 |
| 2026-11-05 | Callback + store (two accounts in one login) | pass | 15:10:22 `instagram:17841400514164190` (sashanclrp) connected v1, 15:10:24 `instagram:17841457247424017` (candyflipfest) refreshed v75; `subscribed_apps` 200 for all eight fields on both; `/connect/accounts` lists both active, no secrets |
| 2026-11-05 | DM to the new Inbox (sashanclrp) | blocked (Meta) | "halo" (~15:11) and `/carousel` (~15:20) to sashanclrp: no webhook reached the server, and no `is_echo` arrived for sashanclrp's own sends either. Same messages to candyflipfest at 15:20 routed and answered. `GET /{ig-id}/subscribed_apps` with each stored token returns the same app and all eight fields for both accounts, so Wappa's connect and subscription are correct; Meta is not delivering sashanclrp events (Development mode: tester invite acceptance / Connected tools "Allow access to messages" on sashanclrp). Also found and fixed: httpx logged OAuth secrets in URLs (`SecretRedactingFilter`) |
| 2026-11-05 | Root cause for sashanclrp | Platform setting | sashanclrp's Message controls → Connected tools → "Allow access to messages" was off: Instagram delivered the DMs to the inbox but to no app. Not a Wappa issue; the connect page should tell operators to check it |
| 2026-11-05 | Third account connected + DM routing | pass | 15:43:11 `instagram:17841458406313025` (candyfliphard) connected v1 with all eight fields; 15:45:54 `/help` from user 1591883612239873 routed to that Inbox (`[I:17841458406313025]`), help buttons accepted, echo and `read` status received. Three Instagram Inboxes plus WhatsApp in one explicit directory |
| 2026-11-05 | P-14 deauthorize | fail (no callback) | ~15:50 app removed in sashanclrp's Instagram "Apps and websites". ngrok request history shows no POST to `/webhook/inboxes/instagram/deauthorize` from Meta (the endpoint is reachable: a malformed probe at 15:58:33 → 400). `/connect/accounts` at 15:57 still lists `instagram:17841400514164190` active. Open question: the connect flow is Facebook Login for Business (`facebook.com/dialog/oauth` + `config_id`, `/me/assigned_instagram_accounts`), so the grant may live on the Facebook side (Business Integrations) and fire the Facebook Login deauthorize URL, whose `user_id` would be the Facebook user, not the Instagram account Wappa expects |
| 2026-11-05 | P-14 diagnosis | not a valid run | sashanclrp's Instagram "Apps and websites → Active" is empty and its tester invite for "30X - Media-IG" is still pending: the Unified Login (Facebook Login for Business config 2221564508405833) grant was made by the operator's Facebook user, so an Instagram-side removal had nothing to remove. Rerun: (a) Facebook → Business integrations removal with the Facebook Login for Business deauthorize URL set; (b) Instagram-login path via the dialog's Instagram option, then removal under Apps and websites |
| 2026-11-05 | P-14 Facebook Business integrations removal | no revocation | ~16:05 "Wappa \| CRM removed" in Facebook → Business integrations. No deauthorize POST in ngrok history; all three stored tokens still valid. `debug_token`: `type: SYSTEM_USER`, `expires_at: 0`, same system user `122097624591542806` for all three Inboxes. Unified Login (Facebook Login for Business config) issues a Business Integration System User token owned by the business portfolio, so a person removing their own integration revokes nothing and Meta sends no per-user deauthorize. Real revocation is a business-portfolio action (remove the app or the Instagram asset); next run tests that and whether any callback fires |
| 2026-11-05 | B-01 start + callback | pass | see rows above: three accounts listed with readiness and per-field outcomes, no token shown |
| 2026-11-05 | B-02 DM the newly connected account | pass | candyfliphard `/help` 15:45:54 routed to `instagram:17841458406313025` and answered |
| 2026-11-05 | B-03 reload the callback URL | pass | replayed the last real callback (code + state) → 400 "unknown or already used connection state"; state consumed before any code exchange |
| 2026-11-05 | B-04 cancel the dialog | pass | 16:11:24 Meta redirected with `error=access_denied&error_reason=user_denied&action=cancel` → callback 200 "Connection cancelled. Nothing was changed."; no record touched |
| 2026-11-05 | B-05 untick messaging permission | not applicable to Unified Login | the Facebook Login for Business configuration fixes the permission set: the dialog only offers business portfolio, Instagram account and optional ad account, then a review screen with no per-permission toggle. The missing-scope path (`missing instagram_manage_messages — not connected`) stays covered offline by the connector readiness tests |
| 2026-11-05 | B-08 Creator account | not run | no Creator account available; candyfliphard and candyflipfest are Business accounts connected through the business portfolio |
| 2026-11-05 | B-06 connect again | pass | candyflipfest v74 → v75 → v76 → v77 and sashanclrp v1 → v2 across reconnects (record rotated) |
| 2026-11-05 | B-07 / P-14 revocation | not applicable to Unified Login | Unified Login issues business-owned `SYSTEM_USER` tokens (no expiry); removing the person's Business integration revokes nothing and Meta sends no deauthorize. The deauthorize lane (signed_request → `InboxConnectionWebhook(DISCONNECTED)` → host deactivates) is covered offline (`tests/test_unified_event_lanes.py`, lab `tests/test_deauthorize_lane.py`) and applies to Instagram-login grants. Follow-up: detect revoked credentials on use (190/10/200) and emit the same DISCONNECTED event |


### Symphonai quote failure report (2026-11-08; 0.34.4 follow-up)

Consumer-reported evidence, not independently replayed by Wappa: Symphonai used Instagram API with Instagram Login, Graph v25.0. Quoting the exact fresh inbound `new_ig_dm_…` Message ID (167 characters) from the same Inbox failed with HTTP 400, code 100, subcode 2534002; sending without the quote succeeded. Wappa's adapter documentation still targets Unified Login; this report does not establish general Instagram Login support or prove that quoted replies are universally unsupported. The user supplied Meta's [Send a reply documentation](https://developers.facebook.com/documentation/business-messaging/instagram-messaging/features/send-message#send-a-reply): the Facebook Graph/Page-token path accepts a top-level `reply_to.mid` containing the target message's original ID, for text, media and template sends. Wappa already preserves the inbound `message.mid` as the Universal Message's `message_id` and forwards it unchanged. This source confirms the payload shape for that path; it does not explain the reported Instagram Login/`graph.instagram.com` rejection. Direct documentation access returned HTTP 429. The 0.34.4 fallback therefore applies only to that definite rejection.

Offline regression evidence: fake Graph responses cover text/image, split text and captions, failed/indeterminate retries, unrelated errors, and sent-message registry writes. Signed callback tests cover unknown-only and mixed batches, warning suppression, invalid signatures/envelopes, account mismatches, inactivity and directory failures.

Live follow-up, not run: restart with 0.34.4; quote a fresh inbound DM with text and media; record the original refusal, unquoted acceptance/message ID, returned `wappa_reply_to` evidence, echo/status and recipient rendering separately. Deliver signed callbacks for an unsubscribed-to-Wappa account and a registered account together: confirm 200, one warning per unknown account per process without values, and dispatch only for the registered account. Confirm bad signatures still return 401 and malformed/mismatched deliveries 400.


### Instagram quote suppression and ID research (0.34.8)

The consumer reports that fresh exact webhook mids still fail with Meta 2534002 after the 0.34.4 fallback. The user requested temporary suppression to avoid that wasted request. In 0.34.8 the adapter ignores reply_to_message_id before I/O and records a suppression reason, without claiming Meta rejected a call it never made. WhatsApp quoting and inbound context are unchanged. Offline tests prove no reply_to and no extra send.

Manual live follow-up, not run: from the existing Instagram conversations lab use app.reply_probe (canonical Wappa scripts/instagram_reply_probe.py) to compare the exact same-Inbox webhook mid with history IDs. Default is read-only and reports fingerprints. Explicitly test one plain control, one webhook ID, and optionally one fingerprint-fenced history candidate, matching Login path, token, host and Graph version. Record acceptance/code/subcode and recipient quote rendering separately. No ID conversion or automatic send matrix is justified by the report. See docs/migration/0.34.8.md.


### Interactive `/reply` diagnostic (unreleased lab change)

Restart `instagram_conversations_example`, send `/reply` as a fresh Instagram DM, then repeat using the app’s Reply action on an earlier message. The diagnostic compares normalized/raw webhook message IDs, optional quoted-message context, a Conversations API ID matched to the fresh command, and a successful unquoted control’s outbound ID. Each distinct candidate is sent once via raw Graph `reply_to.mid`, bypassing suppression/fallback. Record the configured Graph host/version, `REPLY_PROBE` outcomes/error codes, callback acknowledgement and visible quote rendering separately. Do not infer universal unsupported behavior from a failed candidate. Implementation is covered by offline command tests; live run remains pending the User’s DM.


### `/reply` live result — 2026-11-08 14:02 America/Bogota

User ran the existing Instagram lab with the uncommitted diagnostic and supplied a screenshot of the received control and result summary. Configured endpoint: `graph.facebook.com`, Graph `v26.0`. `REPLY_PROBE` at 14:02:03 records an accepted unquoted control, then HTTP 400 / code 100 / subcode 2534002 for both the exact inbound webhook message ID (identical across normalized message, webhook ID and raw `message.mid`) and the accepted control send’s outbound `message_id`. Both distinct tested IDs are 167 characters; raw identifiers are intentionally omitted. No quoted send was accepted, and the screenshot shows the unquoted control and diagnostic summary. The Conversations lookup returned multiple conversations, so the diagnostic skipped history IDs; quoted-message context was absent in this run. Callback HTTP acknowledgement and delivery/read status are not separately established by this probe record.

Verdict: these two native message-ID sources fail quoting on this configured account/endpoint. This supports the proposed temporary adapter mitigation (ignore Instagram `reply_to_message_id`, preserve ordinary sends and expose dropped-quote evidence), but does not establish that every Instagram ID or Login mode fails. A Conversations API candidate remains untested; this is not a completed exhaustive ID investigation. No 0.34.8 publication is implied by this result.


The interactive probe now searches multiple conversations and follows cursor pagination rather than skipping ambiguous results. It matches current-command history IDs by sender, exact text and timestamp, deduplicates ID sources, and reports errors/truncation. Offline regression coverage exercises a match in a later conversation and later message page, including an unreadable neighboring conversation; all 44 lab tests pass. A fresh live `/reply` run is required to exercise the updated handler.


### History-ID gap closed — 2026-11-08, direct read-only live lookup

Using the lab’s configured Instagram account/token and `graph.facebook.com/v26.0`, queried the conversations list and inspected message histories without sending any additional messages. Meta returned 20 conversations despite the User filter. The first conversation contained the User’s `/reply` at `2026-11-08T19:01:53+0000`; its Conversations API message `id` is 167 characters, with SHA-256 prefix `e4c774bf38c3`, exactly matching the inbound webhook candidate already rejected in the 14:02:03 probe. The remaining 19 conversation histories contained no matching `/reply` in the inspected pages. Raw IDs and credentials are omitted.

This closes the current exchange’s alternate-history-ID question: webhook and Conversations API expose the same identifier, not an alternate encoding. The other tested identifier source, the fresh outbound send response, also failed quoting. These live facts support temporary quote suppression for 0.34.8 on the tested account/Graph route; they do not establish behavior for every account, Login mode or API version. The lab diagnostic now returns immediately once it matches the current command in history, avoiding unnecessary reads of unrelated conversations.

### Gate C results (2026-11-08) — closed: C-01 to C-05 pass

Source: the Symphonai session on branch `prd/wappa-v0341` (tip `dbd3100d2`, Wappa pinned to 0.34.8). Its ledger records events, not one UTC time per check. The user then ran C-03, C-04 and C-05 live and reported every Gate C check passed (2026-11-08); the rows below record the user's report, with no per-check time.

| Date | Check | Result | Observation |
| --- | --- | --- | --- |
| 2026-11-08 | C-01 Owner Channel | pass (in substance) | candyfliphard connected through the demo frontend's Instagram login; credential persisted; inbound DMs resolved to that Channel by live routing. `set_active_token` and a direct `instagram:<id>` directory read were not exercised by hand |
| 2026-11-08 | C-02 Agent reply | pass | DMs got the Agent's reply in the same thread; Conversation, messages, Episodes and system messages showed in the operator UI. Found the `reply_to` 2534002 rejection, fixed in 0.34.4 (then 0.34.8) |
| 2026-11-08 | C-03 isolation | pass (user-run) | Two testers at once and one tester on two Instagram accounts: separate Conversations. Also offline: Symphonai's multi-Owner suite (2 Owners × IG + WA, 129 fast and 112 real tests, no cross-Owner leak) |
| 2026-11-08 | C-04 operator takeover | pass (user-run) | Agent and delayed jobs paused, human text delivered, resumed per policy |
| 2026-11-08 | C-05 credential lifecycle | pass (user-run) | Graph read through `resolve_runtime_credential`, rotation picked up on the next call, deactivation raised `RuntimeInboxInvalid` |

### A-11 and B-08 results (2026-11-08, user-run)

| Date | Check | Result | Observation |
| --- | --- | --- | --- |
| 2026-11-08 | A-11 form edge cases | pass (user-run) | Resume with `/form`, stale button, `cancel`, restart and double confirm ("already submitted") behaved as expected. Offline: lab `test_form_intake.py` (resume/cancel/restart, stale, concurrent Users and the same User ID in two Inboxes) |
| 2026-11-08 | B-08 Creator account | pass (user-run) | Creator account connected through Unified Login; reported by the user |
