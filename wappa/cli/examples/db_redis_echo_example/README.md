# DB + Redis Echo Example

A comprehensive example demonstrating **PostgresDatabasePlugin** with Redis caching for conversation history management.

**⚡ Async-First Architecture**: This example uses **asyncpg** and async database operations, optimized for high-concurrency conversational applications like WhatsApp. Async operations allow handling multiple simultaneous user conversations without blocking, ensuring responsive message processing even under heavy load.

## Architecture

This example implements a two-tier async storage architecture:

```
┌─────────────────┐
│ Incoming Message│
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Redis Cache    │  ← Active conversation messages (fast access)
│  (user_cache)   │
└────────┬────────┘
         │
         │ /CLOSE command
         ▼
┌─────────────────┐
│ PostgreSQL DB   │  ← Closed conversations (long-term storage)
│   (Supabase)    │
└─────────────────┘
```

### Storage Strategy

- **Redis** (Async): Stores active conversation messages using Wappa's `user_cache` interface
- **PostgreSQL** (Async via asyncpg): Persists closed conversations to Supabase for long-term storage and analytics

This approach provides:
- **Non-blocking operations**: Handle multiple users concurrently without waiting for database I/O
- **Fast message access**: Redis in-memory cache for active conversations
- **Durable storage**: PostgreSQL for historical data and analytics
- **Cost-effective**: Redis TTL clears old data automatically
- **Scalable**: Connection pooling and async operations support high user concurrency

## Features

- **Async PostgreSQL Integration**: Uses asyncpg driver for non-blocking database operations
- **Redis Caching**: Fast message storage for active conversations using user_cache
- **Conversation Management**: Auto-create, cache, and persist conversations
- **Media Message Support**: Full support for images, audio, video, and documents with metadata (MIME type, SHA256, URL, caption, description)
- **Special Message Types**: Contact, location, and interactive messages with structured JSON persistence
- **Echo Bot**: Type-specific echo responses with metadata for all message types
- **Commands**:
  - `/HISTORY` - Show message count in current conversation
  - `/CLOSE` - Close conversation and persist to database

## Why Asyncpg?

This example uses **asyncpg** (via `postgresql+asyncpg://` URLs) instead of synchronous drivers for critical reasons:

**Conversational App Requirements**:
- WhatsApp apps receive messages from multiple users simultaneously
- Database queries must not block other users' messages
- High concurrency is essential for responsive user experience

**Asyncpg Benefits**:
- **Non-blocking I/O**: Database queries don't block event loop
- **High performance**: ~3x faster than psycopg2 for async operations
- **Native async**: Built from ground up for Python's asyncio
- **Connection pooling**: Efficiently reuse connections across requests

**Example Impact**: With 50 concurrent users, a 100ms database query:
- **Sync driver**: Users wait in queue, 5+ seconds total latency
- **Async driver (asyncpg)**: All users get ~100ms response time

## Database Schema

### Tables

#### `chats`
Represents a user on a specific platform (WhatsApp, Instagram, Telegram).

```sql
- chat_id (UUID, primary key)
- platform (enum: whatsapp, instagram, telegram)
- platform_user_id (text) - Phone number or platform ID
- phone_e164, username, first_name, last_name
- is_blocked, last_inbound_at, last_outbound_at
- last_conversation_summary
- profile (jsonb)
- created_at, updated_at
```

#### `conversations`
Represents a session of messages with a user. Only one open conversation per chat.

```sql
- conversation_id (UUID, primary key)
- chat_id (UUID, foreign key → chats)
- status (enum: open, closing, closed)
- started_at, last_inbound_at, last_activity_at, closed_at
- conversation_summary
- created_at
```

#### `messages`
Individual messages in a conversation.

```sql
- message_id (UUID, primary key)
- conversation_id (UUID, foreign key → conversations)
- chat_id (UUID, foreign key → chats)
- actor (enum: user, agent, system, tool)
- kind (enum: text, image, audio, video, document, contact, location, interactive, etc.)
- platform (enum)
- platform_message_id, platform_timestamp
- text_content
- json_content (jsonb) - For contact, location, interactive, reaction messages
- media_* fields (mime, sha256, url, caption, description, transcript)
- delivery_status, error_code, error_message
- created_at
```

**Media Fields**:
- `media_mime`: MIME type (e.g., `image/jpeg`, `audio/ogg`, `video/mp4`)
- `media_sha256`: SHA256 hash of media file for integrity verification
- `media_url`: Direct download URL from WhatsApp webhook
- `media_caption`: User-provided caption text for images/videos
- `media_description`: Additional description (e.g., document filename)
- `media_transcript`: Transcription text for audio/video messages

**JSON Content Field** (special message types):
- `json_content`: JSONB field for structured data from contact, location, interactive, and reaction messages
- **Contact messages**: Full contact data (name, phone, organization, vCard array)
- **Location messages**: Coordinates, location name, address, map URL
- **Interactive messages**: Button/list selection data (selected_id, title, description)
- **Reaction messages**: Emoji and target message ID

