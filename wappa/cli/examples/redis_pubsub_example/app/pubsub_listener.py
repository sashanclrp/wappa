"""
Redis PubSub Listener - Background task that subscribes to PubSub events.

This listener demonstrates SELF-SUBSCRIBING pattern:
- Subscribes to PubSub channels published by RedisPubSubPlugin
- Receives event notifications in real-time
- Sends WhatsApp messages to users about the events

Architecture:
    RedisPubSubPlugin → Redis PubSub → This Listener → WhatsApp Messenger
"""

import asyncio
from typing import TYPE_CHECKING

from redis.asyncio import Redis

from wappa.core.config.settings import settings
from wappa.core.logging import get_logger
from wappa.domain.factories.messenger_factory import MessengerFactory
from wappa.persistence.redis.pubsub_subscriber import subscribe
from wappa.schemas.core.types import PlatformType

if TYPE_CHECKING:
    from wappa.domain.interfaces.messaging_interface import IMessenger

logger = get_logger(__name__)


async def start_pubsub_listener(http_session) -> None:
    """
    Start Redis PubSub subscriber in background with MULTI-TENANT support.

    This subscriber dynamically creates messengers per inbox as notifications
    arrive, supporting unlimited WhatsApp accounts/inboxes.

    Architecture:
    - Subscribes to ALL inboxes: wappa:notify:*:*:*
    - Creates messenger per inbox on-demand (cached)
    - Each inbox uses its own WhatsApp credentials

    Args:
        http_session: HTTP session for creating messenger (from app.state)
    """
    redis = None
    messenger_cache = {}  # Cache messengers by inbox {inbox_id: IMessenger}

    try:
        logger.info("🔄 Creating messenger factory for MULTI-TENANT subscriber...")

        # Create messenger factory (creates messengers dynamically per inbox)
        messenger_factory = MessengerFactory(http_session)

        logger.info("✅ Messenger factory ready for multi-inbox support")
        logger.info("🔄 Connecting to Redis for PubSub subscription...")

        # Get Redis URL from settings
        redis_url = (
            str(settings.redis_url) if settings.redis_url else "redis://localhost:6379"
        )

        # Create Redis connection
        redis = Redis.from_url(redis_url, decode_responses=True)

        # MULTI-INBOX: Subscribe to ALL inboxes, ALL users, ALL event types
        # Pattern: wappa:notify:*:*:*
        pattern = "wappa:notify:*:*:*"

        logger.info(f"📡 Subscribing to MULTI-TENANT pattern: {pattern}")
        logger.info("🌐 Will create messengers dynamically per inbox")

        # Subscribe and listen for notifications
        async for notification in subscribe(redis, patterns=[pattern]):
            try:
                # Extract notification details
                event_type = notification.event
                inbox = notification.inbox  # ← Inbox from notification
                user_id = notification.user_id  # ← User from notification
                platform = notification.platform  # ← Platform from notification
                data = notification.data

                logger.info(
                    f"📩 Received {event_type} event for inbox={inbox}, user={user_id}: {data}"
                )

                # MULTI-INBOX: Get or create messenger for this inbox
                if inbox not in messenger_cache:
                    logger.info(f"🔨 Creating new messenger for inbox: {inbox}")
                    try:
                        messenger_cache[
                            inbox
                        ] = await messenger_factory.create_messenger(
                            platform=PlatformType(platform),
                            inbox_id=inbox,
                        )
                        logger.info(f"✅ Messenger created for inbox: {inbox}")
                    except Exception as e:
                        logger.error(
                            f"❌ Failed to create messenger for inbox {inbox}: {e}",
                            exc_info=True,
                        )
                        continue  # Skip this notification

                # Get the inbox-specific messenger
                active_messenger = messenger_cache[inbox]

                # Send WhatsApp message to user about the event
                await send_event_notification(
                    active_messenger,
                    user_id,
                    event_type,
                    data,
                )

            except Exception as e:
                logger.error(f"❌ Error processing notification: {e}", exc_info=True)

    except asyncio.CancelledError:
        logger.info("🛑 PubSub listener cancelled")
        raise

    except Exception as e:
        logger.error(f"❌ Fatal error in PubSub listener: {e}", exc_info=True)

    finally:
        try:
            if redis:
                await redis.close()
                logger.info("✅ Redis connection closed")
        except Exception as e:
            logger.error(f"Error closing Redis connection: {e}")


async def send_event_notification(
    messenger: "IMessenger",
    user_id: str,
    event_type: str,
    data: dict,
) -> None:
    """
    Send WhatsApp message to user about received event.

    Args:
        messenger: Messenger instance for sending messages
        user_id: User to notify
        event_type: Type of event received
        data: Event data
    """
    try:
        # Build notification message
        message = _build_notification_message(event_type, data)

        # Send via messenger
        result = await messenger.send_text(
            recipient=user_id,
            text=message,
        )

        if result.success:
            logger.info(f"✅ Sent {event_type} notification to {user_id}")
        else:
            logger.error(f"❌ Failed to send notification: {result.error}")

    except Exception as e:
        logger.error(f"❌ Error sending event notification: {e}", exc_info=True)


def _build_notification_message(event_type: str, data: dict) -> str:
    """
    Build WhatsApp message about the event.

    Args:
        event_type: Type of event
        data: Event data

    Returns:
        Formatted message string
    """
    # Event type emojis
    emojis = {
        "incoming_message": "📨",
        "outgoing_message": "📤",
        "bot_reply": "🤖",
        "status_change": "✅",
    }

    emoji = emojis.get(event_type, "📡")
    event_name = event_type.replace("_", " ").title()

    # Build message based on event type
    if event_type == "incoming_message":
        message_type = data.get("message_type", "unknown")
        return (
            f"{emoji} *PubSub Event Received*\n\n"
            f"Event: {event_name}\n"
            f"Type: {message_type}\n\n"
            f"This notification was triggered by the Redis PubSub subscriber!"
        )

    elif event_type == "status_change":
        status = data.get("status", "unknown")
        return (
            f"{emoji} *PubSub Event Received*\n\n"
            f"Event: {event_name}\n"
            f"Status: {status.upper()}\n\n"
            f"This notification shows your message was {status}!"
        )

    elif event_type == "outgoing_message":
        message_type = data.get("message_type", "unknown")
        success = data.get("success", False)
        status = "✅ Success" if success else "❌ Failed"
        return (
            f"{emoji} *PubSub Event Received*\n\n"
            f"Event: {event_name}\n"
            f"Type: {message_type}\n"
            f"Status: {status}\n\n"
            f"This notification was triggered by an API-sent message!"
        )

    else:
        return (
            f"{emoji} *PubSub Event Received*\n\n"
            f"Event: {event_name}\n"
            f"Data: {data}\n\n"
            f"Self-subscribing example working!"
        )
