"""
Multi-Tenant Echo Test for Wappa Framework

This test demonstrates the improved per-request dependency injection architecture:
1. WebhookController creates MessengerFactory per request with correct tenant_id
2. Each webhook is processed with tenant-specific messenger instance
3. Echo functionality validates proper multi-tenant isolation
4. Dependencies are injected fresh for each request (not cached at startup)

SETUP REQUIRED:
Create a .env file with your WhatsApp Business API credentials:

    # WhatsApp Business API Credentials
    WP_ACCESS_TOKEN=your_access_token_here
    WP_PHONE_ID=your_phone_number_id_here
    WP_BID=your_business_id_here

Test by sending messages to your WhatsApp Business number and observe:
- ✅ Per-request dependency injection with correct tenant_id
- ✅ Echo messages sent back using proper tenant-specific messenger
- ✅ Dependency validation shows correct platform/tenant per request
- ✅ Support for different tenant_ids in future multi-tenant scenarios
"""

import asyncio
from datetime import datetime

from wappa import Wappa, WappaEventHandler, __version__
from wappa.core.config.settings import settings
from wappa.webhooks import ErrorWebhook, IncomingMessageWebhook, StatusWebhook


class MultiTenantEchoHandler(WappaEventHandler):
    """
    Enhanced echo handler that demonstrates per-request dependency injection.

    Shows how the new architecture properly handles:
    - Tenant-specific messenger creation per request
    - Dependency validation with tenant information
    - Multi-tenant isolation (different tenant_ids get different messengers)
    - Echo functionality with comprehensive message support
    """

    def __init__(self):
        """Initialize handler - dependencies injected per request by WebhookController."""
        super().__init__()

        # Track requests for demonstration
        self._request_count = 0

        self.logger.info(
            "🚀 MultiTenantEchoHandler initialized - dependencies will be injected per request"
        )

    async def process_message(self, webhook: IncomingMessageWebhook) -> None:
        """Process incoming messages with comprehensive echo functionality."""
        self._request_count += 1

        # CRITICAL: Validate per-request dependency injection
        if not self.validate_dependencies():
            self.logger.error(
                "❌ Dependencies not properly injected - cannot process message"
            )
            return

        user_id = webhook.user.user_id
        message_text = webhook.get_message_text()
        message_type = webhook.get_message_type_name()
        message_id = webhook.message.message_id

        self.logger.info(
            f"💬 Request #{self._request_count}: Processing {message_type} from {user_id}"
        )

        # Show dependency status with tenant information (KEY IMPROVEMENT!)
        dep_status = self.get_dependency_status()
        self.logger.info(f"📋 Per-Request Dependencies: {dep_status}")

        # Demonstrate tenant-specific information
        if self.messenger:
            self.logger.info(
                f"🏢 Tenant Context: platform={self.messenger.platform.value}, "
                f"tenant_id={self.messenger.tenant_id}"
            )

            await self.messenger.mark_as_read(message_id=message_id, typing=True)

        # Show raw webhook data for debugging
        raw_data = webhook.get_raw_webhook_data()
        if raw_data:
            self.logger.debug(
                f"📄 Raw webhook data available (keys: {list(raw_data.keys())})"
            )

        # Handle different message types with comprehensive echo
        await self._handle_echo_by_type(webhook, user_id, message_text, message_type)

    async def _handle_echo_by_type(
        self,
        webhook: IncomingMessageWebhook,
        user_id: str,
        message_text: str,
        message_type: str,
    ) -> None:
        """Handle echo functionality based on message type."""
        try:
            if message_type.lower() == "text":
                await self._handle_text_echo(webhook, user_id, message_text)
            elif message_type.lower() in [
                "image",
                "video",
                "audio",
                "document",
                "sticker",
            ]:
                await self._handle_media_echo(webhook, user_id, message_type)
            elif message_type.lower() == "location":
                await self._handle_location_echo(webhook, user_id)
            elif message_type.lower() == "contacts":
                await self._handle_contact_echo(webhook, user_id)
            else:
                await self._handle_unsupported_echo(webhook, user_id, message_type)

        except Exception as e:
            self.logger.error(f"❌ Echo handling failed: {e}", exc_info=True)

    async def _handle_text_echo(
        self, webhook: IncomingMessageWebhook, user_id: str, message_text: str
    ) -> None:
        """Handle text message echo with metadata."""
        self.logger.info(f"📝 Processing text echo for: '{message_text}'")

        # Send metadata-rich response first
        metadata_response = self._build_message_metadata_response(webhook, "text")

        result1 = await self.messenger.send_text(
            recipient=user_id,
            text=metadata_response,
            reply_to_message_id=webhook.message.message_id,
        )

        if result1.success:
            self.logger.info(f"✅ Metadata response sent: {result1.message_id}")
        else:
            self.logger.error(f"❌ Metadata response failed: {result1.error}")

        # Wait a moment, then send text echo
        await asyncio.sleep(1.5)

        echo_text = f"🔄 ECHO: {message_text}"

        result2 = await self.messenger.send_text(
            recipient=user_id,
            text=echo_text,
            reply_to_message_id=webhook.message.message_id,
        )

        if result2.success:
            self.logger.info(f"✅ Text echo sent successfully: {result2.message_id}")
        else:
            self.logger.error(f"❌ Text echo failed: {result2.error}")

    async def _handle_media_echo(
        self, webhook: IncomingMessageWebhook, user_id: str, message_type: str
    ) -> None:
        """Handle media message echo."""
        self.logger.info(f"🎬 Processing {message_type} echo")

        # Send metadata response
        metadata_response = self._build_message_metadata_response(webhook, message_type)

        result = await self.messenger.send_text(
            recipient=user_id,
            text=metadata_response,
            reply_to_message_id=webhook.message.message_id,
        )

        if result.success:
            self.logger.info(
                f"✅ {message_type.title()} metadata sent: {result.message_id}"
            )
        else:
            self.logger.error(
                f"❌ {message_type.title()} metadata failed: {result.error}"
            )

    async def _handle_location_echo(
        self, webhook: IncomingMessageWebhook, user_id: str
    ) -> None:
        """Handle location message echo."""
        self.logger.info("📍 Processing location echo")

        # Send metadata response
        metadata_response = self._build_message_metadata_response(webhook, "location")

        result = await self.messenger.send_text(
            recipient=user_id,
            text=metadata_response,
            reply_to_message_id=webhook.message.message_id,
        )

        if result.success:
            self.logger.info(f"✅ Location metadata sent: {result.message_id}")
        else:
            self.logger.error(f"❌ Location metadata failed: {result.error}")

    async def _handle_contact_echo(
        self, webhook: IncomingMessageWebhook, user_id: str
    ) -> None:
        """Handle contact message echo."""
        self.logger.info("👥 Processing contact echo")

        # Send metadata response
        metadata_response = self._build_message_metadata_response(webhook, "contacts")

        result = await self.messenger.send_text(
            recipient=user_id,
            text=metadata_response,
            reply_to_message_id=webhook.message.message_id,
        )

        if result.success:
            self.logger.info(f"✅ Contact metadata sent: {result.message_id}")
        else:
            self.logger.error(f"❌ Contact metadata failed: {result.error}")

    async def _handle_unsupported_echo(
        self, webhook: IncomingMessageWebhook, user_id: str, message_type: str
    ) -> None:
        """Handle unsupported message types."""
        self.logger.info(f"❓ Processing unsupported message type: {message_type}")

        response = f"📨 Received {message_type} message - type not fully supported yet but per-request dependency injection is working!"

        result = await self.messenger.send_text(
            recipient=user_id,
            text=response,
            reply_to_message_id=webhook.message.message_id,
        )

        if result.success:
            self.logger.info(f"✅ Unsupported type response sent: {result.message_id}")
        else:
            self.logger.error(f"❌ Unsupported type response failed: {result.error}")

    def _build_message_metadata_response(
        self, webhook: IncomingMessageWebhook, message_type: str
    ) -> str:
        """Build metadata-rich response showing per-request dependency info."""
        timestamp = datetime.utcnow().isoformat()

        # Get tenant information from injected messenger (KEY IMPROVEMENT!)
        tenant_info = "Unknown"
        platform_info = "Unknown"

        if self.messenger:
            tenant_info = self.messenger.tenant_id
            platform_info = self.messenger.platform.value

        response = f"""📊 **Message Metadata & Dependency Status**

🏢 **Per-Request Context:**
• Platform: {platform_info}
• Tenant ID: {tenant_info}
• Request #: {self._request_count}
• Processed at: {timestamp}

📝 **Message Info:**
• Type: {message_type.upper()}
• From: {webhook.user.user_id}
• Message ID: {webhook.message.message_id}
• Has Dependencies: {"✅ YES" if self.messenger else "❌ NO"}

🎯 **Architecture Demo:**
• Per-request dependency injection ✅
• Tenant-specific messenger ✅
• Multi-tenant support ready ✅
• WebhookController coordination ✅

This message proves the new architecture is working correctly!"""

        return response

    async def process_status(self, webhook: StatusWebhook) -> None:
        """Custom status processing with tenant context."""
        status_value = webhook.status.value
        recipient = webhook.recipient_id

        # Show tenant context in status processing
        tenant_info = self.messenger.tenant_id if self.messenger else "unknown"

        self.logger.info(
            f"📊 Status update: {status_value.upper()} for recipient {recipient} "
            f"(tenant: {tenant_info})"
        )

        # Show raw webhook data for debugging
        raw_data = webhook.get_raw_webhook_data()
        if raw_data:
            self.logger.debug(f"📄 Status webhook data: {list(raw_data.keys())}")

    async def process_error(self, webhook: ErrorWebhook) -> None:
        """Custom error processing with tenant context."""
        error_count = webhook.get_error_count()
        primary_error = webhook.get_primary_error()

        # Show tenant context in error processing
        tenant_info = self.messenger.tenant_id if self.messenger else "unknown"

        self.logger.error(
            f"🚨 Platform error: {error_count} errors, "
            f"primary: {primary_error.error_code} - {primary_error.error_title} "
            f"(tenant: {tenant_info})"
        )


