---
name: wappa-instagram-apps
description: Builds, extends and tests Instagram conversation apps on the Wappa library — DMs with media, quick replies, buttons, cards and carousels, public and Live comments, private replies, comment controls, mentions, post/comment reads, Unified Login connection and extension fields. Use when the user wants an Instagram bot or inbox on Wappa, asks about Meta Instagram webhook/app setup for Wappa, `/webhook/inboxes/instagram`, PrivateReply, reply_comment, comment moderation primitives, or connecting Instagram professional accounts. Not for WhatsApp Templates or other WhatsApp-only work.
---

# Instagram apps with Wappa

Wappa owns the Platform mechanism (signed intake, typed events, sends, comment controls, reads, credentials). The app owns policy: which events trigger work, what to say, moderation, AI, human takeover and business records. Never put app policy into Wappa or invent Wappa APIs.

## Workflow

```
Progress:
- [ ] 1. Inspect: Wappa version, Host (plain Wappa or Symphonai), task
- [ ] 2. Route to one branch below (load only its reference)
- [ ] 3. Build with public imports only
- [ ] 4. Verify offline, then controlled live; report evidence and limits
```

**1. Inspect.** Run `uv run python -c "import wappa, wappa.messaging as m; print(wappa.__version__, hasattr(m, 'PrivateReply'))"`. `False` means the installed Wappa predates the Instagram conversation contract: say so and stop rather than teaching APIs it lacks. A repo with `symphonai` imports is a Symphonai Host; read `references/skill-routing.md` before writing code.

**2. Route.**

| Request | Reference |
| --- | --- |
| Meta app, dashboard, tokens, webhook fields, testers | `references/meta-app-setup.md` |
| Text, media send/receive, location/contact/sticker, `IMediaLibrary` upload/download, `mark_as_read` | `references/text-and-media.md` |
| Buttons, lists (quick replies), carousels, selections, comments, mentions, private/public replies, controls, post reads | `references/interactions-and-comments.md` |
| Self-service login, multiple accounts, token reuse by other services, extra webhook fields | `references/unified-login-and-extensions.md` |
| Something fails, or proving it works | `references/testing-and-troubleshooting.md` |
| Multi-step flows or Scores | hand off to `wappa-conversational-scores` |
| Cache, Redis, TTL, per-User state | hand off to `wappa-runtime-state` |

**3. Build.** Core facts every branch relies on:

- Instagram needs explicit Inbox routing (`InboxRoutingMode.EXPLICIT`) with a Host `IInboxDirectorySource` serving Wappa-encrypted `InstagramActiveInboxCredentialRecord`s. Wappa reads no `IG_*` environment variable.
- One callback: `/webhook/inboxes/instagram`, separate from WhatsApp. `META_APP_SECRET` authenticates POST bytes; `WP_WEBHOOK_VERIFY_TOKEN` answers only the GET challenge.
- Every send takes a target: `DirectMessage(inbox_ref=self.inbox_ref, addresses=webhook.user.delivery_addresses())` or, for a comment, `PrivateReply(comment_ref=webhook.comment_ref)` (text only). There is no `recipient=`.
- Hooks: `process_message` (also every quick-reply and postback selection, read with `webhook.get_interactive_selection()`, and reactions as `InstagramReactionMessage`), `process_message_update` (edits/deletions), `process_outbound_echo` (messages sent from the Instagram app or another tool; Wappa already drops echoes of its own sends), `process_inbox_connection` (WhatsApp only: Unified Login sends no deauthorize callback, so revoke an Instagram Inbox by deactivating its record and calling `connector.disconnect`), `process_comment`, `process_mention`, `process_status` (seen), `process_system_webhook` (standalone referrals, ignored events). Echoes never re-enter `process_message`. Past messages: `messenger.require_capability(IConversationHistoryReader).read_history(user_id)`.
- One Messenger method per action on every Platform (ADR-0016): `mark_as_read`, `send_button_message`, `send_list_message`, `send_cta_message`, `send_carousel`, `send_location`, `send_contact`, `send_sticker`; the adapter maps each onto Instagram (captions become a follow-up text). Never branch on Platform name.
- Check `self.messenger.supported_operations` once before an optional operation (`send_location_request` and `send_contact_request` are WhatsApp-only); unsupported ones raise `UnsupportedOperationError`. Media upload/download is the shared `IMediaLibrary` capability. Instagram-only actions are focused capabilities from `self.messenger.require_capability(ICommentControls | IConversationContentReader)`; public `reply_comment` lives on `ICommentControls`.
- Outcomes are accepted / rejected / indeterminate. Acceptance is not delivery. Never retry an indeterminate send or destructive control automatically.

**4. Verify.** Offline tests drive the real handler with a mocked Graph transport; live checks follow `references/testing-and-troubleshooting.md`. Correct at most three times against specific failing evidence; at the cap, report the remaining finding instead of calling the app ready.

## Excluded on purpose

Cross-app handover, heart stickers, outbound post sharing, multi-image sends, history sync, publishing and insights (extension-owned). If asked, say so and offer the trusted-adapter path in `references/unified-login-and-extensions.md`.

Sending a reaction is a known gap: there is no `send_reaction` yet, so don't invent the method. Inbound reactions work (`BaseReactionMessage`: `target_message_id`, `emoji`, `is_removal`).
