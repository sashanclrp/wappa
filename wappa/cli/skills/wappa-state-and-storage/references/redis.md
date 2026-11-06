# Redis for Wappa

## Contents

- Turn it on
- Pools and key layout
- Pub/Sub notifications
- Expiry triggers
- Inspect and verify
- Migrating from 0.33

## Turn it on

```python
from wappa import Wappa
app = Wappa(cache="redis")        # adds RedisPlugin for you; don't add a second one
```

Set `REDIS_URL` (a base URL with no database number, for example `redis://localhost:6379`). Without it, `cache="redis"` raises `ValueError`. The other settings: `REDIS_MAX_CONNECTIONS` (default 64), `REDIS_CONNECTION_TIMEOUT` (30), `REDIS_HEALTH_CHECK_INTERVAL` (60). If Redis is unreachable at startup, the app doesn't start. Only `RedisPlugin(max_connections=...)` is configurable; other keyword arguments are ignored. `WappaBuilder.with_redis_cache` doesn't exist.

## Pools and key layout

Wappa opens one pool per database on the same server:

| DB | Pool | Holds | Key |
| --- | --- | --- | --- |
| 0 | users | user cache | `{inbox}:user:{user_id}` |
| 1 | state_handler | state cache | `{inbox}:state:{handler}:{user_id}` |
| 2 | table | table cache, Inbox Directory rows | `{context_id}:df:{table}:pkid:{pkid}` |
| 3 | expiry | expiry triggers | `{inbox}:EXPTRIGGER:{action}:{identifier}` |
| 4 | ai_state | AI state cache | `{inbox}:aistate:{agent}:{user_id}` |

`{inbox}` is `InboxRef.cache_namespace` (`<platform>__<inbox_id>`). The layout is for reading and debugging only: always go through the cache factory. A managed Redis must allow databases 0–4 (some proxies expose only database 0).

## Pub/Sub notifications

`app.add_plugin(RedisPubSubPlugin())` (`from wappa.core.plugins import RedisPubSubPlugin`) publishes `incoming_message`, `outgoing_message`, `bot_reply` and `status_change` events on `wappa:notify:{inbox}:{user_id}:{event_type}`. Turn each one off with `publish_incoming=False` and similar flags. It needs `cache="redis"` and fails at startup without it. Subscribers can listen on `wappa:notify:<platform>__<inbox_id>:*` per Inbox. For browsers, prefer `SSEEventsPlugin` (`wappa-host-integration`).

## Expiry triggers

A per-User timer is an expiry key, not a cron, armed with `await self.cache_factory.create_expiry_cache().set("followup", user_id, 900)`. Re-arming the same action and identifier resets it. The key holds no data, so keep what the timer needs in a cache. Wiring it to the hook, the subject binding, `rebind` and delivery rules are in the `wappa-scheduled-tasks` skill.

## Inspect and verify

From a Wappa source checkout (the scripts aren't in the installed package), run from your app folder so its `.env` is found:

```bash
uv run python <wappa>/scripts/redis_inspect.py --platform whatsapp --inbox <phone_number_id> [--user <id>] [--values]
uv run python <wappa>/scripts/verify_redis_cache_live.py --url redis://localhost:6379
```

`redis_inspect.py` is read-only, lists keys with type and TTL across databases 0–4, and redacts secret fields. `verify_redis_cache_live.py` exercises every cache against a real server under a throwaway prefix and cleans up.

## Migrating from 0.33

0.34 qualifies WhatsApp namespaces (`<pnid>` → `whatsapp__<pnid>`). With 0.33 workers stopped:

```bash
wappa migrate cache-namespaces -i <pnid> [-i <pnid2>] --redis-url "$REDIS_URL"          # dry run
wappa migrate cache-namespaces -i <pnid> --redis-url "$REDIS_URL" --apply                # rename, keeps TTLs
```

Add `--json-root PATH` for the JSON backend. Conflicts are reported, never overwritten. Pub/Sub subscribers move to `wappa:notify:whatsapp__<pnid>:*`.
