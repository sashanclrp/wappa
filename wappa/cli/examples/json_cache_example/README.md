# Wappa JSON Cache Example

This example demonstrates how to use Wappa's JSON cache backend with a complete WhatsApp bot implementation following SOLID architecture principles.

## Overview

The JSON Cache Example shows how to build a WhatsApp bot that uses JSON file-based caching for:
- **User Cache**: User profiles and session data (JSON files)
- **Table Cache**: Message history and structured data (JSON files) 
- **State Cache**: Application state management (JSON files)

## Architecture

This example follows **SOLID principles** with a modular score-based architecture:

```
app/
├── main.py                 # FastAPI application with JSON cache
├── master_event.py         # Main event handler using SOLID architecture
├── models/                 # Pydantic data models
│   └── json_demo_models.py # User, MessageLog, StateHandler, CacheStats
├── scores/                 # Business logic modules (Single Responsibility)
│   ├── score_base.py       # Abstract base for all scores
│   ├── score_user_management.py      # User profile management
│   ├── score_message_history.py      # Message logging & /HISTORY
│   ├── score_state_commands.py       # /WAPPA, /EXIT commands
│   └── score_cache_statistics.py     # /STATS command & monitoring
└── utils/                  # Utility functions
    ├── cache_utils.py      # Cache key generation & TTL management
    └── message_utils.py    # Message parsing & formatting
```

## Features

### Cache Operations
- **JSON File Storage**: All data stored in JSON files on disk
- **TTL Support**: Automatic expiration of cached data
- **Persistence**: Data survives application restarts
- **Performance**: Fast file-based operations with JSON serialization

### Available Commands
- `/WAPPA` - Enter special state mode (cached in state layer)
- `/EXIT` - Exit special state mode  
- `/HISTORY` - View your message history (from table cache)
- `/STATS` - View JSON cache statistics and health

### Score Modules (SOLID Architecture)
Each score handles a single responsibility:

1. **UserManagementScore**: User profiles, welcome messages
2. **MessageHistoryScore**: Message logging, history retrieval  
3. **StateCommandsScore**: State management, special commands
4. **CacheStatisticsScore**: Cache monitoring, performance metrics

## Configuration

### Environment Variables
```bash
# WhatsApp Business API (required)
WHATSAPP_API_URL=https://graph.facebook.com/v18.0
WHATSAPP_ACCESS_TOKEN=your_access_token
WHATSAPP_PHONE_NUMBER_ID=your_phone_number_id
WHATSAPP_WEBHOOK_VERIFY_TOKEN=your_webhook_verify_token
WHATSAPP_WEBHOOK_SECRET=your_webhook_secret

# Application Settings
PORT=8000
LOG_LEVEL=INFO
ENVIRONMENT=development
```

**Note**: No Redis configuration needed - JSON cache uses the file system!

## Running the Example

1. **Install Dependencies**:
```bash
cd json_cache_example
uv sync
```

2. **Set Environment Variables**:
```bash
# Copy and edit .env file with your WhatsApp credentials
cp .env.example .env
```

3. **Run the Application**:
```bash
uv run python -m app.main
```

4. **Test via WhatsApp**:
   - Send any message to get welcomed
   - Try `/WAPPA` to enter special state
   - Send `/HISTORY` to view message history  
   - Send `/STATS` to see JSON cache statistics
   - Send `/EXIT` to leave special state

## JSON Cache Behavior

### File Structure
```
cache_data/
├── user_cache/
│   └── user_profile_{phone_number}.json
├── table_cache/  
│   └── msg_history_{phone_number}.json
└── state_cache/
    └── wappa_state_{phone_number}.json
```

### Cache Operations
- **Set**: Creates/updates JSON files with serialized Pydantic models
- **Get**: Reads and deserializes JSON files back to Pydantic models
- **Delete**: Removes JSON files from disk
- **TTL**: Files older than TTL are automatically cleaned up

### Performance Characteristics
- **Speed**: Fast for small to medium datasets
- **Persistence**: Data survives restarts and crashes
- **Scalability**: Good for moderate traffic (hundreds of users)
- **Reliability**: No external dependencies, always available

## Development

### Adding New Score Modules
1. Create new score in `app/scores/`
2. Inherit from `ScoreBase` 
3. Implement `can_handle()` and `process()` methods
4. Register in `master_event.py`

### Cache Usage Patterns
```python
# User cache example
user = User(phone_number="1234567890", user_name="John")
await self.user_cache.set("user_profile:1234567890", user, ttl=3600)
cached_user = await self.user_cache.get("user_profile:1234567890", models=User)

# Table cache example  
message_log = MessageLog(user_id="1234567890")
await self.table_cache.set("msg_history:1234567890", message_log)

# State cache example
state = StateHandler()
state.activate_wappa()
await self.state_cache.set("wappa_state:1234567890", state, ttl=1800)
```

## Monitoring

### Cache Statistics
Use `/STATS` command to monitor:
- File system connectivity
- Total operations count
- Cache hit/miss ratios
- Error rates and health status

### Logging
Comprehensive logging with structured output:
- User operations (cache hits/misses)
- Message processing (success/failure)  
- Command handling (state changes)
- Cache statistics (performance metrics)

## Comparison with Redis

| Feature | JSON Cache | Redis Cache |
|---------|------------|-------------|
| **Setup** | No dependencies | Requires Redis server |
| **Persistence** | Always persistent | Configurable |  
| **Performance** | Good (file I/O) | Excellent (memory) |
| **Scalability** | Moderate | High |
| **Reliability** | High (no external deps) | High (with proper setup) |
| **Development** | Simple | Requires Redis knowledge |

## Use Cases

**JSON Cache is ideal for**:
- Development and testing environments
- Small to medium WhatsApp bots (< 1000 active users)
- Applications requiring guaranteed persistence
- Deployments without external dependencies
- Scenarios where setup simplicity is important

**Consider Redis for**:
- High-traffic applications (> 1000 concurrent users)
- Applications requiring sub-millisecond cache responses
- Distributed deployments
- Advanced Redis features (pub/sub, streams, etc.)
