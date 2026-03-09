# PostgresDatabasePlugin

> Part of the Wappa Plugin Architecture. See [Architecture](./Architecture.md) for the plugin system overview, lifecycle, and patterns.

## What it does

`PostgresDatabasePlugin` provides async PostgreSQL database integration for Wappa applications using the `asyncpg` driver and SQLAlchemy async sessions. It handles the full database lifecycle -- connection pooling, health checks, optional auto-table creation, and clean shutdown -- and injects a session factory into `WappaEventHandler` as `self.db`.

Key capabilities:

- **Async-first API** with `asyncpg` driver for high-concurrency message handling
- **Connection pooling** with configurable pool size, overflow, timeout, and recycling
- **Write/read replica support** for separating write and read traffic
- **Retry logic** with exponential backoff for transient failures
- **Auto-table creation** from SQLModel definitions at startup
- **Health monitoring** with pool status and connectivity checks

## How to activate

```python
from wappa import Wappa
from wappa.core.plugins import PostgresDatabasePlugin

app = Wappa(cache="memory")
app.add_plugin(
    PostgresDatabasePlugin(
        url="postgresql+asyncpg://user:pass@localhost:5432/mydb"
    )
)
```

With `WappaBuilder`:

```python
from wappa.core.factory import WappaBuilder
from wappa.core.plugins import WappaCorePlugin, PostgresDatabasePlugin

builder = WappaBuilder()
builder.add_plugin(WappaCorePlugin())
builder.add_plugin(
    PostgresDatabasePlugin(
        url="postgresql+asyncpg://user:pass@localhost:5432/mydb",
        models=[User, Order],
    )
)
app = builder.build()
```

## Configuration options

| Parameter | Type | Default | Description |
|---|---|---|---|
| `url` | `str` | (required) | Primary database URL for write operations. Must use `postgresql+asyncpg://` scheme |
| `read_urls` | `list[str] \| None` | `None` | Optional list of replica URLs for read operations |
| `models` | `list[type[SQLModel]] \| None` | `None` | SQLModel classes for auto-table creation |
| `auto_create_tables` | `bool` | `True` | Create tables from `models` at startup |
| `auto_commit` | `bool` | `True` | Auto-commit on successful context manager exit |
| `pool_size` | `int` | `20` | Number of persistent connections in the pool |
| `max_overflow` | `int` | `40` | Maximum additional connections beyond `pool_size` |
| `pool_timeout` | `int` | `30` | Seconds to wait for a connection from the pool |
| `pool_recycle` | `int` | `3600` | Recycle connections after N seconds (prevents stale connections) |
| `pool_pre_ping` | `bool` | `True` | Test connections before use (detects dropped connections) |
| `max_retries` | `int` | `3` | Retry attempts for transient database failures |
| `base_delay` | `float` | `1.0` | Base delay in seconds for exponential backoff |
| `max_delay` | `float` | `30.0` | Maximum delay in seconds between retries |
| `echo` | `bool` | `False` | Log all SQL statements (useful for debugging) |
| `statement_cache_size` | `int \| None` | `None` | Asyncpg prepared statement cache size. Set to `0` for pgBouncer/Supabase. `None` uses asyncpg defaults |

## Usage in event handlers

The plugin injects a session factory as `self.db` on `WappaEventHandler`. Use it as an async context manager:

```python
from sqlalchemy import select
from wappa import WappaEventHandler

class MyEventHandler(WappaEventHandler):
    async def handle_message(self, message):
        async with self.db() as session:
            result = await session.execute(
                select(User).where(User.phone == message.sender_phone)
            )
            user = result.scalars().first()

            if not user:
                user = User(phone=message.sender_phone, name="New User")
                session.add(user)
                # auto-commits on context exit when auto_commit=True

        await self.messenger.send_text(f"Hello {user.name}!", message.sender_phone)
```

When `auto_commit=True` (default), the session commits automatically when the `async with` block exits without errors. If an exception occurs, the session rolls back.

## Read replicas

Pass `read_urls` to separate write and read traffic across database instances:

```python
PostgresDatabasePlugin(
    url="postgresql+asyncpg://primary-host:5432/mydb",
    read_urls=[
        "postgresql+asyncpg://replica1-host:5432/mydb",
        "postgresql+asyncpg://replica2-host:5432/mydb",
    ],
)
```

The session manager routes write operations to the primary URL and distributes read operations across the replicas. During startup, all replicas are logged and health-checked alongside the primary connection.

## pgBouncer / Supabase compatibility

When running behind **pgBouncer in transaction mode** or connecting to **Supabase** (which uses pgBouncer internally), you must disable asyncpg's prepared statement cache:

```python
PostgresDatabasePlugin(
    url="postgresql+asyncpg://user:pass@db.supabase.co:5432/postgres",
    statement_cache_size=0,  # Required for pgBouncer transaction mode
)
```

Without `statement_cache_size=0`, asyncpg attempts to use prepared statements that pgBouncer cannot track across pooled connections, causing `prepared statement does not exist` errors.

## Health monitoring

The plugin performs a health check during startup and exposes health status for runtime monitoring:

```python
# Get health status from the plugin instance
health = await postgres_plugin.get_health_status(app)
# Returns:
# {
#     "healthy": True,
#     "plugin": "PostgresDatabasePlugin",
#     "write_url": "postgresql+asyncpg://user:***@localhost:5432/mydb",
#     "read_replicas": 0,
#     "pool_size": 20,
#     "max_overflow": 40,
#     ...
# }
```

The session manager is also available directly on `app.state.postgres_session_manager` for advanced use cases.

## Important notes

- **Use asyncpg URLs**: Connection strings must use the `postgresql+asyncpg://` scheme, not plain `postgresql://`. The plugin relies on the async `asyncpg` driver.
- **Use `session.execute()`, not `session.exec()`**: The plugin provides SQLAlchemy `AsyncSession`, not SQLModel sessions. Use `await session.execute(select(...))` and access results with `.scalars()`.
- **All database operations must be awaited**: Every call through the async session (`execute`, `add`, `commit`, `rollback`) is a coroutine.
- **Hook priority 25**: The plugin registers startup/shutdown hooks at priority 25 -- after Redis (20) and core Wappa (10), but before user hooks (50). This ensures Redis is available if your models or listeners depend on it.
- **Shutdown is fault-tolerant**: If cleanup fails during shutdown, errors are logged but not re-raised, preventing cascading failures.
- **Password masking**: Database URLs are automatically masked in all log output (`user:***@host`).
