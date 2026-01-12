"""
DB + Redis Echo Example - PostgreSQL persistence with Redis caching

Demonstrates PostgresDatabasePlugin with Redis caching for conversation history:
- Redis cache for active conversation messages (fast access)
- PostgreSQL persistence when conversations close (long-term storage)
- Echo bot that tracks message history with /CLOSE and /HISTORY commands

SETUP REQUIRED:
1. Set up Redis server (localhost:6379 by default)
2. Set up PostgreSQL database (Supabase recommended)
3. Configure environment in .env file:
    WP_ACCESS_TOKEN=your_access_token_here
    WP_PHONE_ID=your_phone_number_id_here
    WP_BID=your_business_id_here
    REDIS_URL=redis://localhost:6379
    DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/db

DEMO FEATURES:
- Redis caching for active conversations
- PostgreSQL persistence when conversation closes
- Message history tracking with /HISTORY command
- Conversation management with /CLOSE command
- Echo bot with message counter

USAGE:
- Direct Python: python -m app.main (from project root)
- FastAPI-style: uvicorn app.main:app --reload (from project root)
- Wappa CLI: wappa dev app.main (when CLI is available)
"""

from wappa import Wappa, __version__
from wappa.core.logging import get_logger
from wappa.core.plugins import PostgresDatabasePlugin

from .config.config import settings_with_db
from .master_event import DBRedisExampleHandler
from .models.database_models import Chat, Conversation, Message

logger = get_logger(__name__)


def validate_configuration() -> bool:
    """
    Validate required configuration settings.

    Returns:
        True if configuration is valid, False otherwise
    """
    missing_configs = []

    if not settings_with_db.wp_access_token:
        missing_configs.append("WP_ACCESS_TOKEN")

    if not settings_with_db.wp_phone_id:
        missing_configs.append("WP_PHONE_ID")

    if not settings_with_db.wp_bid:
        missing_configs.append("WP_BID")

    if not settings_with_db.has_redis:
        missing_configs.append("REDIS_URL")

    if not settings_with_db.database_url:
        missing_configs.append("DATABASE_URL")

    if missing_configs:
        logger.error(f"Missing required configuration: {', '.join(missing_configs)}")
        logger.error("Create a .env file with the required credentials")
        return False

    logger.info("Configuration validation passed")
    return True


def display_startup_information() -> None:
    """Display startup information and demo features."""
    print(f"Wappa v{__version__} - DB + Redis Echo Example")
    print("=" * 80)
    print()

    print("ARCHITECTURE:")
    print("  - Redis: Active conversation caching (fast access)")
    print("  - PostgreSQL: Long-term message persistence (Supabase)")
    print("  - Echo bot: Message tracking with history and close commands")
    print()

    print("CONFIGURATION STATUS:")
    print(
        f"  - Access Token: {'Configured' if settings_with_db.wp_access_token else 'Missing'}"
    )
    print(
        f"  - Phone ID: {settings_with_db.wp_phone_id if settings_with_db.wp_phone_id else 'Missing'}"
    )
    print(f"  - Business ID: {'Configured' if settings_with_db.wp_bid else 'Missing'}")
    print(f"  - Redis URL: {'Configured' if settings_with_db.has_redis else 'Missing'}")
    print(
        f"  - Database URL: {'Configured' if settings_with_db.database_url else 'Missing'}"
    )
    print()

    print("DEMO FEATURES:")
    print("  1. Send any message -> Echoed back with message count")
    print("  2. Send '/HISTORY' -> View message count in current conversation")
    print("  3. Send '/CLOSE' -> Close conversation and persist to database")
    print()

    print("CACHE + DATABASE ARCHITECTURE:")
    print("  - Redis: Active conversation messages with automatic expiry")
    print("  - PostgreSQL: Closed conversations with full message history")
    print("  - Supabase schema: Chat, Conversation, Message tables with ENUMs")
    print()


def create_wappa_application() -> Wappa:
    """
    Create and configure the Wappa application.

    Returns:
        Configured Wappa application instance

    Raises:
        ValueError: If DATABASE_URL is not configured
    """
    if not settings_with_db.database_url:
        raise ValueError(
            "DATABASE_URL environment variable is required. "
            "Set it in your .env file: DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/db"
        )

    try:
        logger.info("Creating Wappa application with Redis cache...")
        app = Wappa(cache="redis")

        # Add PostgreSQL database plugin using settings
        logger.info("Adding PostgresDatabasePlugin...")
        app.add_plugin(
            PostgresDatabasePlugin(
                url=settings_with_db.database_url,
                models=[Chat, Conversation, Message],
                auto_create_tables=False,  # Tables already exist in database
                auto_commit=True,
                pool_size=10,
                max_overflow=20,
                pool_timeout=30,
                max_retries=3,
                statement_cache_size=0,  # Required for Supabase pgBouncer (transaction mode)
            )
        )

        logger.info("Wappa application created successfully")
        return app

    except Exception as e:
        logger.error(f"Failed to create Wappa application: {e}")
        raise


def main() -> None:
    """Main application entry point."""
    logger.info("Starting DB + Redis Echo Example")

    try:
        # Display startup information
        display_startup_information()

        # Validate configuration before proceeding
        if not validate_configuration():
            logger.error("Configuration validation failed - cannot start application")
            return

        # Create Wappa application
        app = create_wappa_application()

        # Create and set event handler
        handler = DBRedisExampleHandler()
        app.set_event_handler(handler)

        logger.info("Application initialization completed")

        print("Starting DB + Redis echo demo server...")
        print("Press CTRL+C to stop the server")
        print("=" * 80)
        print()

        # Start the application
        app.run()

    except KeyboardInterrupt:
        logger.info("Application stopped by user")
        print("\nDB + Redis echo demo stopped by user")

    except Exception as e:
        logger.error(f"Application startup error: {e}", exc_info=True)
        print(f"\nServer error: {e}")

    finally:
        logger.info("DB + Redis echo demo completed")
        print("DB + Redis echo demo completed")


# Module-level app instance for uvicorn compatibility
# Only create if DATABASE_URL is configured
if settings_with_db.database_url:
    try:
        logger.info("Creating module-level Wappa application instance")
        app = Wappa(cache="redis")

        # Add PostgreSQL database plugin using settings
        app.add_plugin(
            PostgresDatabasePlugin(
                url=settings_with_db.database_url,
                models=[Chat, Conversation, Message],
                auto_create_tables=False,
                auto_commit=True,
                pool_size=10,
                max_overflow=20,
                pool_timeout=30,
                max_retries=3,
                statement_cache_size=0,  # Required for Supabase pgBouncer (transaction mode)
            )
        )

        # Create and set event handler
        handler = DBRedisExampleHandler()
        app.set_event_handler(handler)

        logger.info("Module-level application instance ready")

    except Exception as e:
        logger.error(f"Failed to create module-level app instance: {e}")
        raise
else:
    # Create a minimal app instance that will fail gracefully at startup
    logger.warning(
        "DATABASE_URL not configured. Set it in your .env file before running."
    )
    app = None  # type: ignore[assignment]


if __name__ == "__main__":
    main()
