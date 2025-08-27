# mimieapify/symphony_ai/redis/README.md
# Redis Module - Multi-Pool Clean Architecture

This module provides Redis operations with clean separation of concerns, following SOLID principles. The Redis Handler package has been refactored from a monolithic 754-line God class into focused, single-responsibility repositories with **multi-pool support** for different subsystems.

## 🏗️ Multi-Pool Architecture

The Redis module now supports multiple Redis pools targeting different databases for optimal separation of concerns:

| Pool Alias | Database | Purpose |
|------------|----------|---------|
| `"default"` | DB 15 | General operations |
| `"user"` | DB 11 | User-specific data |
| `"handlers"` | DB 10 | TTL-based handlers, batch, state, table operations |
| `"symphony_shared_state"` | DB 9 | Shared state between tools/agents |
| `"expiry"` | DB 8 | Key-expiry listener |
| `"pubsub"` | DB 7 | AsyncSendMessage pub/sub |

### Configuration Options

```python
from mimeiapify.symphony_ai import GlobalSymphonyConfig

# Option 1: Single URL (automatic pool creation)
config = GlobalSymphonyConfig(
    redis_url="redis://localhost:6379"
    # Automatically creates all pools with different database numbers
)

# Option 2: Multi-URL (explicit control)
config = GlobalSymphonyConfig(
    redis_url={
        "default": "redis://localhost:6379/15",
        "user": "redis://cache:6379/11", 
        "handlers": "redis://localhost:6379/10",
        "symphony_shared_state": "redis://localhost:6379/9",
        "expiry": "redis://localhost:6379/8",
        "pubsub": "redis://localhost:6379/7"
    }
)

await GlobalSymphony.create(config)
```

## 🏗️ Module Structure

```
redis/
├── __init__.py                    # Main module exports
├── context.py                     # ContextVar for thread-safe shared state
├── redis_client.py               # Multi-pool Redis connection management  
├── ops.py                         # Low-level atomic Redis operations (with pool alias support)
├── README.md                      # This file
├── listeners/                     # Key-expiry trigger system
│   ├── __init__.py               # Expiry listener exports
│   ├── handler_registry.py       # Action → handler mapping with decorators
│   ├── expiry_listener.py        # Redis keyspace event subscriber
│   ├── example_handlers.py       # Example trigger handlers
│   └── README.md                 # Complete expiry trigger documentation
└── redis_handler/                 # Repository layer
    ├── __init__.py               # Repository exports
    ├── utils/                     # Infrastructure & utilities
    │   ├── __init__.py           # Utils exports
    │   ├── key_factory.py        # Stateless key building rules
    │   ├── serde.py              # JSON/Enum/DateTime/BaseModel serialization
    │   └── tenant_cache.py       # Base class with common Redis patterns + alias support
    ├── user.py                   # User data management → RedisUser (uses "user" pool)
    ├── shared_state.py           # Tool/agent scratch space → RedisSharedState (uses "symphony_shared_state" pool)
    ├── state_handler.py          # Handler state management → RedisStateHandler (uses "handlers" pool)
    ├── table.py                  # Table/DataFrame operations → RedisTable (uses "handlers" pool)
    ├── batch.py                  # Batch processing → RedisBatch (uses "handlers" pool)
    ├── trigger.py                # Expiration triggers → RedisTrigger (uses "expiry" pool)
    └── generic.py                # Generic key-value ops → RedisGeneric (uses "default" pool)
```

## 🚀 Quick Start

### Basic Repository Usage with Pool Targeting

```python
from mimeiapify.symphony_ai.redis.redis_handler import (
    RedisUser, RedisStateHandler, RedisTable, RedisSharedState
)

# Initialize repositories - each targets its designated Redis pool automatically
user = RedisUser(tenant="mimeia", user_id="user123", ttl_default=3600)  # → "user" pool (DB 11)
handler = RedisStateHandler(tenant="mimeia", user_id="user123", ttl_default=1800)  # → "handlers" pool (DB 10)
tables = RedisTable(tenant="mimeia")  # → "handlers" pool (DB 10)
shared_state = RedisSharedState(tenant="mimeia", user_id="user123")  # → "symphony_shared_state" pool (DB 9)

# SQL-style operations - upsert for hash operations, set for simple key-value
await user.upsert({"name": "Alice", "score": 100})  # HSET → updates only specified fields
user_data = await user.get()
await user.update_field("score", 110)  # Single field update

# Handler state management
await handler.upsert("chat_handler", {"step": 1, "data": {...}})  # HSET → field-level updates
state = await handler.get("chat_handler")
await handler.update_field("chat_handler", "step", 2)

# True merge operations (reads existing + merges + saves)
final_state = await handler.merge("chat_handler", {"new_field": "value"})

# Table operations
await tables.upsert("users_table", "pk123", {"name": "Bob", "active": True})  # HSET
row = await tables.get("users_table", "pk123")
await tables.update_field("users_table", "pk123", "active", False)

# Shared state for tools/agents
await shared_state.upsert("conversation", {"step": 1, "context": "greeting"})  # HSET
step = await shared_state.get_field("conversation", "step")
```

