# AuthPlugin

> Part of the Wappa Plugin Architecture. See [Architecture](./Architecture.md) for the plugin system overview, lifecycle, and patterns.

## What it does

`AuthPlugin` adds authentication middleware to Wappa applications using a pluggable strategy pattern. It ships with three built-in strategies:

- **BearerTokenStrategy** -- static bearer token comparison (constant-time)
- **BasicAuthStrategy** -- HTTP Basic Auth with constant-time username + password comparison
- **JWTStrategy** -- PyJWT-based token validation with configurable secret, algorithms, audience, and issuer

It also supports **SSE query-param token promotion**: when a request hits `/api/sse/*` without an `Authorization` header, the middleware reads `?token=<value>` and promotes it to a `Bearer` header before authenticating.

## How to activate

```python
from wappa import Wappa
from wappa.core.plugins import AuthPlugin, BearerTokenStrategy

app = Wappa(cache="memory")
app.add_plugin(
    AuthPlugin(
        strategy=BearerTokenStrategy(token="my-secret-token"),
    )
)
```

With `WappaBuilder`:

```python
from wappa.core.factory import WappaBuilder
from wappa.core.plugins import WappaCorePlugin, AuthPlugin, BearerTokenStrategy

builder = WappaBuilder()
builder.add_plugin(WappaCorePlugin())
builder.add_plugin(
    AuthPlugin(strategy=BearerTokenStrategy(token="my-secret-token"))
)
app = builder.build()
```

## Strategies

**Bearer Token** -- simplest option for API keys:

```python
from wappa.core.plugins import AuthPlugin, BearerTokenStrategy

AuthPlugin(strategy=BearerTokenStrategy(token="my-api-key"))
```

**Basic Auth** -- username/password:

```python
from wappa.core.plugins import AuthPlugin, BasicAuthStrategy

AuthPlugin(strategy=BasicAuthStrategy(username="admin", password="secret"))
```

**JWT** -- full token validation (requires PyJWT, bundled as dependency):

```python
from wappa.core.plugins import AuthPlugin, JWTStrategy

AuthPlugin(
    strategy=JWTStrategy(
        secret="my-jwt-secret",
        algorithms=["HS256"],
        audience="my-app",
        issuer="my-issuer",
    )
)
```

## Configuration options

| Parameter | Type | Default | Description |
|---|---|---|---|
| `strategy` | `AuthStrategy` | (required) | Authentication strategy to use |
| `protect` | `list[str] \| None` | `None` | Protect mode: only these path prefixes require auth. Mutually exclusive with `exclude` |
| `exclude` | `list[str] \| None` | `None` | Exclude mode: additional path prefixes to skip auth (merged with defaults). Mutually exclusive with `protect` |
| `sse_token_param` | `str` | `"token"` | Query param name for SSE token promotion |
| `expose_user` | `bool` | `True` | Set `request.state.auth_user` and `request.state.auth_metadata` on success |
| `middleware_priority` | `int` | `60` | Middleware execution priority |

## Exclude vs Protect mode

The plugin operates in one of two **mutually exclusive** modes. Passing both `protect` and `exclude` raises a `ValueError`.

### Exclude mode (default)

**All paths require auth** except those matching an exclude prefix. This is the default when you pass neither parameter or only `exclude`.

Default excluded paths are always included:

- `/health`
- `/api/sse/status`
- `/webhook/messenger`
- `/docs`
- `/openapi.json`
- `/redoc`

Add your own exclusions on top of the defaults:

```python
AuthPlugin(
    strategy=BearerTokenStrategy(token="my-token"),
    exclude=["/public", "/landing"],
)
# Protected: everything
# Excluded: defaults + /public + /landing
```

Path matching is prefix-based (`startswith`), so `/healthcheck` also matches the `/health` exclusion.

### Protect mode

**Only paths matching a protect prefix require auth**; everything else passes through freely. Default excludes do not apply in this mode (they're unnecessary since unmatched paths are already open).

```python
AuthPlugin(
    strategy=BearerTokenStrategy(token="my-token"),
    protect=["/api/admin", "/api/users"],
)
# Protected: /api/admin/* and /api/users/*
# Open: everything else (including /docs, /health, etc.)
```

### Invalid: both at once

```python
# This raises ValueError
AuthPlugin(
    strategy=BearerTokenStrategy(token="my-token"),
    protect=["/api/admin"],
    exclude=["/public"],
)
```

## SSE token promotion

Since `EventSource` in browsers cannot set custom headers, the middleware supports query-param authentication for SSE endpoints:

```javascript
// Frontend -- pass token as query param
const url = new URL("/api/sse/events", window.location.origin);
url.searchParams.set("token", "my-secret-token");
const source = new EventSource(url.toString());
```

The middleware detects requests to `/api/sse/*` without an `Authorization` header, reads the `?token=` param, and injects it as a `Bearer` header before authenticating.

## Accessing auth info in handlers

When `expose_user=True` (default), authenticated user info is available on `request.state`:

```python
@app.get("/api/whoami")
async def whoami(request: Request):
    user = request.state.auth_user      # strategy-specific user dict or JWT payload
    meta = request.state.auth_metadata  # e.g. {"token_type": "jwt"}
    return {"user": user, "metadata": meta}
```

## Custom strategies

Implement the `AuthStrategy` protocol to create your own:

```python
from starlette.requests import Request
from wappa.core.auth import AuthResult, AuthStrategy

class MyCustomStrategy:
    async def authenticate(self, request: Request) -> AuthResult:
        api_key = request.headers.get("x-api-key")
        if api_key == "valid":
            return AuthResult(authenticated=True, user={"key": api_key})
        return AuthResult(authenticated=False, error="Invalid API key")

AuthPlugin(strategy=MyCustomStrategy())
```

## Middleware execution order

```
Request -> Owner(90) -> ErrorHandler(80) -> RequestLogging(70) -> Auth(60) -> Route
```

AuthPlugin is a middleware-only plugin (Pattern 1 in the architecture). It registers `AuthMiddleware` during `configure()` at priority 60, while `startup()` and `shutdown()` are no-ops.
