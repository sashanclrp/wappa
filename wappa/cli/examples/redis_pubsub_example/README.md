# Redis PubSub Example - Multi-Inbox Self-Subscribing App

Demonstrates the **multi-Inbox self-subscribing** pattern: the app publishes events AND subscribes to them across every Inbox, building a messenger per Inbox on demand and reacting by sending WhatsApp messages.

## Architecture

```
User Message → Webhook → RedisPubSubPlugin → Redis PubSub
                                                    ↓
                                    Subscriber (this app, every Inbox)
                                                    ↓
                                    Builds a Messenger per Inbox (cached)
                                                    ↓
                                            WhatsApp Message
```

**Multi-Inbox Flow**:
- App PUBLISHES events via RedisPubSubPlugin
- App SUBSCRIBES to every Inbox via a background task
- App BUILDS a messenger per Inbox on demand
- App REACTS to events by sending WhatsApp messages

## Features

This example demonstrates 3 event types (bot_reply disabled to prevent loops):

1. **incoming_message**: User sends WhatsApp message → App reacts
2. **status_change**: Delivery/read receipts arrive → App reacts
3. **outgoing_message**: API sends message → App reacts
4. **bot_reply**: ❌ DISABLED (would cause infinite loop)

## Why bot_reply is Disabled

With `publish_bot_replies=True`, this would happen:

```
Subscriber receives event
    ↓
Sends WhatsApp message
    ↓
bot_reply event published
    ↓
Subscriber receives bot_reply
    ↓
Sends WhatsApp message
    ↓
INFINITE LOOP! 🔄
```

## Setup

1. Copy `.env.example` to `.env` and configure:
   ```bash
   cp .env.example .env
   ```

2. Start Redis:
   ```bash
   docker run -d -p 6379:6379 redis:alpine
   ```

3. Run the application:
   ```bash
   wappa dev app/main.py
   # or
   uvicorn app.main:app --reload
   ```

## How It Works

### 1. Send WhatsApp Message

```
User: "Hello"
    ↓
incoming_message published to Redis
    ↓
Subscriber receives notification
    ↓
App sends: "📨 PubSub Event Received - Incoming Message"
```

### 2. Delivery Receipt

```
WhatsApp sends delivery receipt
    ↓
status_change published to Redis
    ↓
Subscriber receives notification
    ↓
App sends: "✅ PubSub Event Received - Status: DELIVERED"
```

### 3. API Message

```bash
curl -X POST http://localhost:8000/api/whatsapp/messages/text \
  -H "Content-Type: application/json" \
  -d '{"recipient": "5511999887766", "text": "Hello from API!"}'
```

```
API sends message
    ↓
outgoing_message published to Redis
    ↓
Subscriber receives notification
    ↓
App sends: "📤 PubSub Event Received - API Message Sent"
```

## Channel Pattern

All notifications follow the pattern:
```
wappa:notify:{inbox}:{user_id}:{event_type}
```

The `{inbox}` segment is the Inbox cache namespace: the raw `inbox_id` for WhatsApp (Meta `phone_number_id`), or `<platform>__<id>` for any other Platform.

Examples:
- `wappa:notify:15551234567890:5511999887766:incoming_message`
- `wappa:notify:15551234567890:5511999887766:status_change`
- `wappa:notify:15551234567890:5511999887766:outgoing_message`

## Notification Payload

```json
{
  "event": "incoming_message",
  "inbox": "15551234567890",
  "user_id": "5511999887766",
  "platform": "whatsapp",
  "data": {
    "message_id": "wamid.xxx",
    "message_type": "text"
  },
  "timestamp": "2024-01-15T10:30:00Z",
  "v": "1"
}
```

## Plugin Configuration

```python
from wappa.core.plugins import RedisPubSubPlugin

RedisPubSubPlugin(
    publish_incoming=True,       # ✅ User messages
    publish_outgoing=True,       # ✅ API-sent messages
    publish_bot_replies=False,   # ❌ DISABLED (prevents loop)
    publish_status=True,         # ✅ Delivery/read receipts
)
```

## Multi-Inbox Support

**This example is multi-Inbox.** It subscribes to every Inbox and builds messengers on demand.

### How It Works

`subscribe()` yields a `Notification` (`wappa.persistence.redis.pubsub_subscriber.Notification`) with these fields:

```python
notification.event      # "incoming_message"
notification.inbox      # "15551234567890"  (Inbox cache namespace)
notification.user_id    # "5511999887766"
notification.platform   # "whatsapp"
notification.data       # {"message_id": "wamid.xxx", "message_type": "text"}
notification.timestamp  # ISO-8601
notification.channel    # the channel the message arrived on
notification.version    # payload version, currently "1"
```

The subscriber:

1. **Subscribes to ALL Inboxes**: Pattern `wappa:notify:*:*:*`
2. **Creates messengers dynamically**: One per Inbox, cached for reuse
3. **Uses Inbox-specific credentials**: Each Inbox uses its own WhatsApp credentials

```python
# From app/pubsub_listener.py
messenger_cache = {}  # Cache messengers by Inbox {inbox: IMessenger}

async for notification in subscribe(redis, patterns=["wappa:notify:*:*:*"]):
    inbox = notification.inbox

    # Multi-Inbox: get or build a messenger for this Inbox
    if inbox not in messenger_cache:
        messenger_cache[inbox] = await context_builder.messenger(
            InboxRef(platform=PlatformType(notification.platform), inbox_id=inbox)
        )

    # Use the Inbox-specific messenger
    await send_event_notification(
        messenger_cache[inbox], notification.user_id, notification.event, notification.data
    )
```

`context_builder` is a `DispatchContextBuilder`; `builder.messenger(InboxRef(...))` resolves that Inbox's credentials through the Inbox Directory and returns a ready messenger. It raises an `InboxDirectoryError` subclass when the Inbox is unknown, unavailable, or misconfigured — the listener logs and skips that notification rather than dying.

### Requirements

Every Inbox you expect to reply on must be resolvable: present in the legacy `WP_*` bundle in legacy mode, or in the Inbox Directory in explicit mode.

## Advanced: External Subscriber (No Loop Risk)

If you want a **separate service** (not the bot) to subscribe and react, you CAN enable `publish_bot_replies=True`:

```python
# External service (separate process)
from wappa.persistence.redis.pubsub_subscriber import subscribe

async for notification in subscribe(redis, patterns=["wappa:notify:*"]):
    # This service receives events but doesn't send WhatsApp messages
    # So no loop!
    print(f"Inbox: {notification.inbox}")
    print(f"User: {notification.user_id}")
    print(f"Event: {notification.event}, Data: {notification.data}")
```

This is safe because the external service doesn't send WhatsApp messages.
