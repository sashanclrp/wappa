"""
Wappa Full Example - Main Application Entry Point

This is a comprehensive demonstration of the Wappa framework capabilities including:
- Complete message type handling with metadata extraction
- Interactive commands (/button, /list, /cta, /location) with state management
- Media relay functionality using media_id
- User tracking and analytics with Redis cache
- Welcome messages for first-time users
- Professional error handling and logging

SETUP REQUIRED:
1. Create a .env file with your WhatsApp Business API credentials:
   WP_ACCESS_TOKEN=your_access_token_here
   WP_PHONE_ID=your_phone_number_id_here
   WP_BID=your_business_id_here

2. Set up Redis:
   REDIS_URL=redis://localhost:6379

FEATURES DEMONSTRATED:
- Comprehensive webhook metadata extraction for all message types
- Interactive button demo with animal selection and media responses
- Interactive list demo with media file types
- CTA button linking to external documentation
- Location sharing with predefined coordinates
- State management with TTL (10 minute expiration)
- User profile caching and activity tracking
- First-time user welcome messages with instructions

USAGE:
- Direct Python: python -m app.main (from project root)
- FastAPI-style: uvicorn app.main:app --reload (from project root)
- uv run: uv run python -m app.main
"""

from wappa import Wappa, __version__
from wappa.core.config.settings import settings
from wappa.core.logging import get_logger

logger = get_logger(__name__)

# Import our comprehensive WappaEventHandler implementation
from .master_event import WappaFullExampleHandler


def validate_configuration() -> bool:
    """
    Validate required configuration settings.

    Returns:
        True if configuration is valid, False otherwise
    """
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
        logger.error(f"❌ Missing required configuration: {', '.join(missing_configs)}")
        logger.error("💡 Create a .env file with the required credentials")
        return False

    logger.info("✅ Configuration validation passed")
    return True


def display_startup_information() -> None:
    """
    Display startup information and demo features.
    """
    print(f"🚀 Wappa v{__version__} - Full Example (Comprehensive Demo)")
    print("=" * 80)
    print()

    print("🎯 *COMPREHENSIVE WAPPA FRAMEWORK DEMONSTRATION*")
    print("  This example showcases ALL major Wappa framework features:")
    print("  • Complete message type handling with metadata extraction")
    print("  • Interactive commands with state management and TTL")
    print("  • Media relay functionality using media_id")
    print("  • User tracking and analytics with Redis cache")
    print("  • Welcome messages for first-time users")
    print("  • Professional error handling and logging")
    print()

    print("📋 *CONFIGURATION STATUS:*")
    print(
        f"  • Access Token: {'✅ Configured' if settings.wp_access_token else '❌ Missing'}"
    )
    print(
        f"  • Phone ID: {settings.wp_phone_id if settings.wp_phone_id else '❌ Missing'}"
    )
    print(f"  • Business ID: {'✅ Configured' if settings.wp_bid else '❌ Missing'}")
    print(f"  • Redis URL: {'✅ Configured' if settings.has_redis else '❌ Missing'}")
    print(
        f"  • Environment: {'🛠️ Development' if settings.is_development else '🚀 Production'}"
    )
    print()

    print("🎮 *INTERACTIVE DEMO COMMANDS:*")
    print("  • `/button` → Interactive button demo with animal selection")
    print("    - Creates buttons for Kitty 🐱 and Puppy 🐶")
    print("    - 10-minute TTL with state management")
    print("    - Sends corresponding animal image on selection")
    print("    - Shows comprehensive metadata extraction")
    print()
    print("  • `/list` → Interactive list demo with media files")
    print("    - List with Image, Video, Audio, Document options")
    print("    - Sends actual media files based on selection")
    print("    - Demonstrates list interaction patterns")
    print()
    print("  • `/cta` → Call-to-Action button demonstration")
    print("    - External link to Wappa documentation")
    print("    - Shows CTA button implementation")
    print()
    print("  • `/location` → Location sharing demonstration")
    print("    - Shares predefined location (Bogotá, Colombia)")
    print("    - Shows location message implementation")
    print()

    print("📨 *MESSAGE TYPE HANDLING:*")
    print("  • Text Messages → Echo with 'Echo - {content}' + metadata")
    print("  • Media Messages → Relay same media using media_id + metadata")
    print("  • Location Messages → Echo same location coordinates + metadata")
    print("  • Contact Messages → Echo contact information + metadata")
    print("  • Interactive Messages → Process selections + metadata")
    print()

    print("👤 *USER MANAGEMENT FEATURES:*")
    print("  • First-time user detection and welcome messages")
    print("  • User profile caching with activity tracking")
    print("  • Message count and interaction statistics")
    print("  • Command usage analytics")
    print()

    print("🏗️ *TECHNICAL ARCHITECTURE:*")
    print("  • Redis cache for user profiles and interactive states")
    print("  • Comprehensive metadata extraction per message type")
    print("  • State management with TTL for interactive features")
    print("  • Professional error handling and recovery")
    print("  • Structured logging with performance metrics")
    print("  • Clean code architecture with separation of concerns")
    print()

    print("📊 *DEMONSTRATED PATTERNS:*")
    print("  • Complete IMessenger interface utilization")
    print("  • Media handling with download/upload capabilities")
    print("  • Interactive workflow state machines")
    print("  • User session and activity tracking")
    print("  • Production-ready error handling")
    print("  • Scalable Redis caching strategies")
    print()


