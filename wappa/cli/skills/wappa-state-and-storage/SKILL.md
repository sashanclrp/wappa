---
name: wappa-state-and-storage
description: Designs and reviews where a Wappa app keeps its data — Inbox- and User-scoped runtime caches (state, user, table, expiry, AI) on the memory, JSON or Redis backends, RedisPlugin and RedisPubSubPlugin setup, TTLs, misses and outages, cache namespace migration, and PostgresDatabasePlugin sessions, replicas and models for durable records, with isolation across Users, Inboxes and Platforms (WhatsApp and Instagram). Use when choosing a cache backend, storing flow state, message IDs or profile facts, configuring Redis or Postgres for Wappa, debugging state leaking between users or accounts, inspecting Redis keys, or deciding what belongs in a cache versus the database. Not for Platform setup or send operations (wappa-apps).
---

# State and storage in Wappa apps

Wappa scopes every runtime cache by Inbox (`InboxRef.cache_namespace`, which is Platform-qualified, such as `whatsapp__<pnid>` or `instagram__<id>`) and by User. The same native ID on two Inboxes, or on WhatsApp and Instagram, never shares state unless the app links them with its own evidence. Wappa owns runtime caches; the Host owns its database schema and every business record.

## Decide where the data lives

| Data | Home | Why |
| --- | --- | --- |
| Where a User is in a flow (step, partial answers) | State cache, one key per flow, with a TTL | Transient; a miss means "no active flow" |
| Per-User facts you reuse often (profile name, username, language) | User cache (`create_user_cache()`), refreshed from `resolve_platform_user_profile` | Fast reads, scoped by Inbox |
| A timer per User ("remind in 15 minutes") | Expiry cache (`create_expiry_cache().set(action, id, ttl)`) plus the `wappa-scheduled-tasks` skill (Redis only) | Fires when the key expires |
| Agent memory | AI state cache (`create_ai_state_cache()`) | Scoped per Inbox, User and agent |
| Shared rows (a slot, a counter, a lock-like record) | Table cache with `create_if_absent` / `replace_if` | Compare-and-set without races |
| Submitted forms, orders, conversation history, `MessageResult.message_id` and `wappa_parts` IDs kept for status matching | **Database** (`PostgresDatabasePlugin`) or the Host's own store | Durable; never TTL-only |
| Tokens and credentials | Neither: the encrypted Inbox Directory, resolved per operation | Never in a cache |

## Get a cache

Inside a handler, `self.cache_factory` is already bound to the event's Inbox and User:

```python
state = self.cache_factory.create_state_cache()     # get/upsert/delete(handler_name, ...)
user = self.cache_factory.create_user_cache()       # get/upsert/update_field for this User
table = self.cache_factory.create_table_cache()     # rows scoped by context
```

Outside a handler (jobs, tests), build it from the qualified Inbox:

```python
from wappa.persistence.cache_factory import create_cache_factory
factory = create_cache_factory("redis")(inbox_id=inbox_ref.cache_namespace, user_id=user_id)
```

Never hand-build Redis keys or pass a bare `inbox_id` from another Platform. `self.cache_factory` is `None` in lanes with no bound Inbox (`process_api_message`, system crons, unresolved external events). Check it there.

## Lifetime and failure

| Case | Behavior | App rule |
| --- | --- | --- |
| Miss or expired TTL | `get(...)` returns `None` | Treat it as "no active flow": restart or explain. Never guess. |
| Write | `upsert(..., ttl=seconds)` returns `True` or `False`; `renew_ttl` extends | Give every flow state a TTL and check the return value: `False` is a failed write. |
| Redis down | The connection check raises, so the handler fails. A command that fails after the check is logged and reads back as a miss (`None` / `{}`). | Fail visibly or reply with a safe error. Never treat an unexpected miss on data you just wrote as "the flow ended". |
| Memory backend | Process-local, lost on restart | Development and tests only |
| JSON backend | Files, one process | Development only |
| Concurrency | Last write wins per key | Keep one key per flow and re-read before advancing. For contested rows, use `create_if_absent` / `replace_if` (`TableTransitionResult.written`). |

## Branches

| Task | Load |
| --- | --- |
| Turn on Redis, pools and databases 0–4, env vars, Pub/Sub, expiry triggers, inspecting keys, migrating 0.33 namespaces | `references/redis.md` |
| Postgres: the plugin, sessions in handlers, read replicas, models and tables, pgBouncer and Supabase | `references/database.md` |
| Prove state never leaks between Users, Inboxes or Platforms | `references/isolation-tests.md` |

## Never

- Store credentials, or business records only in a cache.
- Give an AI tool the cache factory or a database session. Give it the narrow data or one function it needs.
- Share state across Inboxes or Platforms by stripping the namespace. Link identities in your own database with your own evidence.
