"""
Example demonstrating the improved webhook management system in Wappa v0.1.

This shows how webhooks flow from HTTP request to user event handler with
clean architecture, SOLID compliance, and proper design patterns.

SETUP REQUIRED:
Create a .env file with your WhatsApp Business API credentials:

    # WhatsApp Business API Credentials
    WP_ACCESS_TOKEN=your_access_token_here
    WP_PHONE_ID=your_phone_number_id_here
    WP_BID=your_business_id_here

The framework will automatically:
1. Load these credentials from .env
2. Generate webhook URLs using WP_PHONE_ID as tenant_id
3. Configure WhatsApp client with proper authentication
4. Route webhooks to your event handler methods
"""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path for direct script execution
sys.path.insert(0, str(Path(__file__).parent.parent))

from wappa import Wappa, WappaEventHandler, __version__, webhook_url_factory
from wappa.core.config.settings import settings
from wappa.webhooks import ErrorWebhook, IncomingMessageWebhook, StatusWebhook


class MyEventHandler(WappaEventHandler):
    """Example event handler showing the new Template Method pattern."""

    def __init__(self):
        """Initialize event handler and validate dependencies."""
        super().__init__()

        # Dependencies will be injected by Wappa framework during startup
        # We'll validate them in the first message processing

    async def process_message(self, webhook: IncomingMessageWebhook) -> None:
        """Process incoming WhatsApp messages (framework handles logging automatically)."""
        # Validate dependencies on first message (after injection should be complete)
        if not self.validate_dependencies():
            self.logger.error("❌ Cannot process message - missing dependencies")
            return

        user_id = webhook.user.user_id
        message_text = webhook.get_message_text()

        self.logger.info(f"💬 Processing message from {user_id}: {message_text}")

        # Show dependency status for debugging
        dep_status = self.get_dependency_status()
        self.logger.debug(f"📋 Dependency Status: {dep_status}")

        # Show raw webhook data for debugging
        raw_data = webhook.get_raw_webhook_data()
        if raw_data:
            self.logger.debug(
                f"📄 Raw webhook JSON available (keys: {list(raw_data.keys())})"
            )
            self.logger.debug(
                f"📄 MESSENGER Raw webhook JSON available (keys: {raw_data})"
            )

        # Echo the message back using the injected messenger
        if self.messenger:
            try:
                result = await self.messenger.send_text(
                    recipient=user_id, text=f"🔄 Echo: {message_text}"
                )

                if result.success:
                    self.logger.info(
                        f"✅ Echo sent successfully (msg_id: {result.message_id})"
                    )
                else:
                    self.logger.error(f"❌ Failed to send echo: {result.error}")

            except Exception as e:
                self.logger.error(
                    f"❌ Exception sending echo message: {e}", exc_info=True
                )
        else:
            self.logger.warning("⚠️  Messenger not available - cannot send echo")

    # Optional: Custom status processing (framework handles logging automatically)
    async def process_status(self, webhook: StatusWebhook) -> None:
        """Custom status processing - called after framework logging."""
        self.logger.info(f"📊 Custom status processing: {webhook.status.value}")

        # Show raw webhook data for debugging
        raw_data = webhook.get_raw_webhook_data()
        if raw_data:
            self.logger.debug(
                f"📄 Raw status webhook JSON available (keys: {list(raw_data.keys())})"
            )
            self.logger.debug(f"📄 Raw webhook JSON available (keys: {raw_data})")

        # Example: Track delivery rates for business metrics
        if webhook.status.value == "delivered":
            self.logger.info(
                "✅ Message successfully delivered - updating delivery metrics"
            )
        elif webhook.status.value == "failed":
            self.logger.error("❌ Message failed - investigating delivery issue")

    # Optional: Custom error processing (framework handles logging and escalation automatically)
    async def process_error(self, webhook: ErrorWebhook) -> None:
        """Custom error processing - called after framework logging and escalation."""
        error_count = webhook.get_error_count()
        primary_error = webhook.get_primary_error()

        self.logger.error(
            f"🚨 Custom error processing: {error_count} errors, primary: {primary_error.error_code}"
        )

        # Show raw webhook data for debugging
        raw_data = webhook.get_raw_webhook_data()
        if raw_data:
            self.logger.debug(
                f"📄 Raw error webhook JSON available (keys: {list(raw_data.keys())})"
            )
            self.logger.debug(f"📄 Raw webhook JSON available (keys: {raw_data})")

        # Example: Custom business logic for specific error types
        if primary_error.error_code == 131047:  # Rate limit error
            self.logger.warning(
                "⏳ Rate limit detected - implementing backoff strategy"
            )
        elif primary_error.error_code == 131026:  # Message undeliverable
            self.logger.warning("📧 Message undeliverable - adding to retry queue")


