# Wappa Plugin Architecture

## Overview

Wappa uses a plugin-based architecture to extend FastAPI applications. Every piece of functionality -- middleware, routes, database connections, caching, authentication, real-time events -- is implemented as a plugin. This ensures a consistent lifecycle, clean separation of concerns, and composable application assembly.

## Core Components

### WappaPlugin Protocol

All plugins implement the `WappaPlugin` protocol defined in `wappa/core/factory/plugin.py`:

```python
class WappaPlugin(Protocol):
    def configure(self, builder: WappaBuilder) -> None: ...
    async def startup(self, app: FastAPI) -> None: ...
    async def shutdown(self, app: FastAPI) -> None: ...
```

Three lifecycle methods, each with a distinct responsibility:

| Method | When it runs | What to do here |
|---|---|---|
| `configure()` | **Synchronously** during `WappaBuilder.build()`, before the FastAPI app is created | Register middleware, routes, startup/shutdown hooks with the builder |
| `startup()` | **Async** during FastAPI lifespan startup | Initialize connections, verify health, set `app.state` |
| `shutdown()` | **Async** during FastAPI lifespan shutdown | Close connections, clean up `app.state` |

**Important**: `configure()` is synchronous. It must not perform I/O or await anything. All async initialization belongs in `startup()`.

### WappaBuilder

The builder (`wappa/core/factory/wappa_builder.py`) orchestrates plugin assembly:

```python
builder = WappaBuilder()
builder.add_plugin(WappaCorePlugin())
builder.add_plugin(RedisPlugin())
builder.add_plugin(AuthPlugin(strategy=BearerTokenStrategy(token="...")))
app = builder.build()
```

`build()` executes this sequence:

1. **Configure all plugins** -- calls `plugin.configure(self)` synchronously for each plugin
2. **Create FastAPI app** -- with a unified lifespan that runs all registered hooks
3. **Add middleware** -- sorted by priority (higher priority = outer/earlier execution)
4. **Include routers** -- all routers registered during configure phase

The builder exposes these registration methods that plugins call during `configure()`:

- `builder.add_middleware(cls, priority=50, **kwargs)` -- register middleware with priority ordering
- `builder.add_router(router, **kwargs)` -- register a FastAPI router
- `builder.add_startup_hook(hook, priority=50)` -- register an async startup function
- `builder.add_shutdown_hook(hook, priority=50)` -- register an async shutdown function

### Wappa Class

The `Wappa` class (`wappa/core/wappa_app.py`) is the user-facing entry point. Internally it creates a `WappaBuilder`, adds `WappaCorePlugin` automatically, and provides convenience methods:

```python
app = Wappa(cache="redis")
app.add_plugin(PostgresDatabasePlugin(url="postgresql+asyncpg://..."))
app.set_event_handler(MyEventHandler())
app.run()
```

## Priority System

Hooks and middleware use a numeric priority to control execution order:

### Startup Hooks (ascending order -- lower runs first)

| Priority | Purpose | Example |
|---|---|---|
| 10 | Core system initialization | WappaCorePlugin (logging, HTTP session) |
| 20 | Infrastructure services | RedisPlugin |
| 22 | Event-based infrastructure | RedisPubSubPlugin, SSEEventsPlugin |
| 25 | Data infrastructure | PostgresDatabasePlugin, ExpiryPlugin |
| 50 | User hooks (default) | Custom startup logic |
| 70+ | Late initialization | Post-setup tasks |

### Shutdown Hooks (descending order -- higher runs first)

| Priority | Purpose | Example |
|---|---|---|
| 90 | Core cleanup (runs last) | WappaCorePlugin (close HTTP session) |
| 25 | Data cleanup | PostgresDatabasePlugin |
| 22 | Event cleanup | RedisPubSubPlugin, SSEEventsPlugin |
| 20 | Infrastructure cleanup | RedisPlugin |

### Middleware Priority (higher = outer/earlier)

| Priority | Middleware | Plugin |
|---|---|---|
| 90 | OwnerMiddleware, CORSMiddleware | WappaCorePlugin, CORSPlugin |
| 85 | SecurityHeaders | CustomMiddlewarePlugin |
| 80 | ErrorHandlerMiddleware | WappaCorePlugin |
| 70 | RequestLoggingMiddleware, RateLimiter | WappaCorePlugin, RateLimitPlugin |
| 60 | AuthMiddleware | AuthPlugin |
| 50 | Custom middleware (default) | CustomMiddlewarePlugin |

```
Request --> Owner(90) --> ErrorHandler(80) --> RequestLogging(70) --> Auth(60) --> Route
```

## Plugin Categories

### Foundation
- **WappaCorePlugin** -- logging, HTTP session, core middleware, core routes, webhook URLs

### Infrastructure
- **RedisPlugin** -- Redis connection pool management
- **PostgresDatabasePlugin** -- PostgreSQL async session management with connection pooling

### Real-Time Events
- **SSEEventsPlugin** -- Server-Sent Events streaming for incoming/outgoing messages
- **RedisPubSubPlugin** -- Redis PubSub notifications for distributed event broadcasting
- **ExpiryPlugin** -- Redis key expiry listener for time-based automation

