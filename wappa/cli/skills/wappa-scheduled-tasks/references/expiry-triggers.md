# Redis expiry triggers

A timer is a Redis key with a TTL. When it expires, Wappa delivers the action to your hook. Redis only: memory and JSON caches raise `NotImplementedError` from `create_expiry_cache()`.

## Contents

- Setup and the subject binding
- Arm, renew, cancel, read
- Rebinding after an identity change
- Delivery

## Setup and the subject binding

```python
from wappa import InboxRef, ScheduledEvent, SchedulingPlugin, Wappa
from wappa.domain.messaging_targets import DeliveryAddresses, DirectMessage

USER_KEYED = {"followup", "message_sync"}
MESSAGE_KEYED = {"template_rollback"}


async def expiry_subject(*, inbox_ref: InboxRef, action: str, identifier: str) -> str | None:
    if action in USER_KEYED:
        return identifier
    if action in MESSAGE_KEYED:
        return None
    raise LookupError(f"Unknown expiry action: {action}")


app = Wappa(cache="redis")
app.add_plugin(SchedulingPlugin(redis_expiry=True, expiry_subjects=expiry_subject))


# On your handler:
async def process_scheduled_event(self, event: ScheduledEvent) -> None:
    match event.action:
        case "followup":                       # User scope: Messenger and User cache ready
            await self.messenger.send_text(
                target=DirectMessage(
                    inbox_ref=self.inbox_ref, addresses=DeliveryAddresses.of(self.user_id)
                ),
                text="Still there?",
            )
        case "template_rollback":              # Inbox scope: no User, no cache_factory
            await roll_back(self.db, wamid=event.identifier)
```

The binding is the only place that decides whether an identifier is a User, because the key can't say. It maps identity and nothing else.

| Binding result | What happens |
| --- | --- |
| A User | Your resolver canonicalizes it, then the hook runs in User scope |
| `None` | The hook runs in Inbox scope |
| Raises | Logged with the action and identifier; the hook doesn't run and the trigger is gone |
| No binding configured | Every expiry is Inbox scope, so `self.user_id` is `None` |

Every valid trigger reaches the hook, so make unknown actions loud in the binding or the hook's `case _`. `event.source` is `"redis_expiry"`, while `event.payload` is always empty and `event.execution_id` is always `None`.

Inbox-scope work has no `self.cache_factory`. To reach a User's cache or re-arm a timer from there, open `self.scope(user_id=...)` once you know the User.

## Arm, renew, cancel, read

On `self.cache_factory.create_expiry_cache()`:

| Call | Effect |
| --- | --- |
| `await expiry.set(action, identifier, ttl_seconds)` | Create, or renew with a new TTL |
| `await expiry.delete(action, identifier)` | Cancel; returns the number removed |
| `await expiry.delete_all_by_identifier(identifier)` | Cancel every action for that identifier |
| `await expiry.exists(action, identifier)` | Still armed? |
| `await expiry.get_ttl(action, identifier)` | Seconds left; negative once gone |

`set` always renews, so a debounce re-arms on every message. If you need a ceiling, keep the first-seen time in your cache and shorten the TTL yourself. A colon in an action or identifier becomes `_` in the key and comes back that way in `event.identifier`. Avoid colons in identifiers you look up later, and namespace actions with an underscore (`app_followup`).

## Rebinding after an identity change

```python
from wappa.scheduling import ExpiryKeyConflictError

try:
    await expiry.rebind("followup", old_user_id, new_user_id)
except ExpiryKeyConflictError:
    ...  # a trigger exists under the new id; both are unchanged, so you decide which to keep
```

The trigger keeps its remaining TTL and fires under the new identifier. Call it once per action you arm. It returns `False` if nothing was armed. It only moves Wappa's keys: rows in your scheduler and other business keys are yours to migrate.

## Delivery

These are Redis Pub/Sub messages, the same as before 0.34:

- A key that expires while no Wappa process listens is never seen.
- Every listening process receives each one. With several workers, let one win, using a key that includes a generation you bump each time you arm a re-armable timer:

  ```python
  from wappa.persistence import TableRowTransition

  claim = await scoped.cache_factory.create_table_cache().create_if_absent(
      "expiry_claims", f"{event.action}:{event.identifier}:{generation}", {"at": event.dispatched_at.isoformat()}, ttl=3600
  )
  if claim.transition is not TableRowTransition.CREATED:
      return                                     # another worker has it
  ```

  Inbox-scope work has no cache factory, so use `self.scope(...)` as above or a unique row in your database.
- The key is gone when the hook runs, so `exists` returns `False` for the trigger that fired.
- Startup enables `notify-keyspace-events Ex`. A managed Redis that forbids `CONFIG SET` needs that applied by hand.
- Triggers live in the existing expiry pool, logical DB 3 by default.

The full project is `wappa examples` → `wappa_expiry_example`.