### Direct Pool Targeting (Advanced)

```python
from mimeiapify.symphony_ai.redis import ops

# All ops functions now accept an alias parameter for pool targeting
await ops.set("key", "value", alias="pubsub")  # → pubsub pool (DB 7)
await ops.hset("hash_key", field="name", value="Alice", alias="user")  # → user pool (DB 11)
await ops.setex("temp_key", 300, "temp_value", alias="expiry")  # → expiry pool (DB 8)

# Repository methods can override their default pool if needed
user = RedisUser(tenant="mimeia", user_id="user123")
await user.upsert({"name": "Alice"})  # → Uses default "user" pool
await user._hset_with_ttl(user._key(), {"temp": "data"}, 60, alias="expiry")  # → Override to "expiry" pool
```

### Context-Aware Shared State (Thread-Safe)

The `context.py` module provides thread-safe access to shared state using Python's `ContextVar`:

```python
from mimeiapify.symphony_ai.redis.context import _current_ss, RedisSharedState
from mimeiapify.symphony_ai import GlobalSymphony
import asyncio

# In your FastAPI handler or async function
async def handle_user_request(tenant: str, user_id: str, message: str):
    # Create user-specific shared state (automatically uses "symphony_shared_state" pool)
    ss = RedisSharedState(tenant=tenant, user_id=user_id)
    
    # Bind to current context (task-local)
    token = _current_ss.set(ss)
    try:
        # Any code running in this context (including tools in thread pools)
        # will see this specific shared state instance
        await process_user_message(message)
    finally:
        _current_ss.reset(token)  # Always cleanup

# Tools can access the context-bound shared state
from mimeiapify.symphony_ai.redis.context import _current_ss

class SomeAsyncTool:
    async def execute(self):
        # Gets the shared state bound to current request context
        shared_state = _current_ss.get()
        await shared_state.update_field("tool_state", "last_tool", "SomeAsyncTool")

# For synchronous tools (like agency-swarm BaseTool)
class SomeSyncTool:
    def run(self):
        shared_state = _current_ss.get()
        loop = GlobalSymphony.get().loop
        
        # Bridge to async world
        coro = shared_state.update_field("tool_state", "last_tool", "SomeSyncTool")
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(timeout=5)
```

### TTL-Driven Workflows (Expiry Triggers)

The `listeners` module provides a powerful system for turning Redis TTLs into background jobs:

```python
from mimeiapify.symphony_ai.redis.listeners import expiration_registry, run_expiry_listener
from mimeiapify.symphony_ai.redis.redis_handler import RedisTrigger

# 1. Register handlers for expiry events
@expiration_registry.on_expire_action("process_message_batch")
async def handle_batch_processing(identifier: str, full_key: str):
    tenant = full_key.split(":", 1)[0]
    logger.info(f"[{tenant}] Processing batch for: {identifier}")
    # Your batch processing logic here...

@expiration_registry.on_expire_action("send_reminder")
async def handle_reminder(user_id: str, full_key: str):
    # Send delayed notification
    await send_notification(user_id, "Don't forget to complete your task!")

# 2. Start the listener (in FastAPI lifespan or similar)
asyncio.create_task(run_expiry_listener(alias="expiry"))

# 3. Schedule deferred work from your application
triggers = RedisTrigger(tenant="mimeia")

# Schedule batch processing for 5 minutes later
await triggers.set("process_message_batch", "wa_123", ttl_seconds=300)

# Schedule reminder for 1 hour later  
await triggers.set("send_reminder", "user456", ttl_seconds=3600)

# Cancel scheduled work if no longer needed
await triggers.delete("process_message_batch", "wa_123")
```

**See `redis/listeners/README.md` for complete documentation with architecture diagrams.**

## 📋 Repository Responsibilities & Pool Assignments

