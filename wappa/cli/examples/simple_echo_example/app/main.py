"""
Simple Echo Example - Clean Architecture Implementation

This is a simplified version of the Redis cache example that demonstrates
basic Wappa functionality without complex dependencies.

Features:
- Clean WappaEventHandler implementation
- Simple message echoing for all message types
- Proper dependency injection
- Professional logging and error handling

SETUP REQUIRED:
1. Create a .env file with your WhatsApp Business API credentials:
    WP_ACCESS_TOKEN=your_access_token_here
    WP_PHONE_ID=your_phone_number_id_here
    WP_BID=your_business_id_here

USAGE:
- Direct Python: python -m app.main (from project root)
- FastAPI-style: uvicorn app.main:app --reload (from project root)
- Wappa CLI: wappa run app/main.py (from project root)
"""

# Import core Wappa components
from wappa import Wappa, __version__
from wappa.core.config.settings import settings
from wappa.core.logging import get_logger

logger = get_logger(__name__)

# Import our simple echo handler
from .master_event import SimpleEchoHandler


def validate_configuration() -> bool:
    """
    Validate required configuration settings.

    Returns:
        True if configuration is valid, False otherwise
    """

    # Check required WhatsApp credentials
    missing_configs = []

    if not settings.wp_access_token:
        missing_configs.append("WP_ACCESS_TOKEN")

    if not settings.wp_phone_id:
        missing_configs.append("WP_PHONE_ID")

    if not settings.wp_bid:
        missing_configs.append("WP_BID")

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
    print(f"🚀 Wappa v{__version__} - Simple Echo Example")
    print("=" * 70)
    print()

    print("📋 *CONFIGURATION STATUS:*")
    print(
        f"  • Access Token: {'✅ Configured' if settings.wp_access_token else '❌ Missing'}"
    )
    print(
        f"  • Phone ID: {settings.wp_phone_id if settings.wp_phone_id else '❌ Missing'}"
    )
    print(f"  • Business ID: {'✅ Configured' if settings.wp_bid else '❌ Missing'}")
    print(
        f"  • Environment: {'🛠️ Development' if settings.is_development else '🚀 Production'}"
    )
    print()

    print("🎯 *DEMO FEATURES:*")
    print("  • Send any text message → Get echo response")
    print("  • Send media files → Get acknowledgment")
    print("  • Send location → Get location confirmation")
    print("  • Send contacts → Get contact confirmation")
    print("  • All messages are counted and logged")
    print()

    print("🔧 *TECHNICAL FEATURES:*")
    print("  • Clean WappaEventHandler implementation")
    print("  • Proper dependency injection")
    print("  • Multi-message-type support")
    print("  • Professional error handling")
    print("  • Structured logging")
    print()


def create_wappa_application() -> Wappa:
    """
    Create and configure the Wappa application.

    Returns:
        Configured Wappa application instance
    """

    try:
        # Create Wappa instance with JSON cache (simple file-based cache for echo example)
        logger.info("🏗️ Creating Wappa application with JSON cache...")
        app = Wappa(cache="json")

        logger.info("✅ Wappa application created successfully")
        return app

    except Exception as e:
        logger.error(f"❌ Failed to create Wappa application: {e}")
        raise


def main() -> None:
    """
    Main application entry point.
    """

    logger.info("🚀 Starting Simple Echo Example")

    try:
        # Display startup information
        display_startup_information()

        # Validate configuration before proceeding
        if not validate_configuration():
            logger.error(
                "❌ Configuration validation failed - cannot start application"
            )
            return

        # Create Wappa application
        app = create_wappa_application()

        # Create and set the simple echo handler
        handler = SimpleEchoHandler()
        app.set_event_handler(handler)

        logger.info("✅ Application initialization completed with SimpleEchoHandler")

        print("🌐 Starting simple echo server...")
        print("💡 Press CTRL+C to stop the server")
        print("=" * 70)
        print()

        # Start the application
        app.run()

    except KeyboardInterrupt:
        logger.info("👋 Application stopped by user")
        print("\\n👋 Simple echo server stopped by user")

    except Exception as e:
        logger.error(f"❌ Application startup error: {e}", exc_info=True)
        print(f"\\n❌ Server error: {e}")

    finally:
        logger.info("🏁 Simple echo example completed")
        print("🏁 Simple echo example completed")


# Module-level app instance for uvicorn compatibility
# This enables: uvicorn app.main:app --reload

try:
    logger.info("📦 Creating module-level Wappa application instance")
    app = Wappa()

    # Create and set the simple echo handler
    handler = SimpleEchoHandler()
    app.set_event_handler(handler)

    logger.info("✅ Module-level application instance ready with SimpleEchoHandler")

except Exception as e:
    logger.error(f"❌ Failed to create module-level app instance: {e}")
    raise


if __name__ == "__main__":
    main()
