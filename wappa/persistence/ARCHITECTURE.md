# ARCHITECTURE.md — Persistence Bounded Context

Internal structure, responsibilities, and design decisions for the Persistence context.

Cross-references: [root ARCHITECTURE.md](../../../ARCHITECTURE.md) · [CONTEXT.md](CONTEXT.md) · [root CONTEXT.md](../../../CONTEXT.md)

## Responsibilities

This context owns:
- Multi-pool Redis client management (lifecycle, fork-safety, health checks)
- Redis key namespace generation via `KeyFactory`
- Context-bound cache repositories for each data domain
- `ICacheFactory` implementation that creates those repositories
- PubSub channel construction and subscription helpers
- Backend selection between Redis, JSON-file, and in-memory backends

This context does NOT own:
- Identity resolution (who the `user_id` is after a BSUID lookup)
- Message sending or webhook parsing
- Event dispatch or handler orchestration
- TTL policy decisions — callers set TTL; the context enforces it

## Module Structure

```
wappa/persistence/
├── cache_factory.py              # Selects backend (redis / memory / json)
│
├── redis/                        # Primary production backend
│   ├── redis_client.py           # 5-pool, fork-safe async Redis client
│   ├── redis_manager.py          # App-lifecycle wrapper: init / health / cleanup
│   ├── redis_cache_factory.py    # ICacheFactory → instantiates repositories
│   ├── ops.py                    # Thin async wrappers over raw redis-py commands
│   ├── pubsub_subscriber.py      # PubSub subscription utilities (subscribe / build_channel)
│   │
│   └── redis_handler/
│       ├── user.py               # RedisUser      → IUserCache
│       ├── state_handler.py      # RedisStateHandler → IStateCache
│       ├── table.py              # RedisTable     → ITableCache
│       ├── expiry.py             # RedisExpiry    → IExpiryCache
│       ├── ai_state.py           # RedisAIState   → IAIStateCache
│       │
│       └── utils/
│           ├── tenant_cache.py   # InboxCache base (currently named TenantCache — rename in progress)
│           ├── key_factory.py    # KeyFactory: all key-building logic
│           └── serde.py          # JSON serialise / deserialise for hash fields
│
├── memory/                       # Dev / test backend (in-process dict)
└── json/                         # Local persistence backend (file-based)
```

## Redis Pool Layout

Five isolated Redis databases, one per data domain:

| Pool alias      | DB  | Purpose                    | Repository class    |
|-----------------|-----|----------------------------|---------------------|
| `users`         | 0   | User profile / metadata    | `RedisUser`         |
| `state_handler` | 1   | Conversational handler state | `RedisStateHandler` |
| `table`         | 2   | Structured inbox-wide records | `RedisTable`       |
| `expiry`        | 3   | TTL-triggered automation keys | `RedisExpiry`      |
| `ai_state`      | 4   | AI agent state              | `RedisAIState`      |

All pools are created at startup via `RedisClient.setup_single_url(base_url)`, which appends `/0`–`/4` automatically.

## Key Patterns

All keys are built exclusively through `KeyFactory`. The `inbox_id` value is always the first segment — it is the namespace boundary for all Wappa runtime data.

| Data domain   | Key pattern                                           |
|---------------|-------------------------------------------------------|
| User          | `{inbox_id}:user:{user_id}`                           |
| State         | `{inbox_id}:state:{handler_name}:{user_id}`           |
| Table record  | `{inbox_id}:df:{table_name}:pkid:{pkid}`              |
| Expiry trigger | `{inbox_id}:EXPTRIGGER:{action}:{identifier}`        |
| AI state      | `{inbox_id}:aistate:{agent_name}:{user_id}`           |
| PubSub channel | `wappa:notify:{inbox_id}:{user_id}:{event_type}`     |

> **Note on rename**: Code currently uses `tenant` where these patterns say `inbox_id`. The key value stored in Redis is the same (it is the `phone_number_id`); only the Python variable and parameter names are changing.

