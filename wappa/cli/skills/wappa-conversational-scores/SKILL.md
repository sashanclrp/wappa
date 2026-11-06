---
name: wappa-conversational-scores
description: Structures plain-Wappa event handlers into injected application Scores and host-owned Conversational Flows (guided forms, intakes, questionnaires) over WhatsApp or Instagram, with button, list, quick-reply and postback selections, validation, branching, resume, cancel and stale-action handling. Use when splitting a big process_message, adding a multi-step form or intake, routing selections, or designing Score dependencies in a Wappa app. In a Symphonai app, routes to symphonai-add-score or symphonai-add-state-handler instead.
---

# Wappa conversational handlers

Wappa has no Score engine or registry. A Score is application code: a small class with injected dependencies that decides whether it owns an event and acts on it. Don't import `ScoreBase` from `wappa`; define it in the app.

**Symphonai Host?** If the repo imports `symphonai`, use `symphonai-add-score` (per-message rules) or `symphonai-add-state-handler` (guided multi-turn flows) and stop here. If those skills are missing, name them, say they ship with Symphonai, and don't recreate their engine.

## Shape

```python
from dataclasses import dataclass
from wappa import WappaEventHandler
from wappa.messaging import DirectMessage, IMessenger
from wappa.domain.interfaces.cache_factory import ICacheFactory

@dataclass(frozen=True)
class ScoreContext:                     # dependency injection, built per event
    messenger: IMessenger
    cache_factory: ICacheFactory        # already scoped to (Inbox, User)
    target: DirectMessage

class Handler(WappaEventHandler):
    def _ctx(self, user_id: str) -> ScoreContext:
        return ScoreContext(self.messenger, self.cache_factory,
                            DirectMessage(inbox_ref=self.inbox_ref, addresses=DeliveryAddresses.of(user_id)))

    async def process_message(self, webhook):            # text, media, every selection
        ctx = self._ctx(webhook.user.user_id)
        for score in (FormScore(ctx), CommandsScore(ctx), FallbackScore(ctx)):
            if await score.handle(webhook):
                return
```

Rules:

- **Handlers route, Scores decide.** Order Scores from most specific to the fallback; the first that returns `True` stops the chain.
- **One selection read on every Platform.** WhatsApp button and list replies and Instagram quick replies and postbacks all arrive in `process_message`; `webhook.get_interactive_selection()` returns the chosen `ReplyButton.id` / `ListRow.id`. A completed WhatsApp Flow arrives there too: `get_interactive_selection()` returns its `flow_token` and `webhook.message.interactive.nfm_reply.response` holds the decoded answers. There is no separate interaction hook.
- **Send with the injected target.** Use `ctx.target`. Never send to an ID from another Inbox, or to a commenter's ID.
- **One method per prompt, not per Platform.** `send_button_message` (≤ 3 options), `send_list_message` (more options; quick replies on Instagram) and `send_carousel` work everywhere; the adapter maps them (ADR-0025). Never branch on Platform name; check `messenger.supported_operations` once only for WhatsApp-only extras (`send_contact_request`, `send_location_request`).

## Guided flow (intake) recipe

The full worked flow, with tests, is in `references/intake-flow.md`. Key policy:

1. Keep flow state in `cache_factory.create_state_cache()` under one key with a TTL (see `wappa-runtime-state`).
2. Put the step in every option id (`form:<step>:<value>`). When a payload's step doesn't match the current step, it's a stale tap: re-prompt and don't apply it.
3. Validate typed answers (length, email regex) and re-prompt on failure. Typed text matching an option title counts as that option.
4. Branch on the answer (for example, `other` leads to an extra question).
5. Starting the flow while it's active resumes it and repeats the current question.
6. `cancel` deletes the state. `restart` resets it. A repeated confirm after completion says it was already submitted.
7. On completion, write the business record to host persistence, not to the flow state, then mark the flow done.

These are your policies, not Wappa behavior. Document them for your users.

## Verify

Test the Score with a recording `IMessenger` fake (implement `platform`, `inbox_id`, `resolve_platform_user_profile` (return `PlatformUserProfile.from_evidence(self.platform, user)`) and the sends you use) plus Wappa's real memory cache: `create_cache_factory("memory")(inbox_id=ref.cache_namespace, user_id=...)`. Cover validation, branching, a stale tap, resume, cancel, completion and two concurrent Users in two Inboxes. See `references/intake-flow.md`.