def create_wappa_application() -> Wappa:
    """
    Create and configure the Wappa application.

    Returns:
        Configured Wappa application instance
    """
    try:
        # Create Wappa instance with Redis cache
        logger.info("🏗️ Creating Wappa application with Redis cache...")
        app = Wappa(cache="redis")

        logger.info("✅ Wappa application created successfully")
        return app

    except Exception as e:
        logger.error(f"❌ Failed to create Wappa application: {e}")
        raise


def main() -> None:
    """
    Main application entry point.

    Demonstrates complete Wappa framework integration with:
    - Configuration validation
    - Application setup
    - Handler registration
    - Professional startup flow
    """
    logger.info("🚀 Starting Wappa Full Example - Comprehensive Demo")

    try:
        # Display comprehensive startup information
        display_startup_information()

        # Validate configuration before proceeding
        if not validate_configuration():
            logger.error(
                "❌ Configuration validation failed - cannot start application"
            )
            return

        # Create Wappa application
        app = create_wappa_application()

        # Create and set our comprehensive WappaEventHandler implementation
        handler = WappaFullExampleHandler()
        app.set_event_handler(handler)

        logger.info(
            "✅ Application initialization completed with comprehensive WappaEventHandler"
        )

        print("🌐 Starting comprehensive Wappa demo server...")
        print("💡 Press CTRL+C to stop the server")
        print()
        print("🎯 *Try these features once connected:*")
        print("   1. Send any message → See metadata extraction + echo")
        print("   2. Send /button → Interactive button demo")
        print("   3. Send /list → Interactive list demo")
        print("   4. Send /cta → Call-to-action button")
        print("   5. Send /location → Location sharing demo")
        print("   6. Send media files → See media relay functionality")
        print("=" * 80)
        print()

        # Start the application
        # The framework will handle dependency injection automatically
        app.run()

    except KeyboardInterrupt:
        logger.info("👋 Application stopped by user")
        print("\n👋 Wappa Full Example stopped by user")

    except Exception as e:
        logger.error(f"❌ Application startup error: {e}", exc_info=True)
        print(f"\n❌ Server error: {e}")

    finally:
        logger.info("🏁 Wappa Full Example completed")
        print("🏁 Wappa Full Example completed")


# Module-level app instance for uvicorn compatibility
# This enables: uvicorn app.main:app --reload

try:
    logger.info("📦 Creating module-level Wappa application instance")
    app = Wappa(cache="redis")

    # Create and set our comprehensive WappaEventHandler implementation
    handler = WappaFullExampleHandler()
    app.set_event_handler(handler)

    logger.info(
        "✅ Module-level application instance ready with comprehensive WappaEventHandler"
    )

except Exception as e:
    logger.error(f"❌ Failed to create module-level app instance: {e}")
    raise


if __name__ == "__main__":
    main()
