"""
PubSub Example Event Handler - WappaEventHandler demonstrating all PubSub events.

This handler demonstrates how RedisPubSubPlugin publishes notifications for:
- incoming_message: Published when this handler receives messages
- bot_reply: Published when this handler sends replies via self.messenger
- status_change: Published when delivery/read receipts arrive
- outgoing_message: Published when messages are sent via API routes

The handler automatically replies to messages, triggering the bot_reply event.
"""

from typing import TYPE_CHECKING

from wappa import WappaEventHandler
from wappa.webhooks import ErrorWebhook, IncomingMessageWebhook, StatusWebhook

if TYPE_CHECKING:
    from wappa.domain.events.api_message_event import APIMessageEvent


class PubSubExampleHandler(WappaEventHandler):
    """
    WappaEventHandler that demonstrates all PubSub event types.

    Events triggered by this handler:
    - Every message received triggers 'incoming_message' PubSub event
    - Every reply sent triggers 'bot_reply' PubSub event
    - Delivery receipts trigger 'status_change' PubSub event
    - API-sent messages trigger 'outgoing_message' PubSub event
    """

    def __init__(self):
        """Initialize the PubSub example handler."""
        super().__init__()
        self._message_count = 0
        self.logger.info("PubSubExampleHandler initialized")

    async def process_message(self, webhook: IncomingMessageWebhook) -> None:
        """
        Process incoming messages and send auto-reply.

        This method:
        1. Receives the message (triggers 'incoming_message' PubSub event via plugin)
        2. Sends a reply via self.messenger (triggers 'bot_reply' PubSub event)

        Args:
            webhook: Incoming message webhook to process
        """
        self._message_count += 1

        try:
            # Get user info
            user_id = webhook.user.user_id if webhook.user else "unknown"
            message_text = webhook.get_message_text() or "[NON-TEXT MESSAGE]"
            message_type = webhook.get_message_type_name()

            self.logger.info(
                f"[INCOMING] #{self._message_count} from {user_id}: "
                f"{message_text[:50]}... (type={message_type})"
            )

            # Send auto-reply - this triggers 'bot_reply' PubSub event!
            reply_text = (
                f"PubSub Demo #{self._message_count}\n\n"
                f"Received your {message_type} message!\n\n"
                f"Check your redis-cli subscriber to see:\n"
                f"1. 'incoming_message' event (your message)\n"
                f"2. 'bot_reply' event (this reply)\n"
                f"3. 'status_change' events (delivery status)"
            )

            result = await self.messenger.send_text(
                recipient=user_id,
                text=reply_text,
            )

            if result.success:
                self.logger.info(
                    f"[BOT_REPLY] Sent reply to {user_id} "
                    f"(message_id={result.message_id})"
                )
            else:
                self.logger.error(f"[BOT_REPLY] Failed to send reply: {result.error}")

        except Exception as e:
            self.logger.error(f"Error processing message: {e}", exc_info=True)

    async def process_status(self, webhook: StatusWebhook) -> None:
        """
        Process status webhooks (delivery/read receipts).

        Status events automatically trigger 'status_change' PubSub notifications
        via the RedisPubSubPlugin.

        Args:
            webhook: Status webhook containing delivery status information
        """
        try:
            status_value = webhook.status.value
            recipient = webhook.recipient_id
            message_id = webhook.message_id

            self.logger.info(
                f"[STATUS] {status_value.upper()} for message {message_id[:20]}... "
                f"to {recipient}"
            )

        except Exception as e:
            self.logger.error(f"Error processing status webhook: {e}", exc_info=True)

    async def process_error(self, webhook: ErrorWebhook) -> None:
        """
        Process error webhooks from WhatsApp Business API.

        Args:
            webhook: Error webhook containing error information
        """
        try:
            error_count = webhook.get_error_count()
            primary_error = webhook.get_primary_error()

            self.logger.error(
                f"[ERROR] WhatsApp API error: {error_count} errors, "
                f"primary: {primary_error.error_code} - {primary_error.error_title}"
            )

        except Exception as e:
            self.logger.error(f"Error processing error webhook: {e}", exc_info=True)

    async def process_api_message(self, event: "APIMessageEvent") -> None:
        """
        Process API-sent message events.

        API messages sent via REST routes automatically trigger 'outgoing_message'
        PubSub notifications via the RedisPubSubPlugin.

        Test with:
            curl -X POST http://localhost:8000/api/whatsapp/messages/text \\
              -H "Content-Type: application/json" \\
              -d '{"recipient": "5511999887766", "text": "Hello from API!"}'

        Args:
            event: APIMessageEvent containing message details
        """
        try:
            status = "SUCCESS" if event.response_success else "FAILED"
            self.logger.info(
                f"[API_MESSAGE] {status} - {event.message_type} to {event.recipient} "
                f"(id={event.message_id})"
            )

            if not event.response_success:
                self.logger.warning(f"[API_MESSAGE] Error: {event.response_error}")

        except Exception as e:
            self.logger.error(f"Error processing API message event: {e}", exc_info=True)

    def __str__(self) -> str:
        """String representation of the handler."""
        return f"PubSubExampleHandler(messages_processed={self._message_count})"
