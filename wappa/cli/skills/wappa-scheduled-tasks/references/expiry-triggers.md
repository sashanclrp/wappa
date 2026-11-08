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
| Raises | Logged with the action and identifier; the hook does not run; an indexed occurrence remains pending for retry |
| No binding configured | Every expiry is Inbox scope, so `self.user_id` is `None` |

Every valid trigger reaches the hook, so make unknown actions loud in the binding or the hook's `case _`. `event.source` is `"redis_expiry"`, while `event.payload` remains empty. Indexed occurrences carry the generation as event.execution_id and original UTC due time as event.scheduled_for. Unindexed pre-upgrade notifications have neither.

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

Redis expiry delivery is at least once across Wappa process restarts while Redis retains its data. set/renew atomically writes the TTL key and a durable pending due index in the existing expiry pool (logical DB 3). Pub/Sub gives prompt notification; startup recovery and two-second ticks find indexed overdue entries whose key is gone, at most 100 admissions/in-flight indexed handlers per process with bounded sorted-set reads. No KEYS scans are needed, and a Host sweep per action is unnecessary.

- Indexed events use the same subject binding and scheduled hook. event.metadata["recovered"] is true for index recovery and false for Pub/Sub; expired_key remains available. The flag describes the path, not an exactly-once guarantee.
- A success acknowledges only its original generation. Raised handler/binding failures, process interruption and acknowledgment failure leave the occurrence pending. A 30-second claim deadline allows recovery; long handlers may be delivered concurrently in another worker. Keep Host business and side-effect fences, and let unknown-action errors stay loud until fixed or explicitly cancelled.
- Store business data in your own cache/database. The pending index is Wappa-owned, not an execution-history store. Do not delete its __system__:expiry:due or __system__:expiry:records keys as ordinary cache cleanup.
- Cancel removes pending work even if the TTL key is already gone. Its return value still counts removed TTL keys. Rebind moves a live key plus its due entry, retaining due time/generation, and refuses a live or pending overdue destination. Cancellation cannot undo already admitted work.
- Startup enables notify-keyspace-events Ex. If a managed Redis forbids CONFIG SET, configure that for prompt notifications; index recovery itself does not depend on notifications or a healthy Pub/Sub connection. The source starts after ordinary capability/Host startup hooks, at priority 95.
- Pre-upgrade armed keys have no index entry. Their live notifications still dispatch, but missed expirations cannot be reconstructed. Re-arm keys needing recovery; rebinding a still-live legacy key also indexes its remaining TTL. The guarantee assumes Redis data is retained.

Record a Host idempotency fence within the action before side effects. Include the task's business generation; an indexed event's execution_id supplies occurrence correlation, not permission to ignore current business state. Old unindexed notifications require your existing generation policy. If you claim before a side effect, release or otherwise repair the claim after failure so recovery can do useful work.

The full project is `wappa examples` → `wappa_expiry_example`.