### RedisUser - User Data Management (`"user"` pool - DB 11)
```python
user = RedisUser(tenant="your_tenant", user_id="user123")

# SQL-style CRUD operations using HSET (field-level updates)
await user.upsert({"name": "Alice", "active": True})  # Updates only specified fields
user_data = await user.get()
await user.update_field("last_login", datetime.now())  # Single field update
await user.delete()

# Atomic operations
await user.increment_field("login_count")
await user.append_to_list("tags", "premium")

# Field-level access
name = await user.get_field("name")
await user.delete_field("temp_data")

# Search (pattern matching across users)
found_user = await user.find_by_field("email", "alice@example.com")

# Check existence
exists = await user.exists()
```

### RedisStateHandler - Conversational State (`"handlers"` pool - DB 10)
```python
handler = RedisStateHandler(tenant="your_tenant", user_id="user123")

# State management using HSET (field-level updates)
await handler.upsert("chat_handler", {"step": 1, "data": {...}})  # Updates only specified fields
state = await handler.get("chat_handler")
await handler.update_field("chat_handler", "step", 2)
current_step = await handler.get_field("chat_handler", "step")

# True merge operations (preserves existing state)
final_state = await handler.merge("chat_handler", {"new_data": "value"})  # Reads + merges + saves
```

### RedisTable - Generic Data Tables (`"handlers"` pool - DB 10)
```python
tables = RedisTable(tenant="your_tenant")

# Table row operations using HSET (field-level updates)
await tables.upsert("products", "prod_123", {"name": "Widget", "price": 29.99})
product = await tables.get("products", "prod_123")
await tables.update_field("products", "prod_123", "price", 19.99)
price = await tables.get_field("products", "prod_123", "price")

# Cross-table cleanup
await tables.delete_all_by_pkid("user_123")  # Deletes from all tables
```

### RedisSharedState - Tool/Agent Scratch Space (`"symphony_shared_state"` pool - DB 9)
```python
shared_state = RedisSharedState(tenant="your_tenant", user_id="user123")

# Store conversation state for tools/agents using HSET
await shared_state.upsert("conversation", {
    "step": 1, 
    "context": "user_greeting",
    "collected_data": {"name": "Alice"}
})

# Update specific fields
await shared_state.update_field("conversation", "step", 2)
await shared_state.update_field("conversation", "last_tool", "email_validator")

# Retrieve state data
current_step = await shared_state.get_field("conversation", "step")
full_state = await shared_state.get("conversation")

# Manage multiple states per user
await shared_state.upsert("form_progress", {"page": 1, "completed_fields": []})
await shared_state.upsert("tool_cache", {"last_api_call": datetime.now()})

# Cleanup operations
states = await shared_state.list_states()  # ["conversation", "form_progress", "tool_cache"]
await shared_state.delete("form_progress")
await shared_state.clear_all_states()  # Delete all states for this user
```

### RedisTrigger - Expiration-based Actions (`"expiry"` pool - DB 8)
```python
triggers = RedisTrigger(tenant="your_tenant")

# Set expiration triggers using SETEX (simple key-value with TTL)
await triggers.set("send_reminder", "user_123", ttl_seconds=3600)  # 1 hour
await triggers.set("cleanup_temp", "session_456", ttl_seconds=300)   # 5 minutes

# Cleanup
await triggers.delete("send_reminder", "user_123")
await triggers.delete_all_by_identifier("user_123")
```

### RedisBatch - Queue Management (`"handlers"` pool - DB 10)
```python
batch = RedisBatch(tenant="your_tenant")

# Enqueue for processing (uses RPUSH + SADD)
await batch.enqueue("email_service", "daily_reports", "send", {
    "user_id": "123", "template": "daily_summary"
})

# Process batches
items = await batch.get_chunk("email_service", "daily_reports", "send", 0, 99)
await batch.trim("email_service", "daily_reports", "send", 100, -1)

# Global coordination (class methods - no tenant)
pending_tenants = await RedisBatch.get_pending_tenants("email_service")
await RedisBatch.remove_from_pending("email_service", "mimeia")
```

### RedisGeneric - Simple Key-Value Operations (`"default"` pool - DB 15)
```python
generic = RedisGeneric(tenant="your_tenant")

# Simple key-value operations using SET (complete value replacement)
await generic.set("config_key", {"theme": "dark", "lang": "en"})  # Replaces entire value
config = await generic.get("config_key")
await generic.delete("config_key")

# Note: No field operations since this uses simple SET, not HSET
```

## 🎯 SQL-Style Method Naming Convention

