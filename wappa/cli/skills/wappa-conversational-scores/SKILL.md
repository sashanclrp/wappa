---
name: wappa-conversational-scores
description: Structures plain-Wappa event handlers into injected application Scores and host-owned Conversational Flows (guided forms, intakes, questionnaires) over WhatsApp or Instagram, with button, list, quick-reply and postback selections, validation, branching, resume, cancel and stale-action handling. Use when splitting a big process_message, adding a multi-step form or intake, routing selections, or designing Score dependencies in a Wappa app. In a Symphonai app, defers to Symphonai's own Score and StateHandler engine (develop-symphonai).
---

# Wappa conversational handlers

Wappa has no Score engine or registry. A Score is application code: a small class with injected dependencies that decides whether it owns an event and acts on it. Don't import `ScoreBase` from `wappa`; define it in the app.

**Symphonai Host?** If the repo imports `symphonai`, it already has a Score engine and StateHandlers: follow its `develop-symphonai` skill and don't recreate them with plain-Wappa Scores. Sends there use Symphonai's targets (`self.deps.user_target`).

## Shape

```python
from dataclasses import dataclass
from wappa import WappaEventHandler
from wappa.messaging import DirectMessage, IMessenger
from wappa.messaging.whatsapp import WhatsAppMessenger
from wappa.domain.interfaces.cache_factory import ICacheFactory

@dataclass(frozen=True)
class ScoreContext:                     # dependency injection, built per event
    messenger: IMessenger               # self.messenger: every shared action
    whatsapp: WhatsAppMessenger | None   # self.whatsapp: WhatsApp-only extras, None elsewhere
    cache_factory: ICacheFactory        # already scoped to (Inbox, User)
    target: DirectMessage

class Handler(WappaEventHandler):
    def _ctx(self, webhook) -> ScoreContext:
        target = DirectMessage(inbox_ref=self.inbox_ref, addresses=webhook.user.delivery_addresses())
        return ScoreContext(self.messenger, self.whatsapp, self.cache_factory, target)

    async def process_message(self, webhook):            # text, media, every selection
        ctx = self._ctx(webhook)
        for score in (FormScore(ctx), CommandsScore(ctx), FallbackScore(ctx)):
            if await score.handle(webhook):
                return
```

Rules:

- **Handlers route, Scores decide.** Order Scores from most specific to the fallback; the first that returns `True` stops the chain.
- **One selection read on every Platform.** WhatsApp button and list replies and Instagram quick replies and postbacks all arrive in `process_message`; `webhook.get_interactive_selection()` returns the chosen `ReplyButton.id` / `ListRow.id`. A completed WhatsApp Flow arrives there too: `get_interactive_selection()` returns its `flow_token` and `webhook.message.interactive.nfm_reply.response` holds the decoded answers. There is no separate interaction hook.
- **Send with the injected target.** Use `ctx.target`. Never send to an ID from another Inbox, or to a commenter's ID.
- **One method per prompt, not per Platform.** `send_button_message` (≤ 3 options), `send_list_message` (more options; quick replies on Instagram) and `send_carousel` work everywhere; the adapter maps them (ADR-0025). Never branch on Platform name; WhatsApp-only extras live on the prebuilt `self.whatsapp` (`send_contact_request`, `send_location_request`, `templates`), which is `None` on other Platforms; the context carries it beside the Messenger. Never look up or build capability objects in a Score.

- **Limits are the strictest across Platforms and fail early.** Button titles and list row titles ≤ 20 characters, 1–3 buttons, ≤ 10 list rows in total, body ≤ 640 (buttons) or 1000 (list), text ≤ 4096. A value over a limit raises `ValidationError` when you build it. Design the step to fit: split a long option list into a category step, move detail into row descriptions. Explain the error to the developer; never truncate titles silently or swallow the error.
- **One result per prompt.** A send returns one `MessageResult`, even when Instagram splits it (`platform_response["wappa_parts"]["message_ids"]` lists the parts). When a step must be tracked (a confirmation, a final summary), store `result.message_id` with the submission in host persistence and match it in `process_status` (the `StatusWebhook` fields are in `wappa-apps`, messaging reference). Classify a failure with `message_outcome(result)`: on `RATE_LIMITED` tell the User to try later, and never retry an `INDETERMINATE` send automatically.

## Guided flow (intake) recipe

The full worked flow, with tests, is in `references/intake-flow.md`. Key policy:

1. Keep flow state in `cache_factory.create_state_cache()` under one key with a TTL (see `wappa-state-and-storage`).
2. Put the step in every option id (`form:<step>:<value>`). When a payload's step doesn't match the current step, it's a stale tap: re-prompt and don't apply it.
3. Validate typed answers (length, email regex) and re-prompt on failure. Typed text matching an option title counts as that option.
4. Branch on the answer (for example, `other` leads to an extra question).
5. Starting the flow while it's active resumes it and repeats the current question.
6. `cancel` deletes the state. `restart` resets it. A repeated confirm after completion says it was already submitted.
7. On completion, write the business record to host persistence, not to the flow state, then mark the flow done.

These are your policies, not Wappa behavior. Document them for your users.

## Verify

Test the Score with a recording `IMessenger` fake (implement `platform`, `inbox_id`, `resolve_platform_user_profile` (return `PlatformUserProfile.from_evidence(self.platform, user)`) and the sends you use, each returning `MessageResult(success=True, platform=self.platform, message_id="m1")`; `from wappa.messaging import MessageResult, PlatformUserProfile`) plus Wappa's real memory cache: `create_cache_factory("memory")(inbox_id=ref.cache_namespace, user_id=...)`. Cover validation, branching, a stale tap, resume, cancel, completion and two concurrent Users in two Inboxes. See `references/intake-flow.md`.