def create_wappa_app():
    """Create and configure the Wappa application."""
    # 1. Create Wappa application
    app = Wappa()

    # 2. Set event handler
    handler = MyEventHandler()
    app.set_event_handler(handler)

    return app

# Export the app for uvicorn auto-reload support
app = create_wappa_app()



def main():
    """Demonstrate the complete webhook management flow."""

    print(f"🚀 Wappa v{__version__} - Webhook Management Demo")
    print("=" * 50)
    print()
    print("📋 Configuration Loaded from .env:")
    print(f"  • Access Token: {'✅ Set' if settings.wp_access_token else '❌ Missing'}")
    print(
        f"  • Phone ID: {settings.wp_phone_id if settings.wp_phone_id else '❌ Missing'}"
    )
    print(f"  • Business ID: {'✅ Set' if settings.wp_bid else '❌ Missing'}")
    print()

    # Use the exported app instance

    # 3. Webhook URL is now automatically displayed during server startup
    print(
        f"📱 Using Phone ID: {settings.owner_id}"
    )  # Show which phone ID is being used
    print("🔗 Webhook URL will be displayed when server starts")
    print()

    # 4. Show supported platforms
    platforms = webhook_url_factory.get_supported_platforms()
    print("🌐 Supported Platforms:")
    for platform_name, details in platforms.items():
        print(f"  • {platform_name.upper()}: {details['webhook_pattern']}")
    print()

    # 5. Show webhook processing flow
    print("🔄 Enhanced Webhook Processing Flow:")
    print("  1. HTTP Request → OwnerMiddleware → extract owner_id")
    print("  2. WebhookController → validate platform + tenant")
    print("  3. ProcessorFactory → detect platform + create UniversalWebhook")
    print("  4. WappaEventDispatcher → route to event handler method")
    print("  5. Framework Logging → DefaultMessageHandler logs message details")
    print("  6. User Processing → MyEventHandler.process_message() business logic")
    print("  7. Status/Error Logging → DefaultStatusHandler/DefaultErrorHandler")
    print("  8. Response → {'status': 'accepted'} with comprehensive logging")
    print()

    print("✅ Enhanced Webhook Management System Ready!")
    print("📝 New Architecture Features:")
    print("  • 🗂️  Organized Events Module (core/events/)")
    print("  • 🏗️  Template Method Pattern for all webhook types")
    print("  • 📊 Built-in Message Logging (non-optional framework feature)")
    print("  • 🔧 Configurable Default Handlers for all webhook types")
    print(
        "  • 🎯 Separate user processing methods (process_message, process_status, process_error)"
    )
    print("  • 🛡️  PII masking and content filtering in message logs")
    print("  • 📈 Comprehensive statistics tracking")
    print("  • ⚡ Production-ready logging strategies")
    print("  • 🤖 Automatic Dependency Injection with Strategy Pattern")
    print("  • 💬 Working Messenger Integration (Echo functionality enabled!)")
    print()

    print("📊 Built-in Logging Features:")
    print("  • Message logging with content preview and PII masking")
    print("  • Status tracking with delivery metrics")
    print("  • Error escalation with configurable thresholds")
    print("  • Statistics collection by user, tenant, and message type")
    print()

    print("🤖 Dependency Injection Features:")
    print("  • Strategy Pattern: Automatic platform detection (WhatsApp)")
    print("  • MessengerFactory: Creates configured WhatsAppMessenger instances")
    print("  • Async Initialization: Dependencies injected during app startup")
    print("  • Validation: Runtime checks for proper dependency injection")
    print("  • Cache Factory: Placeholder for future persistence layer")
    print("  • Multi-tenant: Support for multiple WhatsApp Business accounts")
    print()

    print("🌐 Starting server on http://localhost:8000")
    print("💡 Press CTRL+C to stop the server")
    print("🔗 Health check: GET http://localhost:8000/health")
    print("=" * 50)
    print("🔄 Recommended ways to run:")
    print("   • Development: python examples/webhook_usage.py (auto-reload enabled in DEV)")
    print("   • Manual reload: uvicorn examples.webhook_usage:fastapi_app --reload")
    print("   • Production: Set ENVIRONMENT=PROD in .env (auto-reload disabled)")
    print()

    try:
        # Start the server - this will block and keep running
        # Auto-reload is automatically enabled in DEV environment
        app.run(port=8004)
    except KeyboardInterrupt:
        print("\n👋 Server stopped by user")
    except Exception as e:
        print(f"\n❌ Server error: {e}")
    finally:
        print("🏁 Webhook demo completed")


# Auto-reload Development Setup:
# 1. Direct Python: python examples/webhook_usage.py (simple, no auto-reload)
# 2. Uvicorn reload: uvicorn examples.webhook_usage:fastapi_app --reload (auto-reload enabled)
#
# The fastapi_app export uses thread-based lazy loading to avoid asyncio event loop conflicts
# in uvicorn's subprocess reloader environment.


if __name__ == "__main__":
    main()
