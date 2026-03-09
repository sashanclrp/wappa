# RateLimitPlugin (Work in Progress)

> Part of the Wappa Plugin Architecture. See [Architecture](./Architecture.md) for the plugin system overview, lifecycle, and patterns.

## What it does

`RateLimitPlugin` is a BYOM (bring-your-own-middleware) plugin that wraps a user-provided rate limiting middleware class into the Wappa plugin system. It does not ship with a built-in rate limiter -- you supply the middleware class and its configuration, and the plugin handles registration with proper priority ordering.

This gives you full control over the rate limiting strategy (fixed window, sliding window, token bucket, etc.) and backend (in-memory, Redis, database) while keeping your middleware integrated with the Wappa plugin lifecycle.

## How to activate

```python
from wappa import Wappa
from wappa.core.plugins import RateLimitPlugin
from your_app.middleware import RateLimiterMiddleware

app = Wappa(cache="memory")
app.add_plugin(
    RateLimitPlugin(
        RateLimiterMiddleware,
        max_requests=100,
        window_seconds=60,
    )
)
```

With `WappaBuilder`:

```python
from wappa.core.factory import WappaBuilder
from wappa.core.plugins import WappaCorePlugin, RateLimitPlugin
from your_app.middleware import RateLimiterMiddleware

builder = WappaBuilder()
builder.add_plugin(WappaCorePlugin())
builder.add_plugin(
    RateLimitPlugin(
        RateLimiterMiddleware,
        max_requests=100,
        window_seconds=60,
    )
)
app = builder.build()
```

## Configuration options

| Parameter | Type | Default | Description |
|---|---|---|---|
| `rate_limit_middleware_class` | `type` | (required, positional) | The middleware class to register. Must be a valid Starlette/FastAPI middleware |
| `priority` | `int` | `70` | Middleware execution priority (lower runs first/outer) |
| `**kwargs` | `Any` | -- | All additional keyword arguments are forwarded directly to the middleware class constructor |

The `**kwargs` you pass depend entirely on your middleware class. Common examples include `max_requests`, `window_seconds`, `redis_url`, `key_func`, etc.

## Example with custom middleware class

**Basic in-memory rate limiter:**

```python
from wappa.core.plugins import RateLimitPlugin

# Your middleware class -- accepts kwargs from the plugin
class RateLimiterMiddleware:
    def __init__(self, app, max_requests: int = 100, window_seconds: int = 60):
        self.app = app
        self.max_requests = max_requests
        self.window_seconds = window_seconds

    async def __call__(self, scope, receive, send):
        # Your rate limiting logic here
        await self.app(scope, receive, send)

rate_limit_plugin = RateLimitPlugin(
    RateLimiterMiddleware,
    max_requests=100,
    window_seconds=60,
)
```

**Redis-backed rate limiter:**

```python
from wappa.core.plugins import RateLimitPlugin

rate_limit_plugin = RateLimitPlugin(
    RedisRateLimiterMiddleware,
    max_requests=1000,
    window_seconds=3600,
    redis_url="redis://localhost:6379",
)
```

## Middleware execution order

```
Request -> Owner(90) -> ErrorHandler(80) -> RateLimit(70) -> Auth(60) -> Route
```

RateLimitPlugin is a middleware-only plugin (Pattern 1 in the architecture). It registers the user-provided middleware class during `configure()` at priority 70 (by default), while `startup()` and `shutdown()` only emit debug log messages. Rate limiting runs before authentication so that abusive requests are rejected early, before spending resources on auth validation.
