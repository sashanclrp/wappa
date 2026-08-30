# Redis Cache Example

A command-driven bot that keeps user profiles, message history, and conversation state in Redis. It is the reference for how to structure a Wappa app once it outgrows a single handler file: the event handler orchestrates, and "score" modules own the individual features.

## What it demonstrates

- Redis-backed caching through `Wappa(cache="redis")` — user cache, state cache, and table cache side by side
- Splitting a handler into focused score modules instead of one growing `process_message`
- Conversation state with a TTL, so an abandoned flow expires on its own
- Startup configuration validation that fails loudly instead of half-running

## Setup

```bash
uv sync
docker run -d -p 6379:6379 redis:7-alpine   # or point REDIS_URL at your own
```

Create a `.env` file in the project root:

```env
# Meta application — required whenever the WhatsApp callback is mounted (no dev bypass)
META_APP_SECRET=your_meta_app_secret_here
WP_WEBHOOK_VERIFY_TOKEN=your_verify_token_here

# Legacy single-Inbox credential bundle
WP_ACCESS_TOKEN=your_access_token_here
WP_PHONE_ID=your_phone_number_id_here
WP_BID=your_business_id_here

# Cache
REDIS_URL=redis://localhost:6379
```

## Run

```bash
uv run wappa dev app/main.py
```

Point the Meta callback at `https://<your-host>/webhook/inboxes/whatsapp` — one URL serves both the `GET` verification challenge and the `POST` deliveries.

## Files

| Path | Role |
|---|---|
| `app/main.py` | Configuration validation, `Wappa` assembly, handler registration |
| `app/master_event.py` | `RedisCacheExampleHandler` — routes commands to score modules |
| `app/scores/` | One module per feature (users, history, state, stats) |
| `app/models/` | Pydantic models for the cached records |
| `app/utils/` | Shared cache helpers |

## Cache scoping

Every cache key is scoped by Inbox, so two Inboxes running in one process never read each other's users, state, or history. Table Cache is the one family that takes a general `context_id` instead — use it when you deliberately want a scope that is not an Inbox. See [`wappa/persistence/ARCHITECTURE.md`](../../../persistence/ARCHITECTURE.md) for the full model.
