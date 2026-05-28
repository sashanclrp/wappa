# Plugins Architecture

## Responsibilities

- Define the `WappaPlugin` structural protocol used by all plugins.
- Provide the built-in plugin catalogue that Host Applications compose into a `WappaBuilder`.
- Own the configure → build → startup → shutdown lifecycle for each plugin concern.
- Register middleware, routers, startup hooks, and shutdown hooks with `WappaBuilder` — never directly mutating a live `FastAPI` app.

## Explicit Boundaries

This context does NOT own:
- The `WappaBuilder` build logic or the unified lifespan manager (owned by `wappa/core/factory/`).
- Business event handling logic (owned by `WappaEventHandler` implementations in the Host Application).
- The `AuthStrategy` algorithms themselves (owned by `wappa/core/auth/`).
- Redis pool management (owned by `wappa/persistence/redis/`).
- Database session management (owned by `wappa/database/`).
- SSE routing and client subscription (owned by `wappa/api/routes/sse.py` and `wappa/core/sse/`).

## Module Structure

```
wappa/core/plugins/
├── ARCHITECTURE.md              # this file
├── CONTEXT.md                   # glossary
├── __init__.py                  # re-exports all public plugins
│
│   ── Protocol ──
├── (in factory/) plugin.py      # WappaPlugin structural protocol (configure / startup / shutdown)
│
│   ── Core ──
├── wappa_core_plugin.py         # WappaCorePlugin: logging setup, HTTP client, core middleware
│                                #   (OwnerMiddleware, ErrorHandlerMiddleware, RequestLoggingMiddleware),
│                                #   health and WhatsApp routers. Priority 10/90.
│
│   ── Infrastructure ──
├── redis_plugin.py              # RedisPlugin: initialises RedisManager pools, stores
│                                #   redis_manager on app.state. Priority 20.
├── postgres_database_plugin.py  # PostgresDatabasePlugin: async asyncpg engine via
│                                #   PostgresSessionManager, write/read replica support,
│                                #   optional auto table creation. Priority 20.
│
│   ── Infrastructure listeners ──
├── expiry_plugin.py             # ExpiryPlugin: spawns the Redis keyspace expiry asyncio.Task,
│                                #   requires RedisPlugin (priority 20) to run first. Priority 25.
├── redis_pubsub_plugin.py       # RedisPubSubPlugin: wraps inbound handlers and outbound
│                                #   messenger calls to publish to Redis PubSub channels.
│                                #   Requires RedisPlugin. Priority 25.
├── sse_events_plugin.py         # SSEEventsPlugin: constructs SSEEventHub, registers SSE router,
│                                #   wraps message/status/error handlers and adds
│                                #   SSELifecycleMiddleware to the messenger pipeline. Priority 24.
│
│   ── HTTP concerns ──
├── cors_plugin.py               # CORSPlugin: thin wrapper around FastAPI CORSMiddleware,
│                                #   configurable origins/methods/credentials. Configure-only.
├── auth_plugin.py               # AuthPlugin: registers AuthMiddleware with a pluggable
│                                #   AuthStrategy; supports exclude-mode and protect-mode.
│                                #   Configure-only (no startup/shutdown work).
├── rate_limit_plugin.py         # RateLimitPlugin: registers any rate-limiter middleware class
│                                #   via the builder. Configure-only.
├── custom_middleware_plugin.py  # CustomMiddlewarePlugin: generic wrapper to register any
│                                #   user-provided middleware class. Configure-only.
│
│   ── Integrations ──
├── webhook_plugin.py            # WebhookPlugin: mounts a named webhook endpoint.
│                                #   Raw mode (v1): plain callable handler.
│                                #   Processor mode (v2): IWebhookProcessor + WappaEventHandler,
│                                #   full Wappa context (messenger, cache, db). Priority 30.
└── cron_plugin.py               # CronPlugin: wraps fastapi-crons to schedule recurring jobs
                                 #   that fire CronEvent into the WappaEventHandler pipeline
                                 #   with full or db-only context depending on inbox_id scope.
                                 #   Priority 30.
```

## Key Classes and Their Roles

| Class | Role |
|-------|------|
| `WappaPlugin` (protocol) | Structural interface. Plugins satisfy it without inheriting from it. |
| `WappaCorePlugin` | Mandatory first plugin. Sets up authenticated HTTP client + pooled media download client via `SessionLifecycle`, `BackgroundWorkTracker`, logging, core routes, and core middleware stack. Owns three-phase shutdown: drain mark (90) → background drain (70) → resource close (10). |
| `RedisPlugin` | Infra plugin that initialises connection pools before any feature plugin that requires Redis. |
| `PostgresDatabasePlugin` | Infra plugin that creates the async SQLAlchemy engine and injects `db`/`db_read` into handlers. |
| `ExpiryPlugin` | Depends on `RedisPlugin`. Owns the long-running expiry listener task lifecycle. |
| `RedisPubSubPlugin` | Depends on `RedisPlugin`. Decorates handlers and messenger at startup to fan out Redis notifications. |
| `SSEEventsPlugin` | Self-contained real-time streaming plugin. Constructs `SSEEventHub` at configure time so the messenger middleware can be registered before the app is built. |
| `AuthPlugin` | Stateless configure-only plugin. Delegates all auth logic to `AuthStrategy` + `AuthMiddleware`. |
| `WebhookPlugin` | Mounts a third-party webhook route. Processor mode provides the full `WappaContextFactory` → `with_context()` pipeline. |
| `CronPlugin` | Wraps `fastapi-crons` scheduler. Bridges each fired cron into the `WappaEventHandler.process_cron_event()` pipeline. |

## Plugin Lifecycle

```
WappaBuilder.add_plugin(plugin)
        │
        ▼
plugin.configure(builder)          ← sync; registers middleware, routers, hooks
        │
        ▼
WappaBuilder.build()               ← creates FastAPI app, attaches lifespan
        │
        ▼ (FastAPI lifespan start)
startup hooks sorted by priority   ← async; connections opened, state populated
        │
        ▼ (serving)
        │
        ▼ (FastAPI lifespan end)
shutdown hooks reverse priority    ← async; connections closed, state cleaned up
```

**Invariant**: `configure()` is always synchronous and runs before the `FastAPI` app exists. Any operation that requires an open connection (Redis ping, DB handshake, task spawning) belongs in a startup hook, not in `configure()`.

## Design Patterns

- **Protocol / structural typing**: `WappaPlugin` is a `typing.Protocol`. No base class, no inheritance tax.
- **Builder pattern**: Plugins express intent by calling `WappaBuilder` methods; the builder owns final assembly order.
- **Priority-based ordering**: Startup hooks run low → high (10 → 90); shutdown hooks run high → low (90 → 10). This guarantees infra teardown happens before core teardown.
- **Messenger middleware pipeline**: Cross-cutting outbound concerns (SSE, PubSub, caching, retry) are registered as `MessengerMiddleware` entries rather than subclassing the messenger. Priority bands: 10 reliability, 30 notifications, 50 cache, 70 lifecycle/SSE, 90 observability.
- **Fail-fast startup, fault-tolerant shutdown**: Startup hooks re-raise on error; shutdown hooks log and continue so one bad plugin cannot prevent others from cleaning up.
