---
name: wappa-runtime-state
description: Designs and reviews Inbox- and User-scoped runtime state in Wappa apps — state, user, table, expiry and AI caches on the memory, JSON or Redis backends, TTLs, cache misses, outages, and isolation across Users, Inboxes and Platforms (WhatsApp and Instagram). Use when choosing a cache backend, storing flow state, debugging state leaking between users or accounts, configuring Redis for Wappa, or deciding what must not live in a cache. Not for Platform setup or send operations.
---

# Wappa state and Redis

Wappa scopes runtime caches by Inbox Reference (`InboxRef.cache_namespace`, which is Platform-qualified) and User. The same native ID on two Inboxes, or on WhatsApp and Instagram, never shares state unless the app links them with its own evidence.

## Get a cache

Inside a handler, `self.cache_factory` is already bound to the event's Inbox and User:

```python
state = self.cache_factory.create_state_cache()     # flow/handler state by key
user = self.cache_factory.create_user_cache()       # per-User profile data
table = self.cache_factory.create_table_cache()     # app tables scoped by context
```

Outside a handler (jobs, tests), build the factory from the qualified Inbox:

```python
from wappa.persistence.cache_factory import create_cache_factory
factory = create_cache_factory("redis")(inbox_id=inbox_ref.cache_namespace, user_id=user_id)
```

Never hand-build Redis keys or pass a bare `inbox_id` from another Platform. Pick the backend with `Wappa(cache="memory" | "json" | "redis")`; Redis needs `REDIS_URL`.

## Lifetime and failure

| Case | Behavior | App rule |
| --- | --- | --- |
| Miss or expired TTL | `get(...)` returns `None` | Treat it as "no active flow": restart or explain. Never guess. |
| Write | `upsert(key, data, ttl=seconds)`; `renew_ttl(key, ttl)` extends it | Give every flow state a TTL. |
| Redis outage | Operations raise | Let the handler fail visibly or reply with a safe error. Never treat it as an empty state. |
| Memory backend | Process-local, lost on restart | Use it for development and tests only. |
| Concurrency | Last write wins per key | Keep one key per flow and re-read before advancing. For contested records, use Table Cache compare-and-set (`create_if_absent` / `replace_if`). |

## What does not belong in caches

- **Credentials.** Never store tokens in a cache. Trusted adapters resolve them per operation (`InboxCredentialAccess`).
- **Business records.** Submitted forms, orders and history belong in host persistence. Flow state is transient.
- **Data for AI tools.** Tools get the narrow data or capability they need, not a general cache factory and never a token.

## Verify isolation

The worked test is in `references/isolation-tests.md`. Run it on the backend you deploy: memory in unit tests, plus a Redis run before release.
