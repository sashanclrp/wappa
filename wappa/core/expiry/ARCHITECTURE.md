# Expiry Context — Architecture

## Responsibilities

This context owns:
- Subscribing to Redis keyspace notifications (`__keyevent@{db}__:expired`)
- Parsing expired Expiry Keys into `ExpiryNotification` objects
- Asking the Host's `ExpirySubjectBinding` whether the identifier is a User
- Running the resulting `ScheduledEvent` as tracked background work, with failures logged
- Reconnecting to Redis on connection loss with exponential backoff

## Explicit Boundaries

This context does **not** own:
- Business logic when a key expires (the Host's `process_scheduled_event`)
- Context construction: Messengers, caches, database factories and SSE scope (delegated to `DispatchContextBuilder.scope`, through `wappa.core.scheduling`)
- Writing or TTL-setting of Expiry Keys (the Host uses `cache_factory.create_expiry_cache()`)
- Redis pool management or connection pooling (delegated to `RedisClient` / `PoolAlias`)
- Plugin lifecycle (delegated to `SchedulingPlugin`)
- Delivery guarantees beyond Redis Pub/Sub: no replay, claims, leases, due indexes or history. Every listening process receives each notification, and a key that expires while none listens is missed. Stronger coordination belongs to the Host.

## Module Structure

```
wappa/core/expiry/
├── __init__.py          # Public surface of this context
├── listener.py          # Orchestrator: run_expiry_listener(), _run_listener_loop()
├── parser.py            # parse_expiry_notification() + ExpiryNotification dataclass
├── dispatcher.py        # ExpiryDispatcher: notification → ScheduledEvent on tracked work;
│                        #   ExpirySubjectBinding protocol
├── connection.py        # RedisConnectionManager, RedisConnection, ConnectionConfig
└── reconnection.py      # ReconnectionStrategy, ReconnectionConfig (exponential backoff)
```

## Key Classes and Their Roles

| Class / Symbol | Role |
|---|---|
| `run_expiry_listener` | Entry point. Drives the reconnect loop and hands each parsed notification to the dispatcher. |
| `parse_expiry_notification` | Decodes raw pub/sub messages. Ignores keys that are not triggers; logs and drops a trigger with an invalid Inbox namespace. |
| `ExpiryNotification` | Immutable data container: `expired_key`, `inbox_ref`, `action`, `identifier`. |
| `ExpirySubjectBinding` | Host-supplied async mapping to the subject User or `None`. Absent, every expiry is Inbox-only work. |
| `ExpiryDispatcher` | Tracks one task per notification, builds the `ScheduledEvent` and logs a failure from a done-callback, since no caller awaits it. |
| `RedisConnectionManager` | Obtains a Redis client from the pool, enables `notify-keyspace-events=Ex`, creates and manages a PubSub subscription. |
| `ReconnectionStrategy` | Tracks failure count, computes `base_delay × 2^(n-1)` (capped at `max_delay`), exposes `should_retry()` and `async wait()`. |

## Data Flow

```
Redis TTL expires
        │
        ▼
__keyevent@{db}__:expired  (pub/sub channel)
        │
        ▼
RedisConnectionManager.pubsub.listen()          [connection.py]
        │  raw message dict
        ▼
parse_expiry_notification(message)              [parser.py]
        │  not a trigger or invalid namespace → None → listener ignores
        │  ExpiryNotification(expired_key, inbox_ref, action, identifier)
        ▼
ExpiryDispatcher.dispatch(notification)         [dispatcher.py]
        │  BackgroundWorkTracker.track(...)
        ▼
ExpirySubjectBinding(inbox_ref, action, identifier) → User or None   [Host]
        │  ScheduledEvent(source="redis_expiry", ...)
        ▼
Scheduling.run(event)                           [wappa/core/scheduling]
        │  DispatchContextBuilder.scope: canonical User, Messenger, caches, SSE
        ▼
handler.handle_scheduled_event(event) → process_scheduled_event   [Host]
        │
        ▼
done-callback: failure logged with action and identifier
```

On connection loss, `run_expiry_listener` calls `reconnection.record_failure()` and `await reconnection.wait()` before restarting `_run_listener_loop`, up to `max_attempts` (default: infinite).
