# Expiry Context — Architecture

## Responsibilities

This context owns:
- Subscribing to Redis keyspace notifications (`__keyevent@{db}__:expired`)
- Parsing expired Expiry Keys into structured `ExpiryEvent` objects
- Routing each event to the correct registered handler via `ExpirationHandlerRegistry`
- Dispatching handlers as fire-and-forget async tasks with completion logging
- Wrapping each dispatch in an SSE identity scope so SSE events emitted from handlers carry coherent `inbox_id` / user identity
- Reconnecting to Redis on connection loss with exponential backoff
- Providing helper factories (`create_expiry_messenger`, `create_expiry_cache_factory`) that bootstrap framework dependencies for use inside expiry handlers
- Holding a reference to the host `FastAPI` app via `AppContext` so handlers can reach shared HTTP session state

## Explicit Boundaries

This context does **not** own:
- Business logic executed when a key expires (that lives in host application handlers)
- Writing or TTL-setting of Expiry Keys (callers use `KeyFactory.trigger()` from `wappa.persistence.redis`)
- Redis pool management or connection pooling (delegated to `RedisClient` / `PoolAlias`)
- SSE channel management or event schemas (delegated to `wappa.core.sse`)
- Cache namespace rules or user-cache schemas (delegated to `wappa.persistence`)
- Messenger credentials or API client construction (delegated to `MessengerFactory`)

## Module Structure

```
wappa/core/expiry/
├── __init__.py          # Public surface: re-exports all key types and singletons
├── listener.py          # Orchestrator: run_expiry_listener(), _run_listener_loop()
├── registry.py          # ExpirationHandlerRegistry singleton (expiry_registry)
├── parser.py            # ExpiryEventParser + ExpiryEvent dataclass
├── dispatcher.py        # ExpiryDispatcher — fire-and-forget task creation + SSE scope
├── connection.py        # RedisConnectionManager, RedisConnection, ConnectionConfig
├── reconnection.py      # ReconnectionStrategy, ReconnectionConfig (exponential backoff)
├── app_context.py       # AppContext singleton, set_fastapi_app() / get_fastapi_app()
└── context_helpers.py   # create_expiry_messenger(), create_expiry_cache_factory(),
                         # parse_tenant_from_expired_key()
```

## Key Classes and Their Roles

| Class / Symbol | Role |
|---|---|
| `run_expiry_listener` | Entry point. Instantiates all components and drives the reconnect loop. |
| `ExpirationHandlerRegistry` | Stores `action_name → async handler` mappings. Provides `@on_expire_action` decorator and `resolve(expired_key)` lookup. Global singleton `expiry_registry`. |
| `ExpiryEventParser` | Decodes raw pub/sub messages; delegates key resolution to `registry.resolve()`. Returns `ExpiryEvent` or `None`. |
| `ExpiryEvent` | Immutable data container: `expired_key`, `handler`, `identifier`, `action`. |
| `ExpiryDispatcher` | Creates an `asyncio.Task` per event via `_run_with_sse_scope`. Logs completion or errors via done-callback. |
| `RedisConnectionManager` | Obtains a Redis client from the pool, enables `notify-keyspace-events=Ex`, creates and manages a PubSub subscription. |
| `ReconnectionStrategy` | Tracks failure count, computes `base_delay × 2^(n-1)` (capped at `max_delay`), exposes `should_retry()` and `async wait()`. |
| `AppContext` | Module-level singleton holding a `FastAPI` reference; accessed by context helpers to reach `app.state.http_session`. |

## Design Patterns

- **Orchestrator + Components**: `run_expiry_listener` composes `RedisConnectionManager`, `ExpiryEventParser`, `ExpiryDispatcher`, and `ReconnectionStrategy` without owning any of their logic.
- **Registry / Decorator**: `ExpirationHandlerRegistry.on_expire_action` follows the familiar decorator-registration pattern, keeping handler registration co-located with business code.
- **Longest-prefix matching**: `_best_match` allows hierarchical action namespaces if needed (e.g., `payment_reminder:urgent` is more specific than `payment_reminder`).
- **Fire-and-forget with observability**: `asyncio.create_task` keeps the listener loop non-blocking; done-callbacks provide error visibility without coupling listener to handler lifetimes.
- **Singleton context**: `AppContext` and `expiry_registry` are module-level singletons — the only acceptable globals — to avoid threading global state through every call site.

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
ExpiryEventParser.parse(message)                [parser.py]
        │  delegates to registry.resolve(expired_key)
        ├─── No handler → None → listener loop ignores
        │
        │  ExpiryEvent(expired_key, handler, identifier, action)
        ▼
ExpiryDispatcher.dispatch(event)                [dispatcher.py]
        │  asyncio.create_task(_run_with_sse_scope(event))
        ▼
_run_with_sse_scope                             [dispatcher.py]
        │  parse_tenant_from_expired_key → inbox_id
        │  classify_meta_identifier → bsuid / phone
        │  sse_event_scope(inbox_id, user_id, …)
        ▼
event.handler(identifier, expired_key)          [host application handler]
        │  optionally calls create_expiry_messenger / create_expiry_cache_factory
        ▼
done-callback: _on_completion logs success or error
```

On connection loss, `run_expiry_listener` calls `reconnection.record_failure()` and `await reconnection.wait()` before restarting `_run_listener_loop`, up to `max_attempts` (default: infinite).
