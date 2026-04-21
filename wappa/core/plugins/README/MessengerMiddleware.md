# Messenger Middleware Pipeline

> Part of the Wappa Plugin Architecture. See [Architecture](./Architecture.md) for the full plugin system overview.

## What it is

Every outbound call to `self.messenger.send_*(...)` flows through a priority-ordered **middleware pipeline** assembled once per request. Each middleware wraps the next (ASGI-style), so cross-cutting concerns — caching, SSE lifecycle events, pub/sub notifications, retry, metrics, tracing — live in a single small class each, instead of being hand-rolled into inheritance-based wrappers.

The pipeline is exposed through one public API on `WappaBuilder`:

```python
builder.add_messenger_middleware(middleware, priority=50)
```

That's the extension point. Plugins use it. Downstream apps use it. The `WebhookController` stays agnostic of which concerns are active.

Source: `wappa/core/messaging/pipeline.py`

## Why it exists (what it replaced)

Before v0.4.0, cross-cutting concerns were expressed as **`IMessenger` wrappers** that re-implemented all 18 messaging methods to slip in a pre/post hook. Each wrapper was ~300–465 lines of delegation boilerplate. Composing them was hardcoded in the webhook controller:

```python
# Old shape — webhook_controller.py pre-v0.4.0
if app.state.pubsub_wrap_messenger:
    messenger = PubSubMessengerWrapper(inner=messenger, tenant=..., user_id=...)
if app.state.sse_wrap_messenger:
    messenger = SSEMessengerWrapper(inner=messenger, event_hub=...)
```

Downstream apps that needed to inject a custom concern (e.g., a cache write that must complete *before* the SSE `outgoing_bot_message` fires) had to drill the framework's private attributes:

```python
# Old workaround — downstream code
raw = app_messenger._inner._inner            # underscore drilling, breaks on upgrades
hub = app_messenger._event_hub               # private-by-convention
app_messenger = SSEMessengerWrapper(
    inner=CacheMessengerWrapper(inner=raw, ...),
    event_hub=hub,
)
```

This violated every architectural rule the framework claims to follow: SRP (each wrapper conflated delegation, ordering, serialization, and emission), OCP (controller had to change for every new concern), DIP (plugins communicated with the controller through `app.state` boolean flags), and DRY (each new concern = 300 lines of copy-pasted delegation).

The pipeline is the fix. The 18 `IMessenger` methods are implemented **once** in `MessengerPipeline`. Every middleware is ~40–60 LOC. The controller is agnostic. No private access. No flags.

## Priority bands

Priority determines ordering. Lower = closer to the raw transport (inner); higher = closer to the caller (outer). Higher-priority middleware runs its pre-hook first and its post-hook last — which means its post-hook runs **after** any lower-priority middleware has completed.

This is the mechanism that guarantees "cache write finishes before SSE publishes": the cache middleware sits at priority 50 (inner), the SSE middleware sits at priority 70 (outer), and SSE's `publish_sse_event` call only runs after the whole inner chain — including the cache write — has returned.

| Priority | Band | Used for | Example |
|---|---|---|---|
| 10 | Reliability | retry, circuit-breaker, timeout enforcement | (reserved) |
| 30 | Domain notifications | fire-and-forget pub/sub, analytics taps | `PubSubNotificationMiddleware` |
| 50 | Caching / persistence | write-through cache, conversation history | downstream `CacheMessengerMiddleware` |
| 70 | Lifecycle events | transport-level event publishing (SSE) | `SSELifecycleMiddleware` |
| 90 | Observability | metrics, distributed tracing, audit log | (reserved) |

The bands are a convention, not an enforcement. Any integer works — but following the bands keeps ordering predictable across plugins that don't know about each other.

Constants for the bands are exported from `wappa.core.messaging.pipeline`:

```python
from wappa.core.messaging.pipeline import (
    PRIORITY_RELIABILITY,     # 10
    PRIORITY_NOTIFICATIONS,   # 30
    PRIORITY_CACHE,           # 50
    PRIORITY_LIFECYCLE,       # 70
    PRIORITY_OBSERVABILITY,   # 90
)
```

## Call flow

With `CacheMiddleware (50)` and `SSELifecycleMiddleware (70)` registered:

```
caller: await self.messenger.send_text("hi", recipient)
  │
  ▼
MessengerPipeline.send_text
  │  builds SendInvocation(method_name="send_text", message_type="text", ...)
  ▼
SSELifecycleMiddleware.handle        ── pre: flush_incoming_sse()
  │
  ▼
CacheMiddleware.handle               ── pre: (no-op)
  │
  ▼
raw.send_text(...)                   ── actual HTTP call to WhatsApp
  │  returns MessageResult
  ▼
CacheMiddleware.handle (returning)   ── post: write result to Redis
  │
  ▼
SSELifecycleMiddleware (returning)   ── post: publish "outgoing_bot_message"
  │
  ▼
caller receives MessageResult
```

Key property: the SSE publish happens strictly **after** the cache write. The ordering is declarative (priorities), not topological (wrapper nesting).

## The `SendInvocation` contract

Each outbound call is captured into an immutable `SendInvocation`:

```python
@dataclass(frozen=True, slots=True)
class SendInvocation:
    method_name: str              # "send_button_message"
    message_type: str             # "button" (platform-agnostic label)
    recipient: str                # routing-level identity (BSUID / phone / ID)
    args: tuple[Any, ...]         # positional args for the raw call
    kwargs: Mapping[str, Any]     # keyword args for the raw call
    arguments: Mapping[str, Any]  # same data keyed by parameter name (for events)
```