See the [Message Persistence Guide](/.claude/documents/message-persistence-guide.md) for detailed examples and querying patterns.

## Prerequisites

1. **PostgreSQL Database with asyncpg** (Supabase recommended)
   - Create database and run the schema from Supabase
   - Get Transaction Pooler connection URL (must use `postgresql+asyncpg://` format)
   - asyncpg is automatically installed with Wappa dependencies

2. **Redis Server**
   ```bash
   # Using Docker
   docker run -d -p 6379:6379 redis:alpine

   # Or install locally
   brew install redis  # macOS
   sudo apt install redis-server  # Ubuntu
   ```

3. **WhatsApp Business API**
   - Get API token from Meta Business Suite
   - Configure webhook URL

## Setup

### 1. Install Dependencies

```bash
cd wappa
uv sync
```

### 2. Configure Environment

Create a `.env` file in your project root (not in this example directory):

```env
# WhatsApp Business API
WP_ACCESS_TOKEN=your_token_here
WP_PHONE_ID=your_phone_id_here
WP_BID=your_business_id_here

# Redis
REDIS_URL=redis://localhost:6379

# Database URL (REQUIRED - must use postgresql+asyncpg:// for async operations)
DATABASE_URL=postgresql+asyncpg://user:pass@host:6543/postgres
```

### 3. Create Database Schema

Run the Supabase schema SQL to create tables and enums. The tables will be auto-created by SQLModel if they don't exist (set `auto_create_tables=True` in main.py).

### 4. Run the Example

```bash
# Development mode with auto-reload
uv run wappa dev wappa/cli/examples/db_redis_echo_example/app/main.py

# Or directly with Python
cd wappa/cli/examples/db_redis_echo_example
uv run python -m app.main

# Or with uvicorn
uvicorn app.main:app --reload
```

### 5. Test with WhatsApp

Send messages to your WhatsApp test number:

```
User: Hello!
Bot: Echo: Hello!
     Message #1 in this conversation
     Send '/HISTORY' to see count
     Send '/CLOSE' to close and persist to DB

User: How are you?
Bot: Echo: How are you?
     Message #2 in this conversation
     Send '/HISTORY' to see count
     Send '/CLOSE' to close and persist to DB

User: /HISTORY
Bot: Current conversation has 4 messages in cache.
     Send '/CLOSE' to persist to database.

User: /CLOSE
Bot: Conversation closed and 5 messages persisted to database!
```

### Media Message Example

```
User: [Sends an image with caption "Check this out!"]
Bot: Echo: [Image Message]
     Message #1 in this conversation
     Send '/HISTORY' to see count
     Send '/CLOSE' to close and persist to DB

[Cached in Redis:]
{
  "message_id": "550e8400-e29b-41d4-a716-446655440000",
  "actor": "user",
  "kind": "image",
  "text_content": null,
  "media_mime": "image/jpeg",
  "media_sha256": "2c26b46b68ffc68ff99b453c1d30413413422d706483bfa0f98a5e886266e7ae",
  "media_url": "whatsapp://media/5712345678901234",
  "media_caption": "Check this out!",
  "platform_message_id": "wamid.HBgNMTIzNDU2Nzg5MDEyMzQVAgARGBIxNjEyMzQ1Njc4OTAxMjM0AA==",
  "platform_timestamp": "2025-01-11T10:30:00Z",
  "created_at": "2025-01-11T10:30:00Z"
}

User: /CLOSE
Bot: Conversation closed and 2 messages persisted to database!

[Persisted to PostgreSQL with full media metadata]
```

## Code Structure

Following **SOLID principles** and clean architecture patterns:

```
db_redis_echo_example/
├── app/
│   ├── handlers/                # Business logic handlers (SRP)
│   │   ├── __init__.py
│   │   ├── command_handlers.py  # /CLOSE, /HISTORY command processing
│   │   └── message_handlers.py  # Message type handling + echo responses
│   ├── models/                  # Data models and schemas (SRP)
│   │   ├── __init__.py
│   │   ├── cache_models.py      # Pydantic cache models (Redis)
│   │   └── database_models.py   # SQLModel database models (PostgreSQL)
│   ├── utils/                   # Utility functions (SRP)
│   │   ├── __init__.py
│   │   ├── cache_utils.py       # CacheHelper class for Redis operations
│   │   ├── database_utils.py    # DatabaseHelper class for DB operations
│   │   └── extraction_utils.py  # Media/JSON/contact data extraction
│   ├── __init__.py
│   ├── main.py                  # Application setup with plugins
│   └── master_event.py          # Thin orchestration layer (~250 lines)
└── README.md                    # This file
```

**Architecture Benefits**:
- **Single Responsibility**: Each module has one clear purpose
- **Testability**: Easy to unit test individual handlers and utilities
- **Maintainability**: Files are 100-300 lines instead of 700+
- **Extensibility**: Add new features without modifying existing code
- **Collaboration**: Multiple developers can work on different handlers

