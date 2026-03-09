# CORSPlugin

> Part of the Wappa Plugin Architecture. See [Architecture](./Architecture.md) for the plugin system overview, lifecycle, and patterns.

## What it does

`CORSPlugin` adds Cross-Origin Resource Sharing (CORS) middleware to Wappa applications. It wraps FastAPI's built-in `CORSMiddleware` with sensible defaults, allowing you to control which origins, HTTP methods, and headers are permitted in cross-origin requests.

This is a middleware-only plugin (Pattern 1 in the architecture) -- it registers `CORSMiddleware` during `configure()`, while `startup()` and `shutdown()` are no-ops.

## How to activate

Basic setup (allow all origins, GET only):

```python
from wappa import Wappa
from wappa.core.plugins import CORSPlugin

app = Wappa(cache="memory")
app.add_plugin(CORSPlugin())
```

Production setup with restricted origins:

```python
from wappa import Wappa
from wappa.core.plugins import CORSPlugin

app = Wappa(cache="memory")
app.add_plugin(
    CORSPlugin(
        allow_origins=["https://myapp.com", "https://www.myapp.com"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["*"],
    )
)
```

With `WappaBuilder`:

```python
from wappa.core.factory import WappaBuilder
from wappa.core.plugins import WappaCorePlugin, CORSPlugin

builder = WappaBuilder()
builder.add_plugin(WappaCorePlugin())
builder.add_plugin(
    CORSPlugin(
        allow_origins=["https://myapp.com"],
        allow_methods=["GET", "POST"],
    )
)
app = builder.build()
```

## Configuration options

| Parameter | Type | Default | Description |
|---|---|---|---|
| `allow_origins` | `list[str]` | `["*"]` | Origins permitted to make cross-origin requests. Use `["*"]` to allow all |
| `allow_methods` | `list[str]` | `["GET"]` | HTTP methods allowed in cross-origin requests |
| `allow_headers` | `list[str]` | `[]` | Request headers allowed in cross-origin requests. Use `["*"]` to allow all |
| `allow_credentials` | `bool` | `False` | Whether cookies and auth headers are allowed in cross-origin requests |
| `expose_headers` | `list[str]` | `[]` | Response headers accessible to the browser via JavaScript |
| `max_age` | `int` | `600` | How long (in seconds) browsers can cache preflight responses |
| `priority` | `int` | `90` | Middleware execution priority (lower runs first/outer) |
| `**cors_kwargs` | `Any` | -- | Additional keyword arguments forwarded to FastAPI's `CORSMiddleware` |

## Common configurations

**Development** -- permissive, allow everything:

```python
CORSPlugin(
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**Production** -- locked down to specific origins with credentials:

```python
CORSPlugin(
    allow_origins=["https://myapp.com", "https://admin.myapp.com"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
    expose_headers=["X-Request-Id"],
    max_age=3600,
)
```

> **Note**: When `allow_credentials=True`, `allow_origins` must not be `["*"]` -- browsers reject wildcard origins with credentials. List your origins explicitly instead.

## Middleware execution order

```
Request -> CORS(90) -> ErrorHandler(80) -> RequestLogging(70) -> Auth(60) -> Route
```

CORSPlugin runs at priority 90 (outermost middleware) so that CORS headers are applied before any other middleware can reject the request. This ensures preflight `OPTIONS` requests receive proper CORS headers even if downstream middleware would otherwise block them.