Middleware reads `method_name` / `message_type` / `recipient` for routing or filtering decisions, and `arguments` when it needs to emit a JSON-serializable payload (`SendInvocation.to_request_payload()` does that uniformly).

If a middleware needs to rewrite the call (e.g., recipient rewriting, argument normalization), it constructs a new invocation via `invocation.with_arguments(...)` and passes that to `call_next`. Rewrites are explicit, not accidental.

## Writing a custom middleware

The minimum implementation is a class with a `name` attribute and an async `handle(invocation, call_next)` method — the `MessengerMiddleware` Protocol.

### Pure observer (the common case)

Run work after the send returns, don't touch the result. Example: write the outgoing message to a cache so a frontend can read it via REST.

```python
from wappa.core.messaging.pipeline import (
    MessengerMiddleware,
    SendInvocation,
    SendNext,
    PRIORITY_CACHE,
)
from wappa.messaging.whatsapp.models.basic_models import MessageResult


class CacheMessengerMiddleware(MessengerMiddleware):
    name = "app_cache"

    def __init__(self, cache) -> None:
        self._cache = cache

    async def handle(
        self,
        invocation: SendInvocation,
        call_next: SendNext,
    ) -> MessageResult:
        result = await call_next(invocation)
        if result.success:
            await self._cache.set(
                key=f"msg:{result.message_id}",
                value=invocation.to_request_payload(),
            )
        return result


# Registration — register before .build() so the pipeline sees it:
builder.add_messenger_middleware(
    CacheMessengerMiddleware(cache=redis_cache),
    priority=PRIORITY_CACHE,
)
```

### Reliability middleware (the less common case)

Wrap the inner chain with retry logic. Demonstrates that middleware can also *modify control flow*, not just observe.

```python
class RetryMiddleware(MessengerMiddleware):
    name = "retry"

    def __init__(self, attempts: int = 3) -> None:
        self._attempts = attempts

    async def handle(self, invocation, call_next):
        last_exc: Exception | None = None
        for _ in range(self._attempts):
            try:
                return await call_next(invocation)
            except TransientSendError as exc:
                last_exc = exc
        raise last_exc  # exhausted retries


builder.add_messenger_middleware(RetryMiddleware(attempts=3), priority=PRIORITY_RELIABILITY)
```

### Reading request identity

Middleware is **app-scoped** (constructed once at `configure()` time) and shared across requests. Per-request identity — tenant, user, BSUID, phone — comes from the active `SSEEventContext`, which the framework entry points (webhook / API / expiry) set for every request.

```python
from wappa.core.sse.context import get_sse_context

class TenantAwareMiddleware(MessengerMiddleware):
    name = "tenant_aware"

    async def handle(self, invocation, call_next):
        ctx = get_sse_context()
        tenant = ctx.tenant_id if ctx else "unknown"
        # ... use tenant without per-request construction
        return await call_next(invocation)
```

Never construct middleware per-request. If you find yourself wanting to, the middleware is doing something that belongs inside `handle` via the context, not in `__init__`.

### Short-circuiting

Middleware can skip `call_next` entirely to replace the real send — useful for dry-runs, feature flags, or safe-mode toggles. Return a `MessageResult` and the framework treats the send as completed.

```python
class DryRunMiddleware(MessengerMiddleware):
    name = "dry_run"

    async def handle(self, invocation, call_next):
        # Log what would have been sent, return a fake success.
        logger.info("DRY RUN: %s → %s", invocation.method_name, invocation.recipient)
        return MessageResult(
            success=True,
            message_id=f"dryrun-{uuid4()}",
            recipient=invocation.recipient,
        )
```

## Built-in middleware

| Middleware | Registered by | Priority | Purpose |
|---|---|---|---|
| `SSELifecycleMiddleware` | `SSEEventsPlugin` | 70 | Publishes `outgoing_bot_message` after each successful send |
| `PubSubNotificationMiddleware` | `RedisPubSubPlugin` | 30 | Publishes `bot_reply` notification on Redis pub/sub |

Both are internal to their plugins — activating the plugin is how you get the middleware. You do not register them manually.

## Introspection

`MessengerPipeline` exposes two read-only properties for debugging and tests — **no underscore drilling required**:

```python
pipeline: MessengerPipeline = request_handler.messenger
pipeline.raw_messenger            # the underlying transport (IMessenger)
pipeline.middleware_chain         # tuple of registered middleware, outer → inner
```

## Legacy wrappers (deprecated)

`SSEMessengerWrapper` and `PubSubMessengerWrapper` are kept as thin shims that emit a `DeprecationWarning` on construction. They work for one more minor version and will be removed in v0.6.0. Any code that imports them directly — especially code that reads `._inner` or `._event_hub` — should migrate to `add_messenger_middleware` instead:

```python
# Deprecated
from wappa.core.sse import SSEMessengerWrapper
messenger = SSEMessengerWrapper(inner=raw, event_hub=hub)

# New
# (done automatically when SSEEventsPlugin is added)
builder.add_plugin(SSEEventsPlugin())
```

## Future work

A full **Domain Event Bus** (where SSE, pub/sub, and app caches become *subscribers* of typed domain events rather than middleware in the send path) is tracked in `backlog/260420-messenger-middleware-domain-event-bus.md`. It is **not** planned for the next release — the bus has value only once there are multiple observers of the same event, which the current middleware surface already handles adequately.

## Related docs

- [Architecture](./Architecture.md) — plugin lifecycle and priority system
- [SSEEventsPlugin](./SSEEventsPlugin.md) — how SSE consumes the pipeline
- [RedisPubSubPlugin](./RedisPubSubPlugin.md) — how pub/sub consumes the pipeline
