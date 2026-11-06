# Postgres with PostgresDatabasePlugin

## Contents

- Turn it on
- Sessions in handlers
- Models and tables
- Read replicas and pools
- Failure behavior
- What goes where

## Turn it on

```python
import os
from wappa import Wappa
from wappa.core.plugins import PostgresDatabasePlugin

app = Wappa(cache="redis")
app.add_plugin(PostgresDatabasePlugin(
    url=os.environ["DATABASE_URL"],          # Wappa reads no DATABASE_URL itself
    models=[Submission, Conversation],       # SQLModel classes
    auto_create_tables=False,                # use migrations in production
))
```

`postgresql://`, `postgres://` and `postgresql+asyncpg://` URLs are all accepted (asyncpg underneath). The plugin checks the connection at startup.

## Sessions in handlers

```python
async def process_message(self, webhook):
    async with self.db() as session:           # write session; commits on a clean exit
        session.add(Submission(inbox_id=self.inbox_ref.cache_namespace, user_id=webhook.user.user_id, answers=answers))
    async with self.db_read() as session:      # read session (a replica when configured)
        rows = (await session.execute(select(Submission).where(...))).scalars().all()
```

`self.db` and `self.db_read` are session factories, so call them. They are `None` without the plugin; `self.require_database()` raises a clear error instead. Use `session.execute(...)` (SQLAlchemy `AsyncSession`), not `.exec()`. The database is available in every lane, including `process_api_message`, system crons and external events with no Inbox. Key every row by Inbox (`inbox_ref.platform` plus `inbox_ref.inbox_id`, or `cache_namespace`) and User, because a User ID is unique only within one Inbox.

## Models and tables

`auto_create_tables=True` (the default) runs `SQLModel.metadata.create_all` when `models` is given, which creates **every** imported SQLModel table, not only the listed ones. Use it for development; in production, pass `auto_create_tables=False` and own migrations (Alembic or your tool). Wappa defines no tables of its own in your database.

## Read replicas and pools

`read_urls=[...]` adds replicas, used round-robin by `self.db_read()` and falling back to the primary. Tuning: `pool_size=20`, `max_overflow=40`, `pool_timeout=30`, `pool_recycle=3600`, `pool_pre_ping=True`, `command_timeout=30.0`, `connect_timeout=10.0`. Behind pgBouncer or Supabase's pooler, set `statement_cache_size=0`. With several workers, each process opens its own pool, so size the server's connection limit for workers × (`pool_size` + `max_overflow`).

## Failure behavior

With `auto_commit=True` (the default) a clean exit commits and any exception rolls back. Connecting retries (`max_retries`, `base_delay`, `max_delay`, `connect_max_retries`); a statement inside an open session is not retried. `from wappa.database import TransientDatabaseError` marks errors worth retrying at your level. Never hold a session across a Platform send: write, leave the block, then send.

## What goes where

The database holds what must survive: submissions, orders, conversation history, User records with their per-Platform identities, and `MessageResult.message_id` (plus `wappa_parts` IDs) for matching status webhooks. Caches hold what is cheap to lose (see the table in SKILL.md). Wappa's Inbox Directory (credentials) is not your schema: in explicit mode, your `IInboxDirectorySource` maps your own Inbox tables to Wappa records (`wappa-host-integration`). The worked example is `wappa examples` → `db_redis_echo_example` (Redis for the live conversation, Postgres on close).
