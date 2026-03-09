# WappaCorePlugin

> Part of the Wappa Plugin System -- see [Architecture](./Architecture.md) for the full plugin lifecycle and protocol reference.

## What It Does

`WappaCorePlugin` is the foundation plugin for every Wappa application. It establishes the core infrastructure that all other plugins and application code depend on: logging, HTTP session management, middleware stack, routing, and cache configuration.

Because it owns the lowest-level concerns, its startup hook runs **first** (priority 10) and its shutdown hook runs **last** (priority 90), guaranteeing that core resources are available for the entire lifetime of the application.

## How to Activate

### Automatic (default)

The `Wappa` class adds `WappaCorePlugin` automatically -- no action required:

```python
from wappa import Wappa

app = Wappa(
    whatsapp_token="...",
    whatsapp_phone_id="...",
    whatsapp_business_id="...",
)
# WappaCorePlugin is already registered internally.
```

### Manual (via WappaBuilder)

When assembling an application manually with `WappaBuilder`, register the plugin explicitly:

```python
from wappa.core.plugins.wappa_core_plugin import WappaCorePlugin
from wappa.core.types import CacheType

builder = WappaBuilder()
builder.add_plugin(WappaCorePlugin(cache_type=CacheType.MEMORY))
```

## What It Registers

During `configure()`, the plugin registers the following components with `WappaBuilder`:

### Middleware

| Middleware                 | Priority | Role                                      |
| ------------------------- | -------- | ----------------------------------------- |
| `OwnerMiddleware`         | 90       | Tenant/owner extraction (outermost layer) |
| `ErrorHandlerMiddleware`  | 80       | Global error handling                     |
| `RequestLoggingMiddleware`| 70       | HTTP request/response logging (innermost) |

### Routes

| Router             | Endpoints                             |
| ------------------ | ------------------------------------- |
| `health_router`    | `/health`, `/health/detailed`         |
| `whatsapp_router`  | `/api/whatsapp/...` (webhook + API)   |

### Lifecycle Hooks

| Hook             | Phase    | Priority | Description                         |
| ---------------- | -------- | -------- | ----------------------------------- |
| `_core_startup`  | Startup  | 10       | First to run -- initializes core    |
| `_core_shutdown` | Shutdown | 90       | Last to run -- cleans up core       |

## Startup Behavior

When the startup hook fires (priority 10, before any other plugin), the following sequence executes:

1. **Initialize logging** -- calls `setup_app_logging()` and obtains the application logger.
2. **Log environment info** -- version, environment, owner ID, log level, cache type.
3. **Set cache type in `app.state`** -- stores `app.state.wappa_cache_type` so the webhook controller and other components can detect the active cache backend.
4. **Create persistent HTTP session** -- an `aiohttp.ClientSession` with connection pooling (100 max connections, 30 s keep-alive, auto-cleanup of closed connections, 30 s total timeout). Stored on `app.state.http_session`.
5. **Log available endpoints** -- health check, WhatsApp API, and API documentation URLs.
6. **Display webhook URLs** -- generates and logs the WhatsApp webhook URL via `webhook_url_factory` for easy copy-paste into Meta Business settings.

If any step fails, the error is logged (or printed to stdout if logging itself failed) and the exception is re-raised to prevent the application from starting in a broken state.

## Shutdown Behavior

When the shutdown hook fires (priority 90, after all other plugins have shut down):

1. **Close HTTP session** -- gracefully closes the `aiohttp.ClientSession` and its underlying TCP connector.
2. **Clear app state** -- removes `wappa_cache_type` from `app.state`.
3. **Log completion** -- confirms clean shutdown or logs any errors encountered.

## Configuration Options

`WappaCorePlugin` accepts a single constructor parameter:

| Parameter    | Type        | Default            | Description                                |
| ------------ | ----------- | ------------------ | ------------------------------------------ |
| `cache_type` | `CacheType` | `CacheType.MEMORY` | Cache backend for the application to use.  |

Supported `CacheType` values are defined in `wappa.core.types`:

- `CacheType.MEMORY` -- in-memory cache (fast, non-persistent, default)

The cache type can also be changed before startup via `set_cache_type()`:

```python
plugin = WappaCorePlugin()
plugin.set_cache_type(CacheType.MEMORY)
```

## Middleware Execution Order

Higher priority numbers execute closer to the route handler (added to the ASGI stack later, so they wrap inner). The resulting request/response flow is:

```
  Request
    |
    v
┌──────────────────────────┐
│  RequestLoggingMiddleware │  priority 70  (innermost middleware)
│  ┌────────────────────┐  │
│  │ ErrorHandlerMiddle… │  priority 80
│  │  ┌──────────────┐  │  │
│  │  │ OwnerMiddle… │  priority 90  (outermost middleware)
│  │  │  ┌────────┐  │  │  │
│  │  │  │ Route  │  │  │  │
│  │  │  └────────┘  │  │  │
│  │  └──────────────┘  │  │
│  └────────────────────┘  │
└──────────────────────────┘
    |
    v
  Response
```

**Reading the diagram**: a request first hits `RequestLoggingMiddleware` (logs the incoming request), then `ErrorHandlerMiddleware` (catches exceptions), then `OwnerMiddleware` (extracts tenant context), and finally reaches the route handler. The response travels back through the same layers in reverse order.
