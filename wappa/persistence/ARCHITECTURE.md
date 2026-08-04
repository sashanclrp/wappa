# ARCHITECTURE.md — Persistence Bounded Context

Internal structure, responsibilities, and design decisions for the Persistence context.

Cross-references: [root ARCHITECTURE.md](../../../ARCHITECTURE.md) · [CONTEXT.md](CONTEXT.md) · [root CONTEXT.md](../../../CONTEXT.md)

## Responsibilities

This context owns:
- Multi-pool Redis client management (lifecycle, fork-safety, health checks)
- Redis key namespace generation via `KeyFactory`
- Context-bound cache handlers for each data domain
- Typed table-cache ergonomics over the existing `ITableCache` contract
- `ICacheFactory` implementation that creates those handlers
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
├── cache_space.py                # Optional host-owned namespace segment for table names
├── typed_table_cache.py          # TypedTableCache[T] convenience wrapper over ITableCache
├── versioned_table_cache.py      # VersionedTableCache[T] — bump-to-invalidate read models
│
├── redis/                        # Primary production backend
│   ├── redis_client.py           # 5-pool, fork-safe async Redis client
│   ├── redis_manager.py          # App-lifecycle wrapper: init / health / cleanup
│   ├── redis_cache_factory.py    # ICacheFactory → instantiates cache handlers
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
│           ├── inbox_cache.py    # InboxCache shared Redis behavior
│           ├── key_factory.py    # KeyFactory: all key-building logic
│           └── serde.py          # JSON serialise / deserialise for hash fields
│
├── memory/                       # Dev / test backend (in-process dict)
└── json/                         # Local persistence backend (file-based)
```

## Redis Pool Layout

Five isolated Redis databases, one per data domain:

| Pool alias      | DB  | Purpose                    | Cache handler       |
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

## Component Relationships

```
ICacheFactory (domain interface)
    └── RedisCacheFactory (redis/redis_cache_factory.py)
            ├── constructed with (inbox_id, user_id) defaults
            ├── _resolve_context() merges defaults with per-call overrides
            └── create_*_cache() → instantiates a handler with (inbox_id, user_id, pool_alias)

InboxCache (redis_handler/utils/inbox_cache.py)   ← shared Redis behavior
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

**Cache contract per domain** — Each data domain has one focused interface
(`IUserCache`, `IStateCache`, `ITableCache`, `IExpiryCache`, or
`IAIStateCache`) implemented by each backend. The former unused
`I*Repository` hierarchy was removed: it duplicated these contracts without an
implementation path.

**Typed wrapper over table caches** — `TypedTableCache[T]` binds an
existing `ITableCache` to a table name and Pydantic model. It validates table
names and primary keys, forwards TTLs, and returns typed rows without changing
backend key shapes. Inbox scoping still comes from the `ICacheFactory` /
`ITableCache` instance.

**Cache space as an optional second segment** — Inbox scoping is Wappa's; a
*cache space* is the host's. `build_table_name(table, cache_space)` folds it in
as `"{cache_space}:{table}"`, so two host modules can use the same table name
inside one Inbox without colliding. Wappa never invents a cache space, and
omitting it leaves existing key shapes untouched. Both segments reject `:` and
`@` so a caller cannot smuggle extra key structure through a name.

**Generation counter instead of key enumeration** — `VersionedTableCache[T]`
suffixes its table with a generation (`agents@v3`) read from a counter row in
`_wappa_table_versions`. Invalidating a whole read model is one counter
increment: readers miss immediately, writers land in the new generation, and
the old one is orphaned. This avoids SCAN-and-delete over a live key space,
which is both slow and impossible to do atomically while writers are active.
The cost is one extra cache read per operation — deliberate, because caching
the generation in-process would keep serving rows another worker already
invalidated. Orphaned generations are reclaimed by TTL, which is why
`default_ttl` is required rather than optional — and why the counter row itself
carries a longer TTL, refreshed on every bump, so it can never expire back to
`v1` while orphaned rows are still live.

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

For WhatsApp, the first key segment contains the Inbox's Meta
`phone_number_id`; the adapter owns that mapping.

## Extension Points

- **New cache backend**: implement `ICacheFactory` and the five `I*Cache` interfaces; register it in `cache_factory.py`.
- **New data domain**: add a cache handler inheriting `InboxCache`, implement a new `I*Cache` interface, and add a `create_*_cache()` method to `ICacheFactory` and each backend factory.
- **New key type**: add a builder method to `KeyFactory`; do not build key strings anywhere else.
