# CustomMiddlewarePlugin

> Part of the Wappa Plugin Architecture. See [Architecture](./Architecture.md) for the plugin system overview, lifecycle, and patterns.

## What it does

`CustomMiddlewarePlugin` is a generic wrapper that registers any user-provided middleware class into the Wappa application. It accepts the middleware class, an optional priority, an optional display name (for logging), and forwards any extra keyword arguments to the middleware constructor.

This is the go-to plugin when you need to add custom behavior at the middleware layer -- request logging, security headers, monitoring, request timing, or anything else that operates on the request/response cycle.

## How to activate

**Request logging middleware:**

```python
from wappa import Wappa
from wappa.core.plugins import CustomMiddlewarePlugin
from myapp.middleware import RequestLoggingMiddleware

app = Wappa(cache="memory")
app.add_plugin(
    CustomMiddlewarePlugin(
        RequestLoggingMiddleware,
        priority=60,
        name="RequestLogging",
        log_level="INFO",
    )
)
```

**Security headers middleware:**

```python
from wappa.core.plugins import CustomMiddlewarePlugin
from myapp.middleware import SecurityHeadersMiddleware

app.add_plugin(
    CustomMiddlewarePlugin(
        SecurityHeadersMiddleware,
        priority=85,
        name="SecurityHeaders",
        include_hsts=True,
        include_csp=True,
    )
)
```

**Monitoring / metrics middleware:**

```python
from wappa.core.plugins import CustomMiddlewarePlugin
from myapp.middleware import PrometheusMiddleware

app.add_plugin(
    CustomMiddlewarePlugin(
        PrometheusMiddleware,
        priority=95,
        name="Metrics",
        endpoint="/metrics",
    )
)
```

With `WappaBuilder`:

```python
from wappa.core.factory import WappaBuilder
from wappa.core.plugins import WappaCorePlugin, CustomMiddlewarePlugin
from myapp.middleware import RequestLoggingMiddleware

builder = WappaBuilder()
builder.add_plugin(WappaCorePlugin())
builder.add_plugin(
    CustomMiddlewarePlugin(
        RequestLoggingMiddleware,
        priority=60,
        log_level="DEBUG",
    )
)
app = builder.build()
```

## Configuration options

| Parameter | Type | Default | Description |
|---|---|---|---|
| `middleware_class` | `type` | (required) | The middleware class to register. Must be a valid ASGI/Starlette middleware |
| `priority` | `int` | `50` | Middleware execution priority (lower runs first / outermost layer) |
| `name` | `str \| None` | `None` | Display name used in log messages. Falls back to `middleware_class.__name__` |
| `**kwargs` | `Any` | -- | All extra keyword arguments are forwarded to the middleware class constructor |

## Priority guidelines

Priority controls when middleware runs relative to other middleware. Lower values run first (outermost layer), higher values run last (closest to the route handler).

| Range | Use case | Examples |
|---|---|---|
| 90+ | Outermost concerns | Owner identification, request ID injection |
| 80-89 | Error handling | Global error handler, exception formatting |
| 70-79 | Observability | Request logging, metrics collection |
| 60-69 | Authentication / Authorization | Auth checks, token validation |
| 50 | Default | General-purpose middleware |
| 40-49 | Request transformation | Body parsing, header normalization |
| 30-39 | Business logic middleware | Rate limiting, feature flags |
| < 30 | Innermost concerns | Response formatting, compression |

Choose a priority that reflects where your middleware should sit in the request/response pipeline relative to other middleware.

## Middleware execution order

```
Request -> Owner(90) -> ErrorHandler(80) -> Logging(70) -> Auth(60) -> Custom(50) -> Route
```

`CustomMiddlewarePlugin` is a middleware-only plugin (Pattern 1 in the architecture). It registers the provided middleware class during `configure()` via `builder.add_middleware()`, while `startup()` and `shutdown()` simply emit debug log messages.
