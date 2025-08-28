"""
Echo Project for Wappa Framework

A comprehensive WhatsApp echo system demonstrating all features of the Wappa framework.
This project replicates the complete echo_test_event functionality using Wappa's clean architecture.

Features:
- Comprehensive message echoing with metadata extraction
- Interactive buttons with state management (10min TTL)
- Interactive lists with media options (10min TTL) 
- CTA buttons with URL links (stateless)
- Location request functionality (stateless)
- User data caching (24hr TTL)
- Media echo using WhatsApp media IDs
- State management with Redis cache
- Clean architecture with layered processing

SETUP REQUIRED:
1. Create a .env file with your WhatsApp Business API credentials:
    WP_ACCESS_TOKEN=your_access_token_here
    WP_PHONE_ID=your_phone_number_id_here
    WP_BID=your_business_id_here

2. Set up Redis:
    REDIS_URL=redis://localhost:6379

Commands to test:
- Send any message → Comprehensive echo with metadata
- Send '/button' → Interactive buttons demo
- Send '/list' → Interactive list with media options
- Send '/cta' → Call-to-action button demo
- Send '/location' → Location request demo
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from wappa import Wappa, __version__
from wappa.core.config.settings import settings

from echo_handler import EchoProjectHandler


def create_wappa_app_with_redis() -> Wappa:
    """
    Create Wappa application with Redis cache using unified plugin architecture.
    
    This demonstrates the unified way to use Redis cache - just specify cache="redis"
    and Wappa automatically adds RedisPlugin through the unified architecture.
    """
    print("🔧 Creating Echo Project Wappa app with Redis cache...")

    try:
        # Unified architecture - just specify cache type!
        # Wappa automatically adds RedisPlugin + WappaCorePlugin
        wappa = Wappa(cache="redis")

        print("✅ Wappa created with automatic Redis plugin integration")

        # Set the echo project event handler
        handler = EchoProjectHandler()
        wappa.set_event_handler(handler)

        print("✅ Echo Project handler configured with Redis cache")

        return wappa

    except Exception as e:
        print(f"❌ Failed to create Wappa app with Redis: {e}")
        raise


# Export FastAPI app for uvicorn reload with lazy loading
def create_fastapi_app():
    """Create FastAPI app synchronously for uvicorn reload compatibility."""
    import asyncio
    import threading

    # Check if we're in an event loop (uvicorn subprocess context)
    try:
        loop = asyncio.get_running_loop()
        # We're in a running loop, use thread-based async execution
        result = None
        exception = None

        def run_async():
            nonlocal result, exception
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            try:
                # Create the app and get FastAPI instance
                wappa_app = create_wappa_app_with_redis()
                result = new_loop.run_until_complete(wappa_app.create_app())
            except Exception as e:
                exception = e
            finally:
                new_loop.close()

        thread = threading.Thread(target=run_async)
        thread.start()
        thread.join()

        if exception:
            raise exception
        return result

    except RuntimeError:
        # No running loop, safe to use asyncio.run()
        wappa_app = create_wappa_app_with_redis()
        return asyncio.run(wappa_app.create_app())


# For uvicorn reload: "echo_project.main:fastapi_app"
fastapi_app = create_fastapi_app()


def main():
    """Main echo project function."""
    print(f"🚀 Wappa v{__version__} - Echo Project")
    print("=" * 60)
    print()
    print("🎯 **ECHO PROJECT DEMONSTRATION:**")
    print("  • Comprehensive message echoing with metadata")
    print("  • Interactive buttons with state management")
    print("  • Interactive lists with media options")
    print("  • CTA buttons and location requests")
    print("  • User data caching and state management")
    print("  • Media echo using WhatsApp media IDs")
    print()
    print("📋 Configuration Check:")
    print(f"  • Access Token: {'✅ Set' if settings.wp_access_token else '❌ Missing'}")
    print(f"  • Phone ID: {settings.wp_phone_id if settings.wp_phone_id else '❌ Missing'}")
    print(f"  • Business ID: {'✅ Set' if settings.wp_bid else '❌ Missing'}")
    print(f"  • Redis URL: {'✅ Set' if settings.has_redis else '❌ Missing'}")
    print()

    if not settings.has_redis:
        print("❌ Redis URL not configured! Set REDIS_URL in your .env file")
        return

    print("🧪 **DEMO FEATURES:**")
    print("  1. Send any message → Comprehensive echo with metadata")
    print("  2. Send '/button' → Interactive buttons with images")
    print("  3. Click buttons → Get special images based on selection")
    print("  4. Send '/list' → Interactive list with media options")
    print("  5. Select from list → Get media file (image/video/audio/document)")
    print("  6. Send '/cta' → Call-to-action button with URL")
    print("  7. Send '/location' → Request location sharing")
    print("  8. Send media files → Echo back with metadata")
    print("  9. Send location/contact → Echo back with analysis")
    print("  10. Check logs for comprehensive processing details")
    print()
    print("💾 **REDIS CACHE ARCHITECTURE:**")
    print("  • state_cache: Interactive button/list states (TTL 10min)")
    print("  • user_cache: User profile data (TTL 24hr)")
    print("  • Tenant isolation through dependency injection")
    print("  • Automatic cleanup of expired states")
    print()

    print("🔧 **ECHO PROJECT ARCHITECTURE:**")
    print("  • Master Handler: echo_handler.py (WappaEventHandler)")
    print("  • State Management: Redis-based with TTL")
    print("  • Logic Modules: 17 separate modules for different features")
    print("  • Interactive Features: Buttons, lists, CTA, location")
    print("  • Media Processing: Echo using WhatsApp media IDs")
    print("  • Layered Processing: State → Activation → Echo")
    print()

    print("🌐 Starting Echo Project server...")
    print("💡 Press CTRL+C to stop the server")
    print("=" * 60)

    try:
        # Create the app with unified architecture
        app = create_wappa_app_with_redis()

        # Start the server (auto-reload enabled in DEV environment)
        app.run()

    except KeyboardInterrupt:
        print("\n👋 Echo Project stopped by user")
    except Exception as e:
        print(f"\n❌ Server error: {e}")
    finally:
        print("🏁 Echo Project completed")


if __name__ == "__main__":
    main()