---
name: wappa-apps
description: Builds, extends and tests conversational apps on the Wappa library that run on WhatsApp, Instagram or both from one handler — event lanes, the prebuilt Messengers (self.messenger, self.whatsapp, self.instagram), DirectMessage targets, text, media, buttons, lists, CTA and carousels, results and wappa_parts, rate limits, media formats per Platform, user profiles, WhatsApp Templates, Flows and location requests, Instagram comments, private replies and mentions, connecting accounts through Embedded Signup or Unified Login, and Meta app setup. Use when the user wants a WhatsApp or Instagram bot on Wappa, asks how to send or receive any message type, which media format to send, why a send failed, or how to set up the Meta app or webhook. Hands off forms and Scores to wappa-conversational-scores, caches, Redis and databases to wappa-state-and-storage, and multi-Inbox, plugins and upgrades to wappa-host-integration.
---

# Conversational apps with Wappa

Wappa owns the Platform mechanism: signed webhook intake, typed events, sends, media rules, credentials and rate limits. The app owns policy: what to answer, when, moderation, AI, human takeover and business records. Never put app policy into Wappa, and never invent Wappa APIs. If a call isn't in these files or in `docs/public-contract.md` of the installed Wappa, it doesn't exist.

## Workflow

```
Progress:
- [ ] 1. Inspect: Wappa version, Host (plain Wappa or Symphonai), Platforms, task
- [ ] 2. Route: load only the reference the task needs
- [ ] 3. Build: one code path for shared actions, public imports only
- [ ] 4. Verify offline, then live; report evidence and limits
```

**1. Inspect.** Run `uv run python -c "import wappa; print(wappa.__version__)"`, and read the installed `CHANGELOG.md` when the version is older than these files assume (0.34.6). A repo importing `symphonai` is a Symphonai Host: Symphonai's own skills (`develop-symphonai`, `develop-wappa`) own its Score engine and adapters. Use this skill for the Wappa calls underneath, never to rebuild what Symphonai already has.

**2. Route.**

| Task | Load |
| --- | --- |
| Send or receive text, media, location, contact, sticker, buttons, lists, CTA, carousels; selections; results; `mark_as_read`; the User's name; media upload and download | `references/messaging.md` |
| Which file format to send on each Platform, or why a media send was refused | `references/media-formats.md` |
| WhatsApp-only: Templates, inbound Flow replies and calls, location and phone requests, the 24-hour window, phone and BSUID addressing | `references/whatsapp.md` |
| Instagram-only: comments, Live comments, public and private replies, comment controls, mentions, post reads, story replies and shares | `references/instagram.md` |
| Connecting accounts (WhatsApp Embedded Signup and Instagram Unified Login, one flow), revoking, token reuse by other services, Host-initiated sends, extra webhook fields | `references/connecting-accounts.md` |
| Meta app, dashboard, tokens, webhook fields and subscriptions, testers (both Platforms) | `references/meta-app-setup.md` |
| Something fails, or proving it works | `references/testing-and-troubleshooting.md` |
| Multi-step forms, intakes, Scores | `wappa-conversational-scores` skill |
| Caches, Redis, TTL, Postgres, where data lives | `wappa-state-and-storage` skill |
| Many Inboxes, Inbox Directory, plugins, SSE, external webhooks, upgrading Wappa | `wappa-host-integration` skill |
| Reminders, timers, recurring jobs, heartbeats, crons | `wappa-scheduled-tasks` skill |

**3. Build.** These rules hold in every branch.

