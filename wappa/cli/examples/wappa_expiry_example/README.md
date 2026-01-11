# Wappa Expiry Example

**Inactivity Detection with Message Accumulation using ExpiryActions**

This example demonstrates the ExpiryActions system by implementing an inactivity detector that accumulates messages and echoes them back after 15 seconds of silence.

## 🎯 What This Example Shows

- **ExpiryActions Pattern**: Using Redis KEYSPACE notifications for time-based automation (from wpDemoHotels)
- **Timer Reset Logic**: Creating/deleting expiry triggers to reset inactivity timers
- **Message Accumulation**: Storing multiple messages in UserCache during a conversation
- **Batch Processing**: Processing accumulated data when expiry fires
- **Clean Architecture**: Separation between event handling and expiry handling

## 🔄 How It Works

### User Flow

1. **User sends first message**
   - Message stored in UserCache with timestamp
   - 15-second expiry trigger created
   - User receives confirmation

2. **User sends more messages (within 15 seconds)**
   - Each message stored in UserCache
   - Expiry trigger **deleted and recreated** (timer resets to 15s)
   - User sees running count

3. **User stops sending messages**
   - After 15 seconds of inactivity, expiry trigger fires
   - Expiry handler reads all accumulated messages
   - All messages echoed back with timestamps
   - UserCache cleaned up automatically

4. **User can start a new session**
   - Sending a new message starts the cycle again

### Technical Flow

```
┌─────────────┐
│   Message   │
│   Arrives   │
└──────┬──────┘
       │
       v
┌──────────────────────────────┐
│  MasterEventHandler          │
│  - Store message in UserCache│
│  - Delete old expiry trigger │
│  - Create new 15s trigger    │
│  - Send feedback to user     │
└──────┬───────────────────────┘
       │
       │ (After 15s inactivity)
       v
┌──────────────────────────────┐
│  Redis KEYSPACE Notification │
│  __keyevent@3__:expired      │
└──────┬───────────────────────┘
       │
       v
┌──────────────────────────────┐
│  ExpiryListener (background) │
│  - Detects expired key       │
│  - Parses user_id            │
│  - Dispatches handler        │
└──────┬───────────────────────┘
       │
       v
┌──────────────────────────────┐
│  handle_user_inactivity()    │
│  - Read messages from cache  │
│  - Format with timestamps    │
│  - Echo back to user         │
│  - Clean up cache            │
└──────────────────────────────┘
```

## 📁 Project Structure

```
wappa_expiry_example/
├── README.md                 # This file
└── app/
    ├── __init__.py
    ├── main.py              # Wappa app with ExpiryPlugin
    ├── master_event.py      # Message accumulation logic
    └── expiry_handlers.py   # Expiry action handler (@expiry_registry)
```

## 🚀 Running the Example

### Prerequisites

1. **Redis running** with keyspace notifications enabled:
   ```bash
   redis-server --notify-keyspace-events Ex
   ```
   Or the application will auto-configure it at startup.

2. **Environment variables** in `.env`:
   ```env
   WHATSAPP_TOKEN=your_whatsapp_token
   WHATSAPP_PHONE_ID=your_phone_id
   WHATSAPP_BUSINESS_ID=your_business_id
   REDIS_URL=redis://localhost:6379
   ```

### Start Development Server

```bash
# From project root
uv run wappa dev wappa/cli/examples/wappa_expiry_example/app/main.py

# Or if installed globally
wappa dev wappa/cli/examples/wappa_expiry_example/app/main.py
```

### Test the Flow

1. **Send a message via WhatsApp**
   - You'll see: "Message #1 stored! Timer reset to 15 seconds"

2. **Send more messages quickly (within 15 seconds)**
   - Each message resets the timer
   - You'll see: "Message #2 stored! Timer reset..."

3. **Wait 15 seconds without sending anything**
   - After 15s, you'll receive all your messages echoed back with timestamps
   - Example:
     ```
     📬 Message History (3 messages)

     ⏰ You were inactive for 15 seconds. Here's what you sent:

     1. [10:30:45] Hello there!
     2. [10:30:47] How are you?
     3. [10:30:50] See you later!

     ✨ Session Complete!
     📊 Total: 3 messages
     ⏱️ Timer: 15 seconds
     ```

4. **Start a new session**
   - Send another message to begin accumulating again

## 🔧 Configuration

### Adjust Inactivity Timer

Change the TTL in `master_event.py`:

```python
# Create new expiry trigger (change 15 to your desired seconds)
success = await expiry_cache.set(
    action="user_inactivity",
    identifier=user_id,
    ttl_seconds=15,  # ← Change this value
)
```

