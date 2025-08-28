"""
Echo Project for Wappa Framework - SIMPLIFIED VERSION

This example demonstrates the NEW simplified way to run Wappa apps in development mode.
No more complex create_fastapi_app() boilerplate needed!

A comprehensive WhatsApp echo system demonstrating all features of the Wappa framework.
This project replicates the complete echo_test_event functionality using Wappa's unified architecture.

SETUP REQUIRED:
1. Create a .env file with your WhatsApp Business API credentials:
    WP_ACCESS_TOKEN=your_access_token_here
    WP_PHONE_ID=your_phone_number_id_here
    WP_BID=your_business_id_here

2. Set up Redis:
    REDIS_URL=redis://localhost:6379

DEMO FEATURES:
- Comprehensive message echoing with metadata extraction
- Interactive buttons with state management (10min TTL)
- Interactive lists with media options (10min TTL) 
- CTA buttons with URL links (stateless)
- Location request functionality (stateless)
- User data caching (24hr TTL)
- Media echo using WhatsApp media IDs
- State management with Redis cache
- Clean layered processing: State → Activation → Echo

COMMANDS TO TEST:
- Send any message → Comprehensive echo with metadata
- Send '/button' → Interactive buttons demo with images
- Send '/list' → Interactive list with media options
- Send '/cta' → Call-to-action button demo
- Send '/location' → Location request demo
- Send media files → Echo back with comprehensive metadata
- Send location/contact → Echo back with analysis

DEVELOPMENT MODES:
1. Direct Python: python main.py (uses settings.is_development for mode)
2. FastAPI-style: uvicorn main:app.asgi --reload (clean, no boilerplate)  
3. Wappa CLI: wappa dev main.py (batteries-included convenience)

The new .asgi property approach eliminates all threading complexity!
"""


# Import our demo handler (handle both direct run and CLI execution)
import sys
from pathlib import Path

# Add the example directory to Python path for local imports
example_dir = Path(__file__).parent
if str(example_dir) not in sys.path:
    sys.path.insert(0, str(example_dir))

from echo_handler import EchoProjectHandler

# Import from the installed wappa package
from wappa import Wappa, __version__
from wappa.core.config.settings import settings


# ============================================================================
# SIMPLIFIED WAPPA SETUP - NO COMPLEX BOILERPLATE NEEDED!
# ============================================================================

# Create Wappa instance at module level (required for auto-reload)
app = Wappa(cache="redis")
handler = EchoProjectHandler()
app.set_event_handler(handler)

def main():
    """Main demo function."""
    print(f"🚀 Wappa v{__version__} - Echo Project (SIMPLIFIED)")
    print("=" * 60)
    print()
    print("🎯 **COMPREHENSIVE ECHO DEMONSTRATION:**")
    print("  • Message Echo: All message types with metadata")
    print("  • Interactive Buttons: State management with images")
    print("  • Interactive Lists: Media options with samples")
    print("  • CTA Buttons: External link integration")
    print("  • Location Requests: Location sharing prompts")
    print("  • User Storage: 24-hour profile caching")
    print("  • Media Processing: WhatsApp media ID echo")
    print("  • State Management: Redis-based with TTL")
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
    print("  2. Send '/button' → Interactive buttons with image responses")
    print("  3. Click buttons → Get special images based on selection")
    print("  4. Send '/list' → Interactive list with media options")
    print("  5. Select from list → Get sample media files")
    print("  6. Send '/cta' → Call-to-action button with external URL")
    print("  7. Send '/location' → Location sharing request")
    print("  8. Send media files → Echo back with comprehensive metadata")
    print("  9. Send location/contact → Echo back with detailed analysis")
    print("  10. Check logs for processing details and cache statistics")
    print()
    print("💾 **REDIS CACHE ARCHITECTURE:**")
    print("  • state_cache (db1): Interactive session states with TTL 10min")
    print("  • user_cache (db0): User profiles with TTL 24hr")
    print("  • Automatic cleanup of expired states and user data")
    print("  • Tenant isolation through dependency injection")
    print()

    print("🔧 **ECHO PROJECT ARCHITECTURE:**")
    print("  • Master Handler: echo_handler.py (extends WappaEventHandler)")
    print("  • Components: state_manager, interactive_builder, media_processor")
    print("  • Logic Modules: 20 separate modules for different features")
    print("  • Layered Processing: State → Activation → Echo → Validation")
    print("  • Media Processing: Echo using WhatsApp media IDs")
    print("  • Interactive Features: Buttons, lists, CTA, location with state management")
    print()

    print("🌐 Starting Echo Project server...")
    print("💡 Press CTRL+C to stop the server")
    print()
    print("✨ **NEW FASTAPI-STYLE APPROACH:**")
    print("  • No complex create_fastapi_app() function needed!")
    print("  • Clean .asgi property for uvicorn reload compatibility")
    print("  • Just app.run() OR uvicorn main:app.asgi --reload")
    print("  • Lifespan hooks handle async initialization")
    print("=" * 60)

    try:
        print("✅ Wappa created with automatic Redis plugin integration")
        print("✅ Echo Project handler configured with comprehensive logic")

        # THAT'S IT! No complex ASGI export functions needed!
        # Framework handles everything automatically
        app.run()

    except KeyboardInterrupt:
        print("\n👋 Echo Project stopped by user")
    except Exception as e:
        print(f"\n❌ Server error: {e}")
    finally:
        print("🏁 Echo Project completed")


if __name__ == "__main__":
    main()