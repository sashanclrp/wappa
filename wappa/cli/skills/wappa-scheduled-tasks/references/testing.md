# Testing scheduled work

Test your routing and side effects through the real hook. You need no scheduler and no running server.

## Calling the hook directly

Bind a fake context with `with_context`, then call the template method the runtime calls:

```python
import asyncio
from unittest.mock import AsyncMock

from wappa import InboxRef, ScheduledEvent, WappaEventHandler


class Handler(WappaEventHandler):
    async def process_message(self, webhook) -> None:
        return None

    async def process_scheduled_event(self, event: ScheduledEvent) -> None:
        if event.action == "appointment_reminder":
            await self.messenger.send_text(text=event.payload["text"], target=None)


async def reminder_sends_through_the_prepared_messenger() -> None:
    inbox = InboxRef.whatsapp("111")
    messenger = AsyncMock()
    messenger.platform = None                  # no Platform Messenger on this fake
    bound = Handler().with_context(
        inbox_id=inbox.inbox_id,
        inbox_ref=inbox,
        user_id="user-1",
        messenger=messenger,
        cache_factory=None,
    )
    await bound.handle_scheduled_event(
        ScheduledEvent(
            action="appointment_reminder",
            source="test",
            inbox_ref=inbox,
            user_id="user-1",
            payload={"text": "See you at 3"},
        )
    )
    messenger.send_text.assert_awaited_once()


asyncio.run(reminder_sends_through_the_prepared_messenger())
```

For a System test, bind `inbox_id=None`, `user_id=None`, `messenger=None` and `cache_factory=None`, and omit `inbox_ref`. For an Inbox test, bind `user_id=None` and `cache_factory=None`. A branch using the wrong scope then fails. `self.scope` needs the real builder, so cover it in the integration check below.

## What to cover

- One test per action, in the scope it really runs in.
- An unknown action raises.
- Your binding, as a plain async function: a User action, a message-keyed action returning `None`, an unknown action raising.
- Your job body: an exception from `dispatch` propagates.

## One real firing per source

- **Scheduler:** start the app with `async with app.router.lifespan_context(app):`, then `await run_job(...)` directly. This builds the scope and caches without waiting for a schedule; credentials resolve only if the hook uses the Messenger. A send reaches Meta, so use a test recipient or stop it with Messenger middleware.
- **Redis expiry:** start the app with `cache="redis"`, `await expiry.set(action, identifier, 1)`, and wait for the side effect. `uv run python <wappa>/scripts/redis_inspect.py` from a source checkout shows the keys.
- **Failure:** force one exception and confirm it reaches your engine, or for expiry the `Expiry action failed` log line.