- **One code path for every Platform.** Write each shared action once against `self.messenger` and never branch on Platform for it. Shapes follow WhatsApp; Wappa adapts Instagram internally (a caption becomes a follow-up text, a list becomes quick replies, a long text is split).
- **Prebuilt Messengers.** `self.messenger` handles shared actions, with shared capabilities as attributes (`self.messenger.media`). `self.whatsapp` handles WhatsApp-only actions (`.templates`, `send_location_request`, `send_contact_request`) and `self.instagram` Instagram-only ones (`.comments`, `.content`, `.history`). Each is `None` on the other Platform, so guard with `if self.whatsapp:`. Never build or look up capability objects, and never import adapter classes.
- **Explicit targets.** A conversation reply goes to `DirectMessage(inbox_ref=self.inbox_ref, addresses=webhook.user.delivery_addresses())`. A DM to an Instagram commenter goes to `PrivateReply(comment_ref=webhook.comment_ref)`, with text only. There is no `recipient=`. Never send to an ID from another Inbox.
- **One result per send.** Every send returns one `MessageResult`, even when Instagram needs several messages. `success` is true only when every part was accepted, `message_id` is the final part (the media for a media-plus-caption send), and `platform_response["wappa_parts"]` is `{"message_ids": [...], "delivered": n}`. That key is present only when Instagram split the send. Store `message_id` to match later `process_status` webhooks. Classify a result with `message_outcome(result)` (`from wappa.messaging import message_outcome, OperationOutcome`): `ACCEPTED`, `REJECTED`, `INDETERMINATE` or `RATE_LIMITED`. `MessageResult` has no `outcome` field. Acceptance is not delivery. Never retry an `indeterminate` send automatically, and never resend a partly delivered one whole.
- **Limits fail early.** Interactive limits are the strictest across Platforms. A value over a limit raises `ValidationError` when it is built, and an unfit send raises `ValueError` before any call: a title over 20 characters, more than 10 list rows, text over 4096 characters, a caption over 1024, or a media file the Platform can't play. Read the error and fix the input; never catch and swallow it. Limits count characters, except Instagram's per-message split at 1000 UTF-8 bytes, which Wappa handles for you. One deliberate exception: on Instagram a non-PDF document URL is sent as a text with its name and link, not refused.
- **Media.** Send by https URL, by a Media ID from `self.messenger.media.upload(...)` on the same Inbox, or by local `Path`. Wappa never converts media. It refuses a file that doesn't fit before any call. It provides the format facts; the Host picks the file (`references/media-formats.md`).
- **Rate limits.** Wappa waits out short Meta limits and blocks long ones by itself. `rate_limited` comes with `retry_after` (HTTP 429 on the API) and means "try later", never resend in a loop. Instagram's code `4` budget covers the whole Meta app, so a burst in one conversation blocks every account.
- **Users.** `await self.messenger.resolve_platform_user_profile(webhook.user)` returns what the Platform knows: webhook evidence on WhatsApp, plus a Graph lookup of name and username on Instagram. It reports failure as an outcome and never raises. Read `webhook.user` fields directly, never with `getattr(..., None)`. The Host stores and merges the profile.
- **Never.** Call the Graph API yourself (Wappa owns the credentials), branch on Platform for a shared action, put comment logic in `process_message`, or teach anything marked as proposed or a known gap.

**App skeleton.** One handler serves every Platform:

```python
from wappa import Wappa, WappaEventHandler
from wappa.messaging import DirectMessage
from wappa.webhooks import IncomingCommentWebhook, InboundMessageWebhook, StatusWebhook

class Handler(WappaEventHandler):
    async def process_message(self, webhook: InboundMessageWebhook) -> None:
        target = DirectMessage(inbox_ref=self.inbox_ref, addresses=webhook.user.delivery_addresses())
        await self.messenger.send_text("Hi!", target=target)

app = Wappa(cache="redis")          # or "memory" / "json" for development
app.set_event_handler(Handler())
```

Run it with `wappa dev app/main.py`. `wappa init` scaffolds this shape, and `wappa examples` copies working apps.

**Platform checks.** Guard a Platform-only action with `if self.whatsapp:` / `if self.instagram:`. Check `self.messenger.supported_operations` only before an optional shared operation the adapter may lack; an unsupported one raises `UnsupportedOperationError`.

**Event lanes.** Each action goes in the hook that receives its event. Every hook is an `async def` on your `WappaEventHandler` subclass.

| Hook | Receives |
| --- | --- |
| `process_message` | Conversation messages on every Platform, including every button, list, quick-reply and postback selection (`webhook.get_interactive_selection()`), completed WhatsApp Flows, and Instagram reactions (`BaseReactionMessage`) |
| `process_message_update` | Edits and unsends |
| `process_status` | Sent, delivered, read and failed for your sends (Instagram reports only seen) |
| `process_outbound_echo` | Messages the business sent outside Wappa, such as a human replying in the Instagram app. Wappa already drops echoes of its own sends. |
| `process_comment` / `process_mention` | Instagram comments, Live comments and mentions |
| `process_history_sync` | WhatsApp history sync |
| `process_call` | WhatsApp calls |
| `process_system_webhook` | Number, BSUID and marketing-preference changes, standalone referrals, events Wappa ignores |
| `process_inbox_connection` | WhatsApp connection changes (Instagram sends none) |
| `process_error` | Platform error webhooks |
| `process_api_message` / `process_external_event` / `process_scheduled_event` | Wappa's runtime lanes: HTTP API sends, External Webhook Sources, Scheduled Tasks. Check that an Inbox is bound (`self.messenger` set) before sending; see `wappa-host-integration`. |

Past Instagram messages come from `self.instagram.history.read_history(user_id)`.

**4. Verify.** Offline tests drive the real handler with a mocked transport. Live checks follow `references/testing-and-troubleshooting.md` and separate four facts: the callback 200, Meta's acceptance, the status webhook, and what the User saw. Correct at most three times against specific failing evidence. At the cap, report the remaining finding instead of calling the app ready.

## Known gaps

Don't invent these: sending a reaction (`send_reaction` doesn't exist yet; inbound reactions work), Instagram cross-app handover, heart stickers, outbound post sharing, multi-image sends, publishing and insights. Say so and offer the trusted-adapter path in `references/connecting-accounts.md` when the user needs one.