## Component Relationships

```
ICacheFactory (domain interface)
    └── RedisCacheFactory (redis/redis_cache_factory.py)
            ├── constructed with (inbox_id, user_id) defaults
            ├── _resolve_context() merges defaults with per-call overrides
            └── create_*_cache() → instantiates repository with (inbox_id, user_id, pool_alias)

InboxCache (redis_handler/utils/tenant_cache.py)   ← base for all repositories
    ├── holds: inbox_id, ttl_default, redis_alias, keys: KeyFactory
    ├── _hset_with_ttl()        atomic hash write + EXPIRE
    ├── _get_hash()             HGETALL + deserialise
    ├── _find_by_field()        SCAN + field match
    ├── _delete_by_pattern()    SCAN + DEL batch
    └── _scan_keys_by_pattern() SCAN collect-only
    
    Subclasses (each adds a _key() builder and public API):
    ├── RedisUser         (user:)
    ├── RedisStateHandler (state:)
    ├── RedisTable        (df:)
    ├── RedisExpiry       (EXPTRIGGER:)
    └── RedisAIState      (aistate:)

KeyFactory (redis_handler/utils/key_factory.py)
    - pure Pydantic model, no I/O
    - one method per key type; all accept inbox_id as first positional arg
    - parse_trigger() reverses the Expiry key back to (inbox_id, action, identifier)

RedisClient (redis/redis_client.py)
    - class-level pool registry, keyed by PoolAlias
    - detects fork (PID change) and rebuilds pools in child process
    - setup_single_url() creates all 5 pools from one base URL

RedisManager (redis/redis_manager.py)
    - application lifecycle: initialize() / cleanup() / get_health_status()
    - delegates to RedisClient.setup_single_url() on startup
    - health-checks all 5 pools via PING

pubsub_subscriber.py
    - build_channel() / build_pattern() delegate to KeyFactory.channel() / channel_pattern()
    - subscribe() is an async generator over PSUBSCRIBE messages
    - Notification dataclass carries inbox_id, user_id, event, platform, data
```

## Design Patterns

**Repository per domain** — Each data domain is a discrete class with a focused public API (`get`, `upsert`, `delete`, etc.) rather than a single generic cache adapter. This keeps callers from coupling to raw Redis commands.

**Hybrid context pattern** — `RedisCacheFactory` is constructed once per request with `(inbox_id, user_id)` defaults. Any `create_*_cache()` call can override either dimension without constructing a new factory. This avoids threading context through every call site while still supporting API-event scenarios where the canonical user differs from the sender.

**SCAN over KEYS** — All bulk enumeration (delete-by-pattern, find-by-field, list-handlers) uses cursor-based `SCAN` in batches of 100. `KEYS` is never used.

**Stateless KeyFactory** — All key-string logic lives in one Pydantic model with no side effects. It can be instantiated anywhere and tested without a Redis connection.

## Inbox Identity Naming

The persistence context uses `inbox_id` as the cache namespace boundary.
Legacy `tenant_id` names were removed by ADR 0001 and the v0.13 clean-break
release. Current persistence code should use:

- `ICacheFactory.__init__(inbox_id, user_id)`
- `ICacheFactory._resolve_context(inbox_id, user_id)`
- `create_*_cache(inbox_id=..., user_id=...)`
- Redis key patterns whose first segment is the Inbox ID

**Redis key values are not affected.** The first segment of every key is the `phone_number_id` value, which does not change. Only the Python variable names that hold that value are being renamed.

## Extension Points

- **New cache backend**: implement `ICacheFactory` and the five `I*Cache` interfaces; register it in `cache_factory.py`.
- **New data domain**: add a new repository class inheriting `InboxCache`, implement a new `I*Cache` interface, add a `create_*_cache()` method to `ICacheFactory` and `RedisCacheFactory`.
- **New key type**: add a builder method to `KeyFactory`; do not build key strings anywhere else.