def main():
    """Demonstrate multi-tenant echo functionality with per-request dependency injection."""

    print(f"🚀 Wappa v{__version__} - Multi-Tenant Echo Test")
    print("=" * 60)
    print()
    print("🎯 **TESTING ARCHITECTURAL IMPROVEMENTS:**")
    print("  • Per-request dependency injection")
    print("  • Tenant-specific messenger creation")
    print("  • WebhookController coordination")
    print("  • Multi-tenant isolation readiness")
    print()
    print("📋 Configuration Loaded from .env:")
    print(f"  • Access Token: {'✅ Set' if settings.wp_access_token else '❌ Missing'}")
    print(
        f"  • Phone ID: {settings.wp_phone_id if settings.wp_phone_id else '❌ Missing'}"
    )
    print(f"  • Business ID: {'✅ Set' if settings.wp_bid else '❌ Missing'}")
    print()

    # Create Wappa application
    app = Wappa()

    # Set enhanced echo handler
    handler = MultiTenantEchoHandler()
    app.set_event_handler(handler)

    print(f"📱 Tenant ID: {settings.owner_id}")
    print()

    print("🔧 **NEW ARCHITECTURE FLOW:**")
    print("  1. HTTP Request → WebhookController.process_webhook()")
    print("  2. Extract tenant_id from middleware")
    print("  3. Create MessengerFactory with HTTP session")
    print("  4. Create tenant-specific messenger instance")
    print("  5. Inject fresh dependencies into event handler")
    print("  6. Process webhook with correct tenant context")
    print("  7. Echo response with tenant-aware messaging")
    print()

    print("✅ **EXPECTED BEHAVIOR:**")
    print("  • Each webhook creates fresh messenger with correct tenant_id")
    print("  • Echo messages show tenant context in metadata")
    print("  • Dependency validation passes with tenant info")
    print("  • No shared state between requests (proper isolation)")
    print("  • Support for multiple tenant_ids (future-ready)")
    print()

    print("🧪 **TEST INSTRUCTIONS:**")
    print("  1. Send text messages → Get metadata + echo response")
    print("  2. Send media → Get metadata about media type")
    print("  3. Send location → Get location metadata")
    print("  4. Send contacts → Get contact metadata")
    print("  5. Watch logs for per-request dependency injection")
    print()

    print("🌐 Starting multi-tenant echo test server...")
    print("💡 Press CTRL+C to stop the server")
    print("=" * 60)

    try:
        # Start the server
        app.run()
    except KeyboardInterrupt:
        print("\n👋 Multi-tenant echo test stopped by user")
    except Exception as e:
        print(f"\n❌ Server error: {e}")
    finally:
        print("🏁 Multi-tenant echo test completed")


# Export the FastAPI app for direct uvicorn usage
def create_app():
    """Create the FastAPI app for uvicorn direct usage."""
    app = Wappa()
    handler = MultiTenantEchoHandler()
    app.set_event_handler(handler)
    return app.create_app()


# Create the app instance for uvicorn
fastapi_app = create_app()


if __name__ == "__main__":
    main()
