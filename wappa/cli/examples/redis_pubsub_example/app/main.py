"""
Redis PubSub Example - MULTI-TENANT Self-Subscribing App

This example demonstrates MULTI-TENANT SELF-SUBSCRIBING to PubSub events:
- App PUBLISHES events via RedisPubSubPlugin
- App SUBSCRIBES to ALL tenants via background task
- App CREATES messengers dynamically per tenant
- App REACTS to events by sending WhatsApp messages

Event types demonstrated:
1. **incoming_message**: When users send messages via WhatsApp
2. **outgoing_message**: When messages are sent via API routes
3. **status_change**: When delivery/read receipts arrive

NOTE: bot_reply is DISABLED to prevent infinite loops (subscriber sends message → bot_reply → subscriber sends message...)

MULTI-TENANT SUPPORT:
- Subscribes to pattern: wappa:notify:*:*:*
- Creates messenger per tenant dynamically
- Each tenant uses its own WhatsApp credentials

SETUP REQUIRED:
1. Create a .env file with your WhatsApp Business API credentials:
    WP_ACCESS_TOKEN=your_access_token_here
    WP_PHONE_ID=your_phone_number_id_here
    WP_BID=your_business_id_here
    WP_WEBHOOK_VERIFY_TOKEN=your_verify_token_here

2. Set up Redis:
    REDIS_URL=redis://localhost:6379

USAGE:
- Direct Python: python -m app.main (from project root)
- FastAPI-style: uvicorn app.main:app --reload (from project root)
- Wappa CLI: wappa dev app/main.py
"""

import asyncio

from wappa import Wappa
from wappa.core.config.settings import settings
from wappa.core.logging import get_logger
from wappa.core.plugins import RedisPubSubPlugin

from .master_event import PubSubExampleHandler
from .pubsub_listener import start_pubsub_listener

logger = get_logger(__name__)


def validate_configuration() -> bool:
    """Validate required configuration settings."""
    missing_configs = []

    if not settings.wp_access_token:
        missing_configs.append("WP_ACCESS_TOKEN")

    if not settings.wp_phone_id:
        missing_configs.append("WP_PHONE_ID")

    if not settings.wp_bid:
        missing_configs.append("WP_BID")

    if not settings.has_redis:
        missing_configs.append("REDIS_URL")

    if missing_configs:
        logger.error(f"Missing required configuration: {', '.join(missing_configs)}")
        logger.error("Create a .env file with the required credentials")
        return False

    logger.info("Configuration validation passed")
    return True


def display_startup_information() -> None:
    """Display startup information and testing instructions."""
    print()
    print("=" * 80)
    print("  Redis PubSub Example - SELF-SUBSCRIBING App")
    print("=" * 80)
    print()

    print("ARCHITECTURE:")
    print("  📤 App PUBLISHES events → Redis PubSub")
    print("  📥 App SUBSCRIBES to events ← Redis PubSub")
    print("  💬 App REACTS by sending WhatsApp messages")
    print()

    print("PUBSUB EVENT TYPES (published & subscribed):")
    print("  ✅ incoming_message - User sends WhatsApp message")
    print("  ✅ status_change    - Delivery/read receipts")
    print("  ✅ outgoing_message - Messages sent via API routes")
    print("  ❌ bot_reply        - DISABLED (prevents infinite loop)")
    print()

    print("CHANNEL PATTERN:")
    print("  wappa:notify:{tenant}:{user_id}:{event_type}")
    print()

    print("HOW IT WORKS:")
    print("  1. User sends WhatsApp message")
    print("     → incoming_message published to Redis")
    print("     → Subscriber receives notification")
    print("     → App sends 'Event received!' message")
    print()
    print("  2. Delivery receipt arrives")
    print("     → status_change published to Redis")
    print("     → Subscriber receives notification")
    print("     → App sends status update message")
    print()
    print("  3. API sends message (via REST)")
    print("     → outgoing_message published to Redis")
    print("     → Subscriber receives notification")
    print("     → App sends confirmation message")
    print()

    print("WHY bot_reply IS DISABLED:")
    print("  ⚠️  With bot_reply enabled:")
    print("      Subscriber receives event → sends message → bot_reply published")
    print("      → Subscriber receives bot_reply → sends message → INFINITE LOOP!")
    print()
    print("=" * 80)
    print()


def create_wappa_application() -> Wappa:
    """Create and configure the Wappa application with PubSub plugin and subscriber."""
    try:
        logger.info("Creating Wappa application with Redis cache + PubSub...")

        # Create Wappa instance with Redis cache
        app = Wappa(cache="redis")

        # Add RedisPubSubPlugin to enable real-time notifications
        app.add_plugin(
            RedisPubSubPlugin(
                publish_incoming=True,  # User messages
                publish_outgoing=True,  # API-sent messages
                publish_bot_replies=False,  # DISABLED to prevent infinite loop!
                publish_status=True,  # Delivery/read receipts
            )
        )

        # Use add_startup_hook method from Wappa to register subscriber
        async def start_subscriber_hook(fastapi_app):
            """Start background PubSub subscriber."""
            logger.info("🔄 Starting Redis PubSub subscriber...")

            # Get HTTP session from app state (for messenger creation)
            http_session = getattr(fastapi_app.state, "http_session", None)
            if not http_session:
                logger.error("❌ HTTP session not available - cannot start subscriber")
                return

            # Start subscriber as background task
            asyncio.create_task(start_pubsub_listener(http_session))

            logger.info("✅ Redis PubSub subscriber started")

        app.add_startup_hook(start_subscriber_hook)

        logger.info("Wappa application created with RedisPubSubPlugin + Subscriber")
        return app

    except Exception as e:
        logger.error(f"Failed to create Wappa application: {e}")
        raise


def main() -> None:
    """Main application entry point."""
    logger.info("Starting Redis PubSub Example")

    try:
        display_startup_information()

        if not validate_configuration():
            logger.error("Configuration validation failed")
            return

        # Create app with PubSub subscriber
        app = create_wappa_application()

        # Create and set event handler
        handler = PubSubExampleHandler()
        app.set_event_handler(handler)

        logger.info("Application ready - starting server...")
        print("Starting server... Press CTRL+C to stop")
        print()

        app.run()

    except KeyboardInterrupt:
        logger.info("Application stopped by user")
        print("\nApplication stopped by user")

    except Exception as e:
        logger.error(f"Application startup error: {e}", exc_info=True)
        print(f"\nServer error: {e}")


# Module-level app instance for uvicorn compatibility
# This enables: uvicorn app.main:app --reload

try:
    logger.info("Creating module-level Wappa application instance")

    # Create app with subscriber
    app = create_wappa_application()

    # Create and set event handler
    handler = PubSubExampleHandler()
    app.set_event_handler(handler)

    logger.info(
        "Module-level application instance ready with RedisPubSubPlugin + Subscriber"
    )

except Exception as e:
    logger.error(f"Failed to create module-level app instance: {e}")
    raise


if __name__ == "__main__":
    main()
