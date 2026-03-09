# RedisPlugin

> Part of the Wappa Plugin Architecture. See [Architecture](./Architecture.md) for the plugin system overview, lifecycle, and patterns.

## What it does

`RedisPlugin` initializes and manages Redis connectivity for the entire Wappa application. It creates a `RedisManager` singleton with connection pools during startup, stores it in `app.state.redis_manager`, performs a health check, and tears everything down on shutdown.

This is the foundational Redis plugin -- other plugins that need Redis (`RedisPubSubPlugin`, `ExpiryPlugin`, `SSEEventsPlugin`) depend on `RedisPlugin` being registered first.

## How to activate

**Automatic** -- pass `cache="redis"` to `Wappa` and the plugin is added for you:

```python
from wappa import Wappa

app = Wappa(cache="redis")
```

**Manual** -- add it explicitly through `WappaBuilder`:

```python
from wappa.core.factory import WappaBuilder
from wappa.core.plugins import WappaCorePlugin, RedisPlugin

builder = WappaBuilder()
builder.add_plugin(WappaCorePlugin())
builder.add_plugin(RedisPlugin())
app = builder.build()
```

**With custom connection settings:**

```python
builder.add_plugin(RedisPlugin(max_connections=100))
```

## Configuration options

| Parameter | Type | Default | Description |
|---|---|---|---|
| `max_connections` | `int \| None` | `None` | Maximum number of Redis connections in the pool. When `None`, falls back to `settings.redis_max_connections` |
| `**redis_config` | `Any` | -- | Additional Redis configuration options passed through to the underlying client |

### Environment variables

| Variable | Default | Description |
|---|---|---|
| `REDIS_URL` | (required) | Redis connection URL, e.g. `redis://localhost:6379` |
| `REDIS_MAX_CONNECTIONS` | `64` | Default max connections when not overridden in the constructor |

## How it works

RedisPlugin uses the **Hook-Based pattern** (Pattern 2 in the architecture). During `configure()`, it registers startup and shutdown hooks at **priority 20** -- after core Wappa services (priority 10) but before user hooks (priority 50).

### Startup sequence (priority 20)

1. Reads `redis_url` from `settings.redis_url` (the `REDIS_URL` env var)
2. Resolves `max_connections` -- constructor value wins, otherwise `settings.redis_max_connections`
3. Calls `RedisManager.initialize()` to create connection pools
4. Stores `RedisManager` in `app.state.redis_manager`
5. Runs `RedisManager.get_health_status()` and logs pool health
6. If any step fails, raises `RuntimeError` -- the application will not start with a broken Redis connection

### Shutdown sequence (priority 20)

1. Checks whether `RedisManager` was initialized
2. Calls `RedisManager.cleanup()` to close all connection pools
3. Removes `redis_manager` from `app.state`
4. Errors during shutdown are logged but **not re-raised**, so other plugins can still clean up

### Priority in the lifecycle

```
Startup:   WappaCorePlugin (10)  -->  RedisPlugin (20)  -->  RedisPubSubPlugin (22)
                                                         -->  SSEEventsPlugin (24)
                                                         -->  ExpiryPlugin (25)

Shutdown:  ExpiryPlugin (25)  -->  SSEEventsPlugin (24)  -->  RedisPubSubPlugin (22)  -->  RedisPlugin (20)
```

## Accessing Redis in event handlers

Event handlers do not interact with `RedisPlugin` directly. Instead, they use the `ICacheFactory` that is injected into every handler via `with_context()`:

```python
from wappa import Wappa, WappaEventHandler

class MyHandler(WappaEventHandler):
    async def handle_message(self, message):
        # cache_factory is injected automatically per request
        user_cache = self.cache_factory.create_user_cache(
            tenant_id=self.tenant_id,
            user_id=self.user_id,
        )
        await user_cache.set("last_seen", "2026-03-09")
        value = await user_cache.get("last_seen")
```

The `cache_factory` attribute is set to `None` until the request context is bound. When Redis is the active cache backend, the factory creates Redis-backed cache instances scoped to the current tenant and user.

## Health monitoring

`RedisPlugin` exposes a `get_health_status()` method for monitoring integrations:

```python
status = await redis_plugin.get_health_status(app)
# {
#     "healthy": True,
#     "plugin": "RedisPlugin",
#     "initialized": True,
#     "pools": {
#         "default": {"status": "healthy", ...},
#         ...
#     }
# }
```

If `RedisManager` is not initialized, the response indicates `"healthy": False` with an appropriate error message.

## Dependencies

`RedisPlugin` is a **prerequisite** for these plugins:

| Plugin | Priority | Relationship |
|---|---|---|
| `RedisPubSubPlugin` | 22 | Requires `RedisManager` for PubSub channels. Raises `RuntimeError` if Redis is not initialized |
| `ExpiryPlugin` | 25 | Requires `RedisManager` for key expiry listeners. Raises `RuntimeError` if Redis is not initialized |
| `SSEEventsPlugin` | 24 | Uses `RedisManager` (when available) for wrapping messengers with event broadcasting |

Always register `RedisPlugin` before any of these plugins. When using `Wappa(cache="redis")`, this ordering is handled automatically.
