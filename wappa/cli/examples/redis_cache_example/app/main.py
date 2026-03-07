"""
Redis Cache Example - SOLID Architecture Implementation

This is the main initialization file following SOLID principles:
- Single Responsibility: Pure initialization and configuration
- Open/Closed: Extensible through score module registration
- Liskov Substitution: Compatible with Wappa framework interface
- Interface Segregation: Clean dependency interfaces
- Dependency Inversion: Abstractions injected into concrete implementations

SETUP REQUIRED:
1. Create a .env file with your WhatsApp Business API credentials:
    WP_ACCESS_TOKEN=your_access_token_here
    WP_PHONE_ID=your_phone_number_id_here
    WP_BID=your_business_id_here

2. Set up Redis:
    REDIS_URL=redis://localhost:6379

DEMO FEATURES:
- SOLID architecture with separated concerns
- Master event orchestrator with score modules
- User management, message history, and state commands
- Cache statistics and monitoring
- Professional logging and error handling

USAGE:
- Direct Python: python -m app.main (from project root)
- FastAPI-style: uvicorn app.main:app --reload (from project root)
- Wappa CLI: wappa dev app.main (when CLI is available)
"""

# Import core Wappa components
from wappa import Wappa, __version__
from wappa.core.config.settings import settings
from wappa.core.logging import get_logger

# Import our SOLID architecture WappaEventHandler implementation
from .master_event import RedisCacheExampleHandler

logger = get_logger(__name__)


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

    Shows configuration status, architecture overview,
    and available demo features.
    """
    print(f"🚀 Wappa v{__version__} - Redis Cache Example (SOLID Architecture)")
    print("=" * 80)
    print()

    print("🏗️ *SOLID ARCHITECTURE IMPLEMENTATION:*")
    print("  • Single Responsibility: Each score module has one specific concern")
    print("  • Open/Closed: New score modules can be added without modification")
    print("  • Liskov Substitution: All scores implement the same interface")
    print("  • Interface Segregation: Clean, focused interfaces for each concern")
    print("  • Dependency Inversion: Dependencies injected through abstractions")
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

    print("🎯 *SCORE MODULES (BUSINESS LOGIC):*")
    print("  • UserManagementScore: User profile and caching logic")
    print("  • MessageHistoryScore: Message logging and /HISTORY command")
    print("  • StateCommandsScore: /WAPPA and /EXIT command processing")
    print("  • CacheStatisticsScore: Cache monitoring and /STATS command")
    print()

    print("🧪 *DEMO FEATURES:*")
    print("  1. Send any message → User profile created/updated + message logged")
    print("  2. Send '/WAPPA' → Enter special state with cache management")
    print("  3. While in WAPPA state → All messages replied with 'Hola Wapp@ ;)'")
    print("  4. Send '/EXIT' → Leave special state with session summary")
    print("  5. Send '/HISTORY' → View your last 20 messages with timestamps")
    print("  6. Send '/STATS' → View comprehensive cache statistics")
    print()

    print("💎 *REDIS CACHE ARCHITECTURE:*")
    print("  • user_cache: User profiles with dependency injection")
    print("  • table_cache: Message history with BaseModel auto-serialization")
    print("  • state_cache: Command state management with TTL")
    print("  • Comprehensive error handling and logging")
    print()

    print("🔧 *TECHNICAL FEATURES:*")
    print("  • Dependency injection with interface abstractions")
    print("  • Score module registry with automatic discovery")
    print("  • Professional error handling and recovery")
    print("  • Performance monitoring and statistics")
    print("  • Comprehensive logging with structured output")
    print("  • Proper WappaEventHandler implementation with all required methods")
    print()


def create_wappa_application() -> Wappa:
    """
    Create and configure the Wappa application.

    This function follows Single Responsibility Principle by focusing
    only on application creation and initial configuration.

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

    Demonstrates SOLID principles in action:
    - Single Responsibility: Each function has one clear purpose
    - Dependency Inversion: Dependencies flow from abstractions
    - Open/Closed: System is open for extension via score modules
    """

    logger.info("🚀 Starting Redis Cache Example with SOLID Architecture")

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

        # Create and set the SOLID WappaEventHandler implementation
        handler = RedisCacheExampleHandler()
        app.set_event_handler(handler)

        logger.info(
            "✅ Application initialization completed with SOLID WappaEventHandler"
        )

        print("🌐 Starting SOLID Redis cache demo server...")
        print("💡 Press CTRL+C to stop the server")
        print("=" * 80)
        print()

        # Start the application
        # The framework will handle dependency injection automatically
        app.run()

    except KeyboardInterrupt:
        logger.info("👋 Application stopped by user")
        print("\n👋 Redis cache demo stopped by user")

    except Exception as e:
        logger.error(f"❌ Application startup error: {e}", exc_info=True)
        print(f"\n❌ Server error: {e}")

    finally:
        logger.info("🏁 Redis cache demo completed")
        print("🏁 Redis cache demo completed")


# Module-level app instance for uvicorn compatibility
# This enables: uvicorn main:app --reload

# Set up basic logging for module-level initialization


try:
    logger.info("📦 Creating module-level Wappa application instance")
    app = Wappa(cache="redis")

    # Create and set the SOLID WappaEventHandler implementation
    handler = RedisCacheExampleHandler()
    app.set_event_handler(handler)

    logger.info(
        "✅ Module-level application instance ready with SOLID WappaEventHandler"
    )

except Exception as e:
    logger.error(f"❌ Failed to create module-level app instance: {e}")
    raise


if __name__ == "__main__":
    main()