### Customize Message Format

Modify the echo format in `expiry_handlers.py`:

```python
# Customize the echo message template
echo_text = f"📬 *Your Messages* ({message_count} total)\n\n"
for idx, msg in enumerate(messages, 1):
    echo_text += f"{idx}. {msg['text']}\n"
```

## 💡 Key Concepts Demonstrated

### 1. Expiry Handler Registration

```python
from wappa import expiry_registry

@expiry_registry.on_expire_action("user_inactivity")
async def handle_user_inactivity(identifier: str, full_key: str) -> None:
    # This fires when the trigger expires
    pass
```

### 2. Timer Reset Pattern

```python
# Delete old trigger (if exists)
await expiry_cache.delete("user_inactivity", user_id)

# Create new trigger (resets timer)
await expiry_cache.set("user_inactivity", user_id, ttl_seconds=15)
```

### 3. Message Accumulation

```python
# Store in UserCache
user_cache = cache_factory.create_user_cache()
user_data = await user_cache.get() or {}
messages = user_data.get("messages", [])
messages.append(new_message)
await user_cache.upsert({"messages": messages})
```

### 4. Batch Processing on Expiry

```python
# Read accumulated data when expiry fires
user_data = await user_cache.get()
messages = user_data.get("messages", [])

# Process all messages
for msg in messages:
    # Format and echo back
    pass

# Clean up
await user_cache.delete()
```

## 🎓 Learning Points

1. **Event-Driven Architecture**: No polling needed - Redis notifies when keys expire
2. **Timer Management**: Deleting and recreating triggers resets the countdown
3. **Stateful Conversations**: UserCache maintains context across messages
4. **Clean Separation**: Event handling (message arrival) separate from expiry handling (timeout)
5. **Fire-and-Forget**: Expiry handlers run asynchronously without blocking

## 🔍 Monitoring and Debugging

### Check Expiry Triggers

```bash
# Connect to Redis
redis-cli -n 3

# List all expiry triggers
KEYS wappa:EXPTRIGGER:*

# Check TTL for a specific user
TTL wappa:EXPTRIGGER:user_inactivity:+1234567890
```

### View User Cache

```bash
# Connect to Redis
redis-cli -n 0

# Get user data
GET wappa:user:+1234567890
```

### Application Logs

Look for these log messages:

- `📬 Message from {user_id}` - Message received
- `💾 Stored message #{count}` - Message saved to cache
- `⏰ Started/reset 15s inactivity timer` - Trigger created/reset
- `⏰ User inactivity detected` - Expiry fired
- `✅ Successfully echoed {count} messages` - Messages sent back

## 🚨 Common Issues

### Expiry handler not firing?

1. **Check Redis keyspace notifications**:
   ```bash
   redis-cli CONFIG GET notify-keyspace-events
   # Should return: "Ex"
   ```

2. **Check ExpiryPlugin is registered**:
   ```python
   app.use_plugin(ExpiryPlugin())  # ← Must be called
   ```

3. **Check expiry handlers imported**:
   ```python
   from . import expiry_handlers  # ← Must import to register decorator
   ```

### Messages not accumulating?

1. **Check Redis connection**: Ensure `REDIS_URL` is correct
2. **Check cache factory**: Verify `cache_factory` is initialized in event handler
3. **Check logs**: Look for "💾 Stored message" log entries

### Timer not resetting?

1. **Verify trigger deletion**: Check logs for "Started/reset 15s inactivity timer"
2. **Check timing**: Ensure messages arrive within 15 seconds
3. **Debug expiry cache**:
   ```python
   # In master_event.py, check if trigger exists
   exists = await expiry_cache.exists("user_inactivity", user_id)
   self.logger.info(f"Trigger exists: {exists}")
   ```

## 🔗 Related Examples

- **wappa_full_example**: Complete bot with template state handlers
- **redis_cache_example**: Advanced Redis caching patterns
- **wpDemoHotels**: Original expiry actions pattern (reference implementation)

## 📚 Further Reading

- [ExpiryActions System Documentation](../../core/expiry/README.md)
- [Redis KEYSPACE Notifications](https://redis.io/docs/manual/keyspace-notifications/)
- [Wappa Plugin System](../../core/plugins/README.md)
- [Cache Factory Pattern](../../persistence/cache_factory.py)

## 🙏 Credits

This example is based on the ExpiryActions pattern from **wpDemoHotels**, demonstrating how to use Redis expiry events for inactivity detection and batch processing in production WhatsApp bots.
