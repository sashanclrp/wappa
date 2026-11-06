# Intake flow (worked example)

## Contents

- State model
- Handling an event
- Prompts per step
- Tests

## State model

```python
from pydantic import BaseModel, Field

class FormState(BaseModel):
    step: str = "name"            # name → service → [details] → budget → email → confirm → done
    answers: dict[str, str] = Field(default_factory=dict)

STATE_KEY, TTL = "form_intake", 1800

async def load(state_cache) -> FormState | None:
    raw = await state_cache.get(STATE_KEY)
    return FormState.model_validate(raw) if raw else None

async def save(state_cache, state: FormState) -> None:
    await state_cache.upsert(STATE_KEY, state.model_dump(), ttl=TTL)
```

## Handling an event

```python
def parse(option_id: str | None) -> tuple[str, str] | None:
    if not option_id or not option_id.startswith("form:"):
        return None
    _, step, value = option_id.split(":", 2)
    return step, value

async def handle(self, event) -> bool:
    state = await load(self.state_cache)
    parsed = parse(event.get_interactive_selection())   # any button, list row, quick reply or postback
    if state is None or state.step == "done":
        if parsed:                                      # old button after completion
            await self.say("That form was already submitted. Send /form to start again.")
            return True
        return False
    text = (event.get_message_text() or "").strip()
    if text.lower() == "cancel":
        await self.state_cache.delete(STATE_KEY)
        await self.say("Cancelled. Nothing was saved.")
        return True
    if parsed and parsed[0] != state.step:              # stale tap
        await self.say("That option belongs to an earlier question:")
        await self.prompt(state)
        return True
    value = parsed[1] if parsed else text
    # validate value for state.step, update answers, advance step, save, prompt
    return True
```

## Prompts per step

One method per step on every Platform (ADR-0025); the adapter maps it.

| Step | Method | Instagram renders | WhatsApp renders |
| --- | --- | --- | --- |
| choose one of ≤ 3 | `send_button_message` with `ReplyButton`s | button template (postbacks) | reply buttons |
| choose one of ≤ 10 | `send_list_message` with `ListSection`/`ListRow` (row title ≤ 20) | quick replies (descriptions dropped) | list |
| open a URL | `send_cta_message` | button template with one URL button | CTA URL button |
| summary + confirm | `send_button_message` with two `ReplyButton`s (optional `InteractiveHeader` image) | the image first, then the button template | reply buttons with an image header |
| email/phone | ask for typed text | typed text | typed text, or `send_contact_request` if `supported_operations` lists it |

Selections from every row come back through `event.get_interactive_selection()`. Check `messenger.supported_operations` once for WhatsApp-only extras; don't try operations and catch exceptions as a control flow.

## Tests

```python
factory = create_cache_factory("memory")(inbox_id=REF.cache_namespace, user_id="u1")
form = FormScore(ScoreContext(Recorder(REF), factory, DirectMessage(inbox_ref=REF, addresses=DeliveryAddresses.of("u1"))))
await form.start()
await form.handle(text_event("A"))            # invalid name → re-prompt
await form.handle(quick_event("form:service:other"))
await form.handle(quick_event("form:service:website"))   # stale at the next step → re-prompt
```

Run three flows through `asyncio.gather` (two Users in Inbox A, plus the same User ID in Inbox B) and assert that each submission and each recipient stays in its own Inbox. The sibling example `instagram_conversations_example/tests/test_form_intake.py` in the Wappa examples repo is a complete version.
