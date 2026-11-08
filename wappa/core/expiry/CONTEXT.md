# Expiry Context — Glossary

Terms specific to the `wappa.core.expiry` bounded context. Shared Wappa kernel terms (`inbox_id`, `Inbox`, `Host Application`, etc.) are defined in the root `CONTEXT.md` and are not repeated here.

| Term | Definition |
|---|---|
| **Expiry Action** | The name a Host gives a timer. When its Redis Expiry Key expires, Wappa delivers it to `process_scheduled_event` as `ScheduledEvent.action`. |
| **Expiry Key** | A Redis key with a TTL whose sole purpose is to trigger an Expiry Action. Format: `{inbox_namespace}:EXPTRIGGER:{action}:{identifier}`. The namespace is decoded by Wappa into `InboxRef`; invalid namespaces are rejected. The key carries no payload; all routing information lives in its name. |
| **Trigger Prefix** | The literal segment `EXPTRIGGER` that marks a Redis key as an Expiry Key and distinguishes it from operational cache keys. |
| **Action Name** | The third colon-segment of an Expiry Key (e.g., `payment_reminder`). The Host's hook routes on it. |
| **Identifier** | The fourth colon-segment of an Expiry Key: an opaque value such as a User or a message ID, delivered as `ScheduledEvent.identifier`. Wappa never reads a User from its shape. |
| **Expiry Notification** | The parsed form of a Redis keyspace notification: the expired key, its `InboxRef`, action and identifier. Produced by `parse_expiry_notification`, consumed by `ExpiryDispatcher`. |
| **Expiry Subject Binding** | The Host's mapping from an action and identifier to the subject User, or to `None` for Inbox-only work. Raising marks the action unknown: the failure is logged and the hook does not run. |
| **Keyspace Notification** | A Redis pub/sub message on `__keyevent@{db}__:expired` that fires when any key in that database expires. The expiry listener subscribes to this channel. |
| **Expiry Listener** | The long-running async task (`run_expiry_listener`) that subscribes to Redis keyspace notifications and orchestrates the parse → dispatch pipeline. |

| **Expiry Occurrence** | One arming generation and its intended due time; renewal creates a replacement occurrence. |
| **Recovered Expiry** | An overdue indexed occurrence admitted after its Expiry Key is gone, possibly late or repeated. The Host keeps business effects idempotent. |
| **Expiry Due Index** | Pending occurrences discoverable by due/eligibility time without enumerating all Expiry Keys. |