## How It Works

### Message Flow

1. **Incoming Message** arrives via WhatsApp webhook
2. **Get or Create Conversation**: Check user_cache for active conversation
3. **Extract Media Data**: For media messages (images, audio, video, documents), extract metadata:
   - MIME type from `message.media_type`
   - SHA256 hash from platform-specific field (e.g., `message.image.sha256`)
   - Media ID from `message.get_download_info()`
   - Caption from `message.caption`
   - Additional metadata (filename for documents, etc.)
4. **Cache Message**: Store message with all metadata in Redis using user_cache.upsert()
5. **Process**: Echo message back to user with message count
6. **Cache Response**: Store outgoing message in Redis
7. **On /CLOSE**: Persist conversation + all messages (including media metadata) to PostgreSQL, delete from cache

### Redis Storage (via user_cache)

The example uses Wappa's built-in `user_cache` interface:
- `await self.user_cache.get(models=ConversationCache)` - Get conversation
- `await self.user_cache.upsert(data, ttl=86400)` - Store/update conversation
- `await self.user_cache.delete()` - Clear conversation

**TTL**: 24 hours (configurable)

### Database Persistence

When `/CLOSE` command is received:

1. Fetch conversation from user_cache
2. Create `Conversation` record in PostgreSQL
3. Create `Message` records for all cached messages
4. Update `Chat` record with last activity
5. Delete conversation from user_cache
6. Confirm to user

## Key Concepts Demonstrated

### 1. PostgresDatabasePlugin Usage

```python
from wappa.core.plugins import PostgresDatabasePlugin

app.add_plugin(
    PostgresDatabasePlugin(
        url="postgresql+asyncpg://...",
        models=[Chat, Conversation, Message],
        auto_create_tables=False,  # Tables exist in Supabase
        auto_commit=True,
        statement_cache_size=0,  # Required for pgBouncer transaction mode
    )
)
```

**Important**: When using **Supabase** or **pgBouncer** in transaction/statement mode, you **must** set `statement_cache_size=0` to disable asyncpg's prepared statement cache. This prevents the `DuplicatePreparedStatementError` that occurs with connection poolers.

### 2. Async Database Operations in Event Handler

**All database operations are async** to prevent blocking. Use `session.execute()` (not `session.exec()`) with SQLAlchemy's AsyncSession:

```python
async def process_message(self, webhook):
    # Async context manager - non-blocking
    async with self.db() as session:
        # Async query - doesn't block other users
        result = await session.execute(select(Chat).where(...))
        chat = result.scalars().first()

        # Create new record
        new_chat = Chat(platform=Platform.WHATSAPP, ...)
        session.add(new_chat)
        # Auto-commits on context exit (non-blocking)
```

**Why Async Matters for WhatsApp**:
- User A's slow database query doesn't delay User B's message
- Handle 100+ concurrent conversations without blocking
- Better resource utilization and response times

### 3. Redis Cache Integration (user_cache)

```python
# Get conversation
conversation = await self.user_cache.get(models=ConversationCache)

# Store conversation
await self.user_cache.upsert(conversation.model_dump(), ttl=86400)

# Delete conversation
await self.user_cache.delete()
```

### 4. Enum Handling (30x-community pattern)

```python
# Define enum
class Platform(str, Enum):
    WHATSAPP = "whatsapp"

# Use in model
platform: Platform = Field(
    sa_column=get_enum_column(
        Platform,
        column_name="platform_t",  # Supabase enum type name
        nullable=False,
    )
)
```

## Performance Considerations

- **Redis Cache**: Messages stored in memory for instant access
- **Connection Pooling**: PostgreSQL pool (10 connections + 20 overflow)
- **Retry Logic**: Automatic retry on transient database failures
- **Batch Writes**: All messages persisted in single transaction

## Troubleshooting

### Database Connection Issues

```bash
# Test database connection
psql "postgresql://user:pass@host:6543/postgres"

# Check pool status in logs
# Look for "PostgresDatabasePlugin initialized successfully"
```

### Redis Connection Issues

```bash
# Test Redis connection
redis-cli ping

# Check Redis logs
docker logs <redis-container-id>
```

### Tables Not Created

```bash
# Verify auto_create_tables=True in plugin config (in main.py)
# Check application logs for "Database tables created for models"
# Manually run Supabase schema SQL if needed
```

## Next Steps

- **Download Media Files**: Implement WhatsApp Media API integration to download and store media files locally or in cloud storage (S3, GCS)
- **Media Processing**: Add image/audio/video processing (thumbnails, transcription, compression)
- **AI-Powered Summaries**: Add conversation summarization using OpenAI
- **Search & Analytics**: Implement full-text search and conversation analytics
- **Archival & Cleanup**: Implement conversation archival policies and automated cleanup
- **Intelligent Responses**: Add OpenAI integration for context-aware responses

## License

This example is part of the Wappa framework.