### Middleware Wrappers
- **AuthPlugin** -- strategy-based authentication (Bearer, Basic, JWT, custom)
- **CORSPlugin** -- Cross-Origin Resource Sharing configuration
- **RateLimitPlugin** -- bring-your-own rate limiting middleware
- **CustomMiddlewarePlugin** -- generic wrapper for any user-defined middleware

### Integrations
- **WebhookPlugin** -- custom webhook endpoints for payment providers and third-party services

## Plugin Patterns

### Pattern 1: Middleware-Only (no hooks needed)

Plugins that only register middleware during `configure()`. Startup/shutdown are no-ops.

```python
class CORSPlugin:
    def configure(self, builder):
        builder.add_middleware(CORSMiddleware, priority=90, **self.cors_config)

    async def startup(self, app): pass
    async def shutdown(self, app): pass
```

**Used by**: AuthPlugin, CORSPlugin, RateLimitPlugin, CustomMiddlewarePlugin

### Pattern 2: Hook-Based (infrastructure lifecycle)

Plugins that register startup/shutdown hooks during `configure()` for async resource management.

```python
class RedisPlugin:
    def configure(self, builder):
        builder.add_startup_hook(self._redis_startup, priority=20)
        builder.add_shutdown_hook(self._redis_shutdown, priority=20)

    async def _redis_startup(self, app):
        await RedisManager.initialize(...)
        app.state.redis_manager = RedisManager

    async def _redis_shutdown(self, app):
        await RedisManager.cleanup()
        del app.state.redis_manager
```

**Used by**: WappaCorePlugin, RedisPlugin, PostgresDatabasePlugin, ExpiryPlugin, SSEEventsPlugin, RedisPubSubPlugin

### Pattern 3: Router + Hooks (routes with lifecycle)

Plugins that register both routes and lifecycle hooks.

```python
class SSEEventsPlugin:
    def configure(self, builder):
        builder.add_router(sse_router)
        builder.add_startup_hook(self._startup_hook, priority=24)
        builder.add_shutdown_hook(self._shutdown_hook, priority=24)
```

**Used by**: SSEEventsPlugin, WebhookPlugin

## Dependency Order

Some plugins depend on others being initialized first. The priority system enforces this:

```
WappaCorePlugin (10)  -->  RedisPlugin (20)  -->  SSEEventsPlugin (24)
                                              -->  RedisPubSubPlugin (22)
                                              -->  ExpiryPlugin (25)
                                              -->  PostgresDatabasePlugin (25)
```

Middleware plugins (Auth, CORS, RateLimit, CustomMiddleware) have no startup dependencies -- they only register middleware during `configure()`.

## Writing a Custom Plugin

```python
from wappa.core.factory.plugin import WappaPlugin

class MyPlugin:
    def __init__(self, some_config: str):
        self.config = some_config

    def configure(self, builder):
        # Register middleware, routes, or hooks
        builder.add_startup_hook(self._start, priority=30)
        builder.add_shutdown_hook(self._stop, priority=30)

    async def startup(self, app):
        await self._start(app)

    async def shutdown(self, app):
        await self._stop(app)

    async def _start(self, app):
        # Initialize your service
        app.state.my_service = MyService(self.config)

    async def _stop(self, app):
        # Clean up
        if hasattr(app.state, "my_service"):
            await app.state.my_service.close()
            del app.state.my_service
```

Register it:

```python
app = Wappa(cache="memory")
app.add_plugin(MyPlugin(some_config="value"))
```

## Available Plugins

| Plugin | File | README |
|---|---|---|
| WappaCorePlugin | `wappa_core_plugin.py` | [WappaCorePlugin.md](./WappaCorePlugin.md) |
| RedisPlugin | `redis_plugin.py` | [RedisPlugin.md](./RedisPlugin.md) |
| PostgresDatabasePlugin | `postgres_database_plugin.py` | [PostgresDatabasePlugin.md](./PostgresDatabasePlugin.md) |
| SSEEventsPlugin | `sse_events_plugin.py` | [SSEEventsPlugin.md](./SSEEventsPlugin.md) |
| RedisPubSubPlugin | `redis_pubsub_plugin.py` | [RedisPubSubPlugin.md](./RedisPubSubPlugin.md) |
| ExpiryPlugin | `expiry_plugin.py` | [ExpiryPlugin.md](./ExpiryPlugin.md) |
| AuthPlugin | `auth_plugin.py` | [AuthPlugin.md](./AuthPlugin.md) |
| CORSPlugin | `cors_plugin.py` | [CORSPlugin.md](./CORSPlugin.md) |
| RateLimitPlugin | `rate_limit_plugin.py` | [RateLimitPlugin.md](./RateLimitPlugin.md) |
| CustomMiddlewarePlugin | `custom_middleware_plugin.py` | [CustomMiddlewarePlugin.md](./CustomMiddlewarePlugin.md) |
| WebhookPlugin | `webhook_plugin.py` | [WebhookPlugin.md](./WebhookPlugin.md) |
