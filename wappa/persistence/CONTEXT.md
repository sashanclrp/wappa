# CONTEXT.md — Persistence Bounded Context

Local glossary for the Persistence context. Terms in the root `CONTEXT.md` (shared kernel) apply here without repetition. This file covers terms specific to how Wappa scopes, names, and manages runtime cache data.

Reference: [root CONTEXT.md](../../CONTEXT.md)

## Cache Repositories

| Term | Definition |
|------|-----------|
| **Cache Repository** | A context-bound object that owns all Redis operations for one data domain (user, state, table, expiry, AI state). Created by `ICacheFactory`. User, state, expiry, and AI state repositories use Inbox Reference/User context; Table Cache uses one `context_id`. |
| **InboxCache** | Base class for the Redis repositories. User, State, Expiry, and AI State repositories bind it to an Inbox Namespace; `RedisTable` binds it to a Table Cache Scope (`context_id`). |
| **State Cache** | Repository for per-user conversational handler state within an Inbox. Keyed by `(InboxRef, handler_name, user_id)`. |
| **User Cache** | Repository for per-user profile and metadata within an Inbox. Keyed by `(InboxRef, user_id)`. |
| **Table Cache** | Repository for arbitrary structured Pydantic records and DB-derived read models. Keyed by `(context_id, table_name, pkid)`. No `user_id` dimension. Constructed with `context_id` (positional or keyword; the former `inbox`/`inbox_id` keywords raise `TypeError`). Normal Inbox-owned usage passes the Inbox Namespace; System uses the reserved System Scope; hosts may define their own business context. The scopes are siblings with no fallback or cascade. |
| **System Scope** | The exact reserved `context_id` `"__system__"` (`SYSTEM_SCOPE`), built with `create_system_table_cache(cache_type)`. No Inbox or Host-defined context may encode to it; native identifiers may not contain `__`. |
| **Inbox Directory Table** | `InboxDirectoryTable`: Wappa-owned rows on a System-Scope Table Cache. Primary table `wappa_inbox_directory` (pkid = `InboxRef.cache_namespace`) and index table `wappa_inbox_directory_account_index` (pkid = `PlatformAccountRef.cache_namespace`). Owns TTLs, versioned compare-and-set, and repair; knows nothing about sources, keys, or clients. |
| **Expiry Cache** | Repository for time-triggered automation entries. Keyed by `(InboxRef, action, identifier)`. |
| **AI State Cache** | Repository for AI agent state scoped to `(InboxRef, agent_name, user_id)`. |

## Key Namespace

| Term | Definition |
|------|-----------|
| **Inbox Namespace** | `InboxRef.cache_namespace`: the collision-free string Wappa derives from an Inbox Reference for persistence. WhatsApp keeps its raw `phone_number_id` so deployed keys stay readable; every other Platform uses `<platform>__<inbox_id>`. Host Applications never construct it. |
| **Key Pattern** | The Redis naming template used to namespace data. Inbox Namespace is the first segment for Inbox runtime caches. Table Cache alone may use another explicit `context_id` as its first segment. All patterns are built by `KeyFactory`. |
| **Expiry Key** | A Redis entry with a TTL whose expiration fires an Expiry Action. Format: `{inbox_namespace}:EXPTRIGGER:{action}:{identifier}`. |
| **PubSub Channel** | Redis Pub/Sub channel for real-time notifications. Format: `wappa:notify:{inbox_id}:{user_id}:{event_type}`. Note the `wappa:notify:` prefix before `inbox_id`. |
| **KeyFactory** | Pure stateless Pydantic model that constructs all Redis key strings. Single source of truth for key format. |
| **Cache Space** | Optional host-owned namespace folded into a table name as `{cache_space}:{table_name}`. Separates unrelated read models that share a table name inside one Table Cache context. Wappa never assigns one; the Host Application passes it explicitly. |
| **Table Generation** | The version suffix (`{table}@v{n}`) identifying which generation of a versioned table cache is live. Starts at `v1`. |
| **Version Bump** | Incrementing a versioned table's generation counter to invalidate every row in one operation, without enumerating keys. Orphaned generations expire by TTL. |

## Connection Infrastructure

| Term | Definition |
|------|-----------|
| **Pool Alias** | One of five named Redis connection pools: `users`, `state_handler`, `table`, `expiry`, `ai_state`. Each maps to a dedicated Redis database (db0–db4). |
| **Fork-Safe Client** | `RedisClient` detects when a worker process is forked and rebuilds its connection pools in the child so no parent descriptors leak. |
| **TTL** | Time-to-live in seconds applied to every cache key. Default: 86 400 s (24 h). Handlers may override per-call. |

## Anti-Language (Persistence-local)

| Forbidden Term | Use Instead |
|----------------|-------------|
| `tenant`, `tenant_id` (as cache scope) | `inbox_id` for Inbox runtime caches; `context_id` only for Table Cache |
| `inbox_id=` / `inbox=` on a Table Cache constructor | `context_id=` (positional calls unchanged; stored keys unchanged) |
| `TenantCache` | `InboxCache` — the rename is in progress; new code must use the canonical name |
| `KEYS` (Redis command) | `SCAN` — `KEYS` blocks the server; all pattern-based enumeration uses cursor-based SCAN |
