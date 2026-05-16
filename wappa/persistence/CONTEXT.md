# CONTEXT.md — Persistence Bounded Context

Local glossary for the Persistence context. Terms in the root `CONTEXT.md` (shared kernel) apply here without repetition. This file covers terms specific to how Wappa scopes, names, and manages runtime cache data.

Reference: [root CONTEXT.md](../../../CONTEXT.md)

## Cache Repositories

| Term | Definition |
|------|-----------|
| **Cache Repository** | A context-bound object that owns all Redis operations for one data domain (user, state, table, expiry, AI state). Created by `ICacheFactory`; scoped to `(inbox_id, user_id)`. |
| **InboxCache** | Base class for all Redis repositories. Holds the `inbox_id` that namespaces every key it builds. Code currently names this `TenantCache` — that name is being replaced. |
| **State Cache** | Repository for per-user conversational handler state within an Inbox. Keyed by `(inbox_id, handler_name, user_id)`. |
| **User Cache** | Repository for per-user profile and metadata within an Inbox. Keyed by `(inbox_id, user_id)`. |
| **Table Cache** | Repository for structured inbox-wide records. Keyed by `(inbox_id, table_name, pkid)`. No `user_id` dimension. |
| **Expiry Cache** | Repository for time-triggered automation keys. Keyed by `(inbox_id, action, identifier)`. |
| **AI State Cache** | Repository for AI agent state scoped to `(inbox_id, agent_name, user_id)`. |

## Key Namespace

| Term | Definition |
|------|-----------|
| **Key Pattern** | The Redis key naming template used to namespace data. `inbox_id` is always the first segment. All patterns are built by `KeyFactory`. |
| **Expiry Key** | A Redis key with a TTL whose expiration fires an Expiry Action. Format: `{inbox_id}:EXPTRIGGER:{action}:{identifier}`. |
| **PubSub Channel** | Redis Pub/Sub channel for real-time notifications. Format: `wappa:notify:{inbox_id}:{user_id}:{event_type}`. Note the `wappa:notify:` prefix before `inbox_id`. |
| **KeyFactory** | Pure stateless Pydantic model that constructs all Redis key strings. Single source of truth for key format. |

## Connection Infrastructure

| Term | Definition |
|------|-----------|
| **Pool Alias** | One of five named Redis connection pools: `users`, `state_handler`, `table`, `expiry`, `ai_state`. Each maps to a dedicated Redis database (db0–db4). |
| **Fork-Safe Client** | `RedisClient` detects when a worker process is forked and rebuilds its connection pools in the child so no parent descriptors leak. |
| **TTL** | Time-to-live in seconds applied to every cache key. Default: 86 400 s (24 h). Handlers may override per-call. |

## Anti-Language (Persistence-local)

| Forbidden Term | Use Instead |
|----------------|-------------|
| `tenant`, `tenant_id` (as cache scope) | `inbox_id` — the Wappa Inbox is the namespace boundary, not a business tenant |
| `TenantCache` | `InboxCache` — the rename is in progress; new code must use the canonical name |
| `KEYS` (Redis command) | `SCAN` — `KEYS` blocks the server; all pattern-based enumeration uses cursor-based SCAN |
