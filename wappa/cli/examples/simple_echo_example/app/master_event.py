"""
Simple Echo Master Event Handler

A simplified, clean event handler that demonstrates basic echo functionality
following the same patterns as the redis_cache_example but without the complexity.

This handler shows:
- Clean WappaEventHandler implementation
- Simple message echoing
- Multi-message-type support
- Proper logging and error handling
"""

from wappa import WappaEventHandler
from wappa.core.logging import get_logger
from wappa.webhooks import ErrorWebhook, IncomingMessageWebhook, StatusWebhook

logger = get_logger(__name__)


class SimpleEchoHandler(WappaEventHandler):
    """
    Simple echo handler that replies to all messages.

    This demonstrates the basic WappaEventHandler pattern without
    the complexity of score modules or caching systems.
    """

    def __init__(self):
        """Initialize the simple echo handler."""
        super().__init__()
        self._message_count = 0
        logger.info("🔄 SimpleEchoHandler initialized - ready to echo messages")

    async def process_message(self, webhook: IncomingMessageWebhook) -> None:
        """
        Process incoming messages with simple echo functionality.

        Args:
            webhook: Incoming message webhook to process
        """

        # Validate dependencies are properly injected
        if not self.validate_dependencies():
            logger.error(
                "❌ Dependencies not properly injected - cannot process message"
            )
            return

        self._message_count += 1

        user_id = webhook.user.user_id
        message_text = webhook.get_message_text()
        message_type = webhook.get_message_type_name()
        message_id = webhook.message.message_id

        logger.info(f"📝 Message #{self._message_count}: {message_type} from {user_id}")

        try:
            # Mark message as read with typing indicator
            await self.messenger.mark_as_read(message_id=message_id, typing=True)

            # Handle different message types
            await self._handle_message_by_type(
                webhook, user_id, message_text, message_type
            )

        except Exception as e:
            logger.error(f"❌ Error processing message: {e}", exc_info=True)

    async def _handle_message_by_type(
        self,
        webhook: IncomingMessageWebhook,
        user_id: str,
        message_text: str,
        message_type: str,
    ) -> None:
        """Handle message based on its type."""

        try:
            if message_type.lower() == "text":
                await self._handle_text_message(webhook, user_id, message_text)
            elif message_type.lower() in [
                "image",
                "video",
                "audio",
                "document",
                "sticker",
            ]:
                await self._handle_media_message(webhook, user_id, message_type)
            elif message_type.lower() == "location":
                await self._handle_location_message(webhook, user_id)
            elif message_type.lower() == "contacts":
                await self._handle_contact_message(webhook, user_id)
            else:
                await self._handle_other_message(webhook, user_id, message_type)

        except Exception as e:
            logger.error(f"❌ Error handling {message_type} message: {e}")

    async def _handle_text_message(
        self, webhook: IncomingMessageWebhook, user_id: str, message_text: str
    ) -> None:
        """Handle text messages with simple echo."""

        logger.info(f"💬 Echoing text: '{message_text}'")

        # Create echo response
        echo_response = f"🔄 Echo: {message_text}"

        # Add some metadata for the first few messages
        if self._message_count <= 3:
            echo_response += (
                f"\n\n📊 Message #{self._message_count} processed successfully!"
            )
            if self._message_count == 1:
                echo_response += "\n👋 Welcome to the Simple Echo Example!"

        # Send echo response
        result = await self.messenger.send_text(
            recipient=user_id,
            text=echo_response,
            reply_to_message_id=webhook.message.message_id,
        )

        if result.success:
            logger.info(f"✅ Text echo sent successfully: {result.message_id}")
        else:
            logger.error(f"❌ Text echo failed: {result.error}")

    async def _handle_media_message(
        self, webhook: IncomingMessageWebhook, user_id: str, message_type: str
    ) -> None:
        """Handle media messages."""

        logger.info(f"🎬 Processing {message_type} message")

        response = f"📁 {message_type.title()} received! Simple echo doesn't download media, but message was processed successfully.\n\n📊 Total messages: {self._message_count}"

        result = await self.messenger.send_text(
            recipient=user_id,
            text=response,
            reply_to_message_id=webhook.message.message_id,
        )

        if result.success:
            logger.info(f"✅ {message_type} response sent: {result.message_id}")
        else:
            logger.error(f"❌ {message_type} response failed: {result.error}")

    async def _handle_location_message(
        self, webhook: IncomingMessageWebhook, user_id: str
    ) -> None:
        """Handle location messages."""

        logger.info("📍 Processing location message")

        response = f"📍 Location received! Thanks for sharing your location.\n\n📊 Total messages: {self._message_count}"

        result = await self.messenger.send_text(
            recipient=user_id,
            text=response,
            reply_to_message_id=webhook.message.message_id,
        )

        if result.success:
            logger.info(f"✅ Location response sent: {result.message_id}")
        else:
            logger.error(f"❌ Location response failed: {result.error}")

    async def _handle_contact_message(
        self, webhook: IncomingMessageWebhook, user_id: str
    ) -> None:
        """Handle contact messages."""

        logger.info("👥 Processing contact message")

        response = f"👥 Contact shared! Thanks for the contact information.\n\n📊 Total messages: {self._message_count}"

        result = await self.messenger.send_text(
            recipient=user_id,
            text=response,
            reply_to_message_id=webhook.message.message_id,
        )

        if result.success:
            logger.info(f"✅ Contact response sent: {result.message_id}")
        else:
            logger.error(f"❌ Contact response failed: {result.error}")

    async def _handle_other_message(
        self, webhook: IncomingMessageWebhook, user_id: str, message_type: str
    ) -> None:
        """Handle other message types."""

        logger.info(f"❓ Processing unsupported message type: {message_type}")

        response = f"📨 {message_type.title()} message received! This message type is not fully supported yet, but was processed successfully.\n\n📊 Total messages: {self._message_count}"

        result = await self.messenger.send_text(
            recipient=user_id,
            text=response,
            reply_to_message_id=webhook.message.message_id,
        )

        if result.success:
            logger.info(f"✅ {message_type} response sent: {result.message_id}")
        else:
            logger.error(f"❌ {message_type} response failed: {result.error}")

    async def process_status(self, webhook: StatusWebhook) -> None:
        """Process status webhooks with simple logging."""

        status_value = webhook.status.value
        recipient = webhook.recipient_id

        logger.info(
            f"📊 Status update: {status_value.upper()} for recipient {recipient}"
        )

    async def process_error(self, webhook: ErrorWebhook) -> None:
        """Process error webhooks with simple logging."""

        error_count = webhook.get_error_count()
        primary_error = webhook.get_primary_error()

        logger.error(
            f"🚨 Platform error: {error_count} errors, "
            f"primary: {primary_error.error_code} - {primary_error.error_title}"
        )
