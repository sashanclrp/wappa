# Plugins and middleware

## Contents

- How an app is assembled
- Startup order
- Auth
- CORS
- Rate limiting
- HTTP middleware
- Messenger middleware
- SSE events to a frontend

## How an app is assembled

```python
from wappa import Wappa
from wappa.core.plugins import AuthPlugin, BearerTokenStrategy, CORSPlugin

app = Wappa(cache="redis")                       # adds the core plugin and, for redis, RedisPlugin
app.set_event_handler(MasterEventHandler())
app.add_plugin(AuthPlugin(BearerTokenStrategy(os.environ["API_TOKEN"])))
app.add_plugin(CORSPlugin(allow_origins=["https://app.example.com"], allow_methods=["GET", "POST"]))
```

Every plugin import is `from wappa.core.plugins import ...` (`ExpiryPlugin` is also exported from `wappa`). `Wappa` methods chain: `add_plugin`, `add_router(router, public=False)`, `add_middleware(cls, priority=50)`, `add_startup_hook(fn, priority=50)`, `add_shutdown_hook`, `register_webhook_field(field_name, parser, handler, platform=PlatformType...)`, `set_identity_resolver`, `configure(**overrides)`. Embedded Hosts that need full control compose a `WappaBuilder` instead. A bare `WappaBuilder()` has no core plugin and no Meta webhook router, so prefer `Wappa(...)` unless you mean it. A plugin is any object with a synchronous `configure(builder)` (`WappaPlugin`); its async work goes in startup and shutdown hooks it registers.

## Startup order

Startup hooks run from low to high priority, shutdown in reverse, and a failing startup hook stops the app. Built-in priorities: core 10, Redis 20, Redis Pub/Sub 22, SSE 24, Postgres and Expiry 25, Webhook, Cron and RateLimit 30, Host hooks 50 by default. A Host hook that needs Redis or the database registers at 50 or later. Don't add `RedisPlugin` yourself when `cache="redis"`: it is already there, and a second one runs twice.

## Auth

`AuthPlugin(strategy, protect=None, exclude=None, sse_token_param="token", expose_user=True, middleware_priority=60)` with `BearerTokenStrategy(token)`, `BasicAuthStrategy(username, password)` or `JWTStrategy(secret=..., or jwks_url=..., algorithms=, audience=, issuer=)`. Pass `protect=[...]` (only these prefixes) or `exclude=[...]`, not both. Routers mounted with `public=True` (the Meta webhooks, health, External Webhook Sources) are always skipped, because they authenticate by signature. `/api/sse/events` accepts the token as `?token=` for browsers' `EventSource`. A custom strategy implements `async authenticate(request) -> AuthResult(authenticated, user, error, metadata)` (`from wappa.core.plugins import AuthResult, AuthStrategy`); use it to check that the caller owns the `X-Wappa-Inbox-ID` it sends.

## CORS

`CORSPlugin(allow_origins=None, allow_methods=None, allow_headers=None, allow_credentials=False, expose_headers=None, max_age=600, priority=90)`. The defaults are `["*"]` origins and `GET` only, so list your frontend origins and methods. Priority 90 makes it an inner middleware; give it a low priority (outer) if preflight requests must bypass auth.

## Rate limiting

```python
from wappa.core.plugins import RateLimitPlugin, RateLimitProfile, rate_limit
app.add_plugin(RateLimitPlugin([RateLimitProfile("sends", limit=60, window_seconds=60, key_by="inbox_id")]))

@router.post("/{platform}/notify", dependencies=[Depends(rate_limit("sends"))])
async def notify(platform: str) -> dict: ...
```

`key_by` is `client_ip`, `inbox_id` or `inbox_id_and_client_ip`. The limiter is in-process and fixed-window: each worker counts on its own. This is your API's limit. Meta's limits are handled by Wappa's governor (`rate_limited` results).

## HTTP middleware

`app.add_middleware(MyASGIMiddleware, priority=50, **kwargs)` or `CustomMiddlewarePlugin(cls, priority=50, name=None, **kwargs)`. Lower priority is outer (runs first on the request).

## Messenger middleware

Messenger middleware wraps every outbound `IMessenger` call: Handler, API, jobs and Templates alike. Use it for a 24-hour window guard, auditing, human-takeover pauses or metrics:

```python
from wappa.messaging import MessageResult, MessengerMiddleware, SendInvocation, SendNext

class AuditMiddleware:
    name = "audit"
    async def handle(self, invocation: SendInvocation, call_next: SendNext) -> MessageResult:
        result = await call_next(invocation)       # or return early to block the send
        await audit_log(invocation.method_name, invocation.target, result.message_id)
        return result
```

`Wappa` has no `add_messenger_middleware`; register it from a small plugin, whose `configure` receives the builder:

```python
class AuditPlugin:
    def configure(self, builder) -> None:
        builder.add_messenger_middleware(AuditMiddleware(), priority=90)

app.add_plugin(AuditPlugin())
```

To block a send, return a failed result without calling `call_next`: `MessageResult(success=False, platform=invocation.target.inbox_ref.platform, error="outside the 24-hour window", error_code="WINDOW_CLOSED")`. `invocation.method_name` tells Templates (`send_text_template`, `send_media_template`, `send_location_template`) from free-form sends. The priority bands are 10 reliability, 30 notifications, 50 cache, 70 lifecycle, 90 observability. Middleware is built once per app; read per-request identity from `invocation.target` (its `inbox_ref`), never from globals. HTTP API sends run the same middleware, so a guard written for bot replies also stops operator sends unless it checks `invocation`.

## SSE events to a frontend

`SSEEventsPlugin()` serves `GET /api/sse/events` (subscribe) and `GET /api/sse/status`, publishing incoming messages, API sends, bot replies, statuses and webhook errors. Publish your own events with `from wappa.sse import publish_sse_event, register_sse_event_type`. The default `SSEEventHub` is process-local. For several replicas, inject your own `SSEHub` (`event_hub=` or `event_hub_factory=`) backed by a broker: remote events enter through `deliver_envelope()`, never `publish()`, so they aren't rebroadcast and keep their IDs. When a subscriber's queue overflows (`queue_size`, default 200), Wappa closes only that subscription with `backpressure_gap`. The frontend reconnects and reloads durable state: SSE is a live feed, not a ledger.