The system now uses **SQL-style naming** that reflects the underlying Redis operation:

### Hash Operations (HSET) - Field-Level Updates
- `upsert(data_dict)` - Create or update multiple fields (Redis HSET behavior)
- `update_field(field, value)` - Update single field
- `get()` / `get_field(field)` - Retrieve operations
- `delete()` / `delete_field(field)` - Delete operations

### Simple Key-Value Operations (SET) - Complete Replacement
- `set(value)` - Replace entire value (Redis SET behavior)
- `get()` - Retrieve value
- `delete()` - Delete key

### Special Operations
- `merge(data_dict)` - True merge (read existing + merge + save) - StateHandler only
- `increment_field(field, amount)` - Atomic increment (HINCRBY)
- `append_to_list(field, value)` - Append to list field
- `exists()` - Check existence

## 🔧 Pydantic BaseModel Support

The system provides full support for Pydantic models with optimized boolean storage (`"1"`/`"0"` instead of `true`/`false`).

### Define Your Models

```python
from pydantic import BaseModel
from typing import List

class UserProfile(BaseModel):
    name: str
    active: bool
    score: int
    preferences: List[bool]

class UserSettings(BaseModel):
    notifications: bool
    theme: str = "dark"
    auto_save: bool = True
```

### Typed Operations

```python
# Store BaseModel directly
profile = UserProfile(name="Alice", active=True, score=100, preferences=[True, False])
await user.update_field("profile", profile)

# Retrieve with automatic typing
models = {
    "profile": UserProfile,
    "settings": UserSettings
}
user_data = await user.get(models=models)
# user_data["profile"] is now a UserProfile instance
# user_data["profile"].active is bool, not string

# Search with typed results
found_user = await user.find_by_field("active", True, models=models)

# Handler state with context models
handler_models = {"context": ConversationContext}
state = await handler.get("chat_handler", models=handler_models)
```

## 🏗️ Architecture Improvements

### Multi-Pool Benefits
- **🔒 Data Isolation**: Different subsystems use separate Redis databases
- **📈 Performance**: Targeted pool usage reduces connection contention
- **🛡️ Fault Tolerance**: Issues in one pool don't affect others
- **🔧 Maintenance**: Database-specific operations (FLUSHDB, monitoring)
- **📊 Monitoring**: Per-pool metrics and alerting

### TenantCache Enhancement
All repository classes inherit from `TenantCache` which now supports:
- **Default pool assignment**: Each repository targets its designated pool
- **Pool override capability**: Methods accept optional `alias` parameter
- **Inherited method priority**: Uses `_hset_with_ttl()`, `_get_hash()`, etc. before direct ops
- **Consistent error handling**: Unified logging and fallback behavior

### Operations Layer (ops.py)
All Redis operations now support pool targeting:
```python
# Every ops function accepts alias parameter
await ops.set("key", "value", alias="pubsub")
await ops.hget("hash", "field", alias="user") 
await ops.scan_keys("pattern*", alias="handlers")
```

## 🏭 Production Implementation with GlobalSymphony

### 1. FastAPI Integration with Multi-Pool Context

```python
from mimeiapify.symphony_ai.redis.context import _current_ss, RedisSharedState
from mimeiapify.symphony_ai import GlobalSymphony
from mimeiapify.symphony_ai.redis.redis_handler import RedisUser, RedisStateHandler
from fastapi import FastAPI, Request, Depends
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize GlobalSymphony with multi-pool Redis
    from mimeiapify.symphony_ai import GlobalSymphonyConfig
    
    config = GlobalSymphonyConfig(
        # Option 1: Single URL with auto-pool creation
        redis_url="redis://localhost:6379",
        
        # Option 2: Explicit pool configuration
        # redis_url={
        #     "default": "redis://localhost:6379/15",
        #     "user": "redis://cache-users:6379/11", 
        #     "handlers": "redis://cache-handlers:6379/10",
        #     "symphony_shared_state": "redis://cache-shared:6379/9",
        #     "expiry": "redis://cache-expiry:6379/8",
        #     "pubsub": "redis://cache-pubsub:6379/7"
        # },
        
        workers_user=os.cpu_count() * 4,
        workers_tool=32,
        workers_agent=16,
        max_concurrent=128
    )
    
    await GlobalSymphony.create(config)
    yield

app = FastAPI(lifespan=lifespan)

# Middleware for context binding
@app.middleware("http")
async def bind_shared_state_context(request: Request, call_next):
    tenant_id = extract_tenant_from_request(request)
    user_id = extract_user_from_request(request)
    
    if tenant_id and user_id:
        # Create and bind shared state to request context
        # Automatically uses "symphony_shared_state" pool
        ss = RedisSharedState(tenant=tenant_id, user_id=user_id)
        token = _current_ss.set(ss)
        
        try:
            response = await call_next(request)
            return response
        finally:
            _current_ss.reset(token)
    else:
        return await call_next(request)

# FastAPI endpoints can now use context-aware tools
@app.post("/chat")
async def handle_chat(message: str, request: Request):
    # Any tools or agents called from here will automatically
    # have access to the correct shared state via _current_ss.get()
    
    # Direct access to shared state (symphony_shared_state pool)
    ss = _current_ss.get()
    await ss.update_field("conversation", "last_message", message)
    
    # Tools in thread pools will also see the same shared state
    result = await process_with_tools(message)
    return {"response": result}
```

### 2. Agency-Swarm Tool Integration with Context

```python
from agency_swarm.tools import BaseTool
from mimeiapify.symphony_ai.redis.context import _current_ss
from mimeiapify.symphony_ai import GlobalSymphony
import asyncio

class AsyncBaseTool(BaseTool):
    """Enhanced BaseTool with context-aware Redis support"""
    
    @property
    def shared_state(self) -> RedisSharedState:
        """Get context-bound shared state - safe across threads"""
        return _current_ss.get()
    
    def run_async(self, coro) -> Any:
        """Execute async operation from sync tool context"""
        loop = GlobalSymphony.get().loop
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(timeout=30)
    
    # Convenient sync wrappers for common operations
    def get_state(self, state_name: str) -> dict:
        return self.run_async(self.shared_state.get(state_name)) or {}
    
    def upsert_state(self, state_name: str, data: dict) -> bool:
        return self.run_async(self.shared_state.upsert(state_name, data))
    
    def get_state_field(self, state_name: str, field: str):
        return self.run_async(self.shared_state.get_field(state_name, field))
    
    def update_state_field(self, state_name: str, field: str, value) -> bool:
        return self.run_async(self.shared_state.update_field(state_name, field, value))

# Example tool using context-aware shared state
class EmailValidatorTool(AsyncBaseTool):
    email: str = Field(..., description="Email to validate")
    
    def run(self) -> str:
        # No need to manually inject shared state - it's context-aware!
        self.update_state_field("tool_history", "last_tool", "email_validator")
        
        # Validate email logic here
        is_valid = "@" in self.email
        
        # Store result in shared state
        self.update_state_field("validation_results", self.email, is_valid)
        
        return f"Email {self.email} is {'valid' if is_valid else 'invalid'}"
```

## 🔧 Migration from Old Architecture

### Key Changes
- **✅ Multi-pool architecture**: Separate Redis databases for different concerns
- **✅ SQL-style naming**: `upsert()` for hash operations, `set()` for simple key-value
- **✅ Pool alias support**: All operations can target specific pools
- **✅ Inherited method priority**: TenantCache methods used before direct ops
- **✅ Consistent field operations**: All hash repositories support `get_field()` / `update_field()`
- **✅ Removed task queue complexity**: No more `GlobalAgentState.task_queue` or `pending_tasks`
- **✅ Added context-aware shared state**: Thread-safe access via `ContextVar`
- **✅ Organized utils**: Infrastructure moved to `redis_handler/utils/`
- **✅ Simplified imports**: Clean package structure with proper `__init__.py` files

### Before (Single Pool + Complex Queue)
```python
# Old approach - single pool, complex queue plumbing
task_id = str(uuid.uuid4())
GlobalAgentState.pending_tasks[task_id] = asyncio.Future()
await GlobalAgentState.task_queue.put((task_id, some_coroutine()))
result = await GlobalAgentState.pending_tasks[task_id]

# Manual shared state injection per tool
BaseTool._shared_state = redis_shared_state  # Race condition!

# Inconsistent naming
await user.set({"name": "Alice"})  # Was this HSET or SET?
await user.update_field("score", 100)  # Mixed naming conventions
```

### After (Multi-Pool + Direct Integration)  
```python
# New approach - multi-pool, direct and context-aware
loop = GlobalSymphony.get().loop
future = asyncio.run_coroutine_threadsafe(some_coroutine(), loop)
result = future.result(timeout=5)

# Context-aware shared state (thread-safe, automatic pool targeting)
token = _current_ss.set(RedisSharedState(tenant="mimeia", user_id="user123"))
try:
    # All tools automatically get the right shared state
    result = await call_tools()
finally:
    _current_ss.reset(token)

# Clear SQL-style naming
await user.upsert({"name": "Alice"})  # HSET - field-level updates
await generic.set("config", {"theme": "dark"})  # SET - complete replacement
await user.update_field("score", 100)  # Consistent field operations
```

