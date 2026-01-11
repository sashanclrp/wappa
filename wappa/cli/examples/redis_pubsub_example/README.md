# Redis PubSub Example - MULTI-TENANT SELF-SUBSCRIBING App

Demonstrates **multi-tenant self-subscribing** pattern: the app publishes events AND subscribes to them across ALL tenants, dynamically creating messengers per tenant and reacting by sending WhatsApp messages.

## Architecture

```
User Message → Webhook → RedisPubSubPlugin → Redis PubSub
                                                    ↓
                                    Subscriber (this app, ALL tenants)
                                                    ↓
                                    Creates Messenger per Tenant (cached)
                                                    ↓
                                            WhatsApp Message
```

**Multi-Tenant Flow**:
- App PUBLISHES events via RedisPubSubPlugin
- App SUBSCRIBES to ALL tenants via background task
- App CREATES messengers dynamically per tenant
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
wappa:notify:{tenant}:{user_id}:{event_type}
```

Examples:
- `wappa:notify:mimeia:5511999887766:incoming_message`
- `wappa:notify:mimeia:5511999887766:status_change`
- `wappa:notify:mimeia:5511999887766:outgoing_message`

## Notification Payload

```json
{
  "event": "incoming_message",
  "tenant": "mimeia",
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

## Multi-Tenant Support

**This example IS MULTI-TENANT.** It subscribes to ALL tenants and creates messengers dynamically.

### How It Works

The notification contains tenant information:

```python
notification.tenant    # "mimeia", "acme", "company-x", etc.
notification.user_id   # "5511999887766"
notification.platform  # "whatsapp"
```

The subscriber:

1. **Subscribes to ALL tenants**: Pattern `wappa:notify:*:*:*`
2. **Creates messengers dynamically**: One per tenant, cached for reuse
3. **Uses tenant-specific credentials**: Each tenant uses its own WhatsApp credentials

```python
# From app/pubsub_listener.py
messenger_cache = {}  # Cache messengers by tenant {tenant_id: IMessenger}

async for notification in subscribe(redis, patterns=["wappa:notify:*:*:*"]):
    tenant = notification.tenant

    # MULTI-TENANT: Get or create messenger for this tenant
    if tenant not in messenger_cache:
        logger.info(f"🔨 Creating new messenger for tenant: {tenant}")
        messenger_cache[tenant] = await messenger_factory.create_messenger(
            platform=PlatformType(platform),
            tenant_id=tenant,  # Use tenant-specific credentials
        )

    # Use the tenant-specific messenger
    active_messenger = messenger_cache[tenant]
    await send_event_notification(active_messenger, user_id, event_type, data)
```

### Requirements

Each tenant must have its own WhatsApp credentials configured in the system.

## Advanced: External Subscriber (No Loop Risk)

If you want a **separate service** (not the bot) to subscribe and react, you CAN enable `publish_bot_replies=True`:

```python
# External service (separate process)
from wappa.persistence.redis.pubsub_subscriber import subscribe

async for notification in subscribe(redis, patterns=["wappa:notify:*"]):
    # This service receives events but doesn't send WhatsApp messages
    # So no loop!
    print(f"Tenant: {notification.tenant}")
    print(f"User: {notification.user_id}")
    print(f"Event: {notification.event}, Data: {notification.data}")
```

This is safe because the external service doesn't send WhatsApp messages.
