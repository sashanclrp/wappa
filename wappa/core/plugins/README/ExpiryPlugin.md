# ExpiryPlugin

> Part of the Wappa Plugin Architecture. See [Architecture](./Architecture.md) for the plugin system overview, lifecycle, and patterns.

## What it does

`ExpiryPlugin` manages the lifecycle of a Redis key-expiry listener as a background `asyncio.Task`. When Redis keys expire, the listener picks up the expiration events and dispatches them to registered expiry action handlers. The plugin takes care of:

- Verifying the Redis expiry pool is available at startup
- Spawning the background listener task (`run_expiry_listener()`)
- Storing the task reference in `app.state` for external monitoring
- Cancelling the listener gracefully on shutdown (5-second timeout)
- Automatic reconnection on transient Redis errors

## How to activate

```python
from wappa import Wappa
from wappa.core.plugins import ExpiryPlugin

app = Wappa(cache="redis", redis_url="redis://localhost:6379")
app.add_plugin(ExpiryPlugin())
```

With `WappaBuilder`:

```python
from wappa.core.factory import WappaBuilder
from wappa.core.plugins import WappaCorePlugin, RedisPlugin, ExpiryPlugin

builder = WappaBuilder()
builder.add_plugin(WappaCorePlugin())
builder.add_plugin(RedisPlugin(url="redis://localhost:6379"))
builder.add_plugin(ExpiryPlugin())
app = builder.build()
```

## Configuration options

| Parameter | Type | Default | Description |
|---|---|---|---|
| `alias` | `str` | `"expiry"` | Redis pool alias used for expiry key subscriptions |
| `reconnect_delay` | `int` | `10` | Seconds to wait before reconnecting after a listener error |
| `max_reconnect_attempts` | `int \| None` | `None` | Maximum reconnection attempts. `None` means infinite retries |

```python
ExpiryPlugin(
    alias="expiry",
    reconnect_delay=10,
    max_reconnect_attempts=None,  # infinite retries
)
```

## How it works

ExpiryPlugin uses the **Hook-Based pattern** (Pattern 2) -- it registers startup and shutdown hooks at priority 25, which runs after RedisPlugin (priority 20).

### Startup sequence

1. Verify `RedisManager` is initialized (raises `RuntimeError` if not)
2. Verify the expiry pool exists by calling `RedisManager.get_client(alias)`
3. Create a background `asyncio.Task` running `run_expiry_listener()` with the configured alias, reconnect delay, and max attempts
4. Store the task in `app.state.expiry_listener_task`
5. Set the FastAPI app reference globally so expiry handlers can access the HTTP session

### Shutdown sequence

1. Cancel the listener task if it is still running
2. Wait up to 5 seconds for graceful shutdown (`asyncio.wait_for`)
3. Remove `expiry_listener_task` from `app.state`
4. Log completion -- errors during shutdown are logged but not re-raised to avoid blocking other shutdown hooks

## Monitoring

Two static methods are available for checking listener health at runtime:

```python
from wappa.core.plugins import ExpiryPlugin

# Get the raw asyncio.Task (or None if not started)
task = ExpiryPlugin.get_listener_task(app)

# Boolean check -- True when task exists and is not done
running = ExpiryPlugin.is_listener_running(app)
```

These can be wired into health-check endpoints or observability dashboards.

## Dependencies

`ExpiryPlugin` **requires** `RedisPlugin` (or equivalent Redis initialization) to be configured and started first. The plugin verifies this at startup and raises `RuntimeError` if Redis is not available.

Hook priority ordering ensures correct sequencing:

```
RedisPlugin (priority 20) -> ExpiryPlugin (priority 25)
```