## 🔍 Key Features

- **✅ Multi-Pool Architecture**: Separate Redis databases for different subsystems
- **✅ SQL-Style Naming**: Clear distinction between HSET (`upsert`) and SET (`set`) operations
- **✅ Pool Alias Support**: All operations can target specific Redis pools
- **✅ Single Responsibility**: Each repository handles one domain with designated pool
- **✅ Type Safety**: Full Pydantic BaseModel support with boolean optimization
- **✅ Tenant Isolation**: Automatic key prefixing and scoping
- **✅ TTL Management**: Flexible per-operation and per-repository TTL control
- **✅ Atomic Operations**: Built on Redis atomic operations
- **✅ Context-Aware**: Thread-safe shared state via `ContextVar`
- **✅ GlobalSymphony Integration**: Seamless event loop and thread pool management
- **✅ Clean Architecture**: Utils separated from business logic, inherited methods prioritized
- **✅ No Task Queue Overhead**: Direct async/sync bridging

## 📚 Best Practices

1. **Use designated pools** - Let repositories automatically target their assigned pools
2. **Override pools sparingly** - Only use `alias` parameter when cross-pool operations are needed
3. **Follow SQL naming** - `upsert()` for hash operations, `set()` for simple key-value
4. **Use context-aware shared state** instead of manual injection
5. **Leverage `_current_ss.get()`** in tools for automatic context binding
6. **Use specific repositories** over `RedisGeneric` when possible
7. **Define BaseModel mappings** once and reuse across operations
8. **Set appropriate TTLs** per data type (users: long, handlers: short, triggers: very short)
9. **Bind shared state at request level** using middleware
10. **Always reset context tokens** in `finally` blocks
11. **Use `GlobalSymphony.get().loop`** for async/sync bridging
12. **Import from utils** for infrastructure components
13. **Cache repository instances** per tenant to avoid repeated initialization
14. **Prefer inherited methods** over direct ops calls within repositories

## 🎯 Import Patterns

```python
# Main Redis functionality
from mimeiapify.symphony_ai.redis import RedisClient, ops, context, listeners

# Repository layer (each targets its designated pool)
from mimeiapify.symphony_ai.redis.redis_handler import (
    RedisUser,           # → "user" pool (DB 11)
    RedisSharedState,    # → "symphony_shared_state" pool (DB 9)
    RedisStateHandler,   # → "handlers" pool (DB 10)
    RedisTable,          # → "handlers" pool (DB 10)
    RedisBatch,          # → "handlers" pool (DB 10)
    RedisTrigger,        # → "expiry" pool (DB 8)
    RedisGeneric         # → "default" pool (DB 15)
)

# TTL-driven workflows
from mimeiapify.symphony_ai.redis.listeners import (
    expiration_registry,     # @on_expire_action decorator
    run_expiry_listener      # Background task for keyspace events
)

# Infrastructure utilities
from mimeiapify.symphony_ai.redis.redis_handler.utils import (
    KeyFactory, dumps, loads, TenantCache
)

# Context-aware shared state
from mimeiapify.symphony_ai.redis.context import _current_ss, RedisSharedState

# GlobalSymphony integration
from mimeiapify.symphony_ai import GlobalSymphony, GlobalSymphonyConfig

# Utilities and logging
from mimeiapify.utils import logger, setup_logging
```

## 🔧 Pool Targeting Examples

```python
# Repository automatic pool targeting
user = RedisUser(tenant="mimeia", user_id="user123")  # → Uses "user" pool automatically
await user.upsert({"name": "Alice"})

# Direct ops with pool targeting
await ops.set("temp_key", "value", alias="expiry")  # → "expiry" pool
await ops.hget("user_hash", "name", alias="user")   # → "user" pool

# Repository pool override (advanced usage)
shared_state = RedisSharedState(tenant="mimeia", user_id="user123")
await shared_state.upsert("temp_state", {"data": "temp"})  # → Uses default "symphony_shared_state" pool
await shared_state._hset_with_ttl(
    shared_state._key("temp_state"), 
    {"urgent": "data"}, 
    ttl=60, 
    alias="expiry"  # → Override to "expiry" pool for urgent data
)
``` 