"""
Message History Score - Single Responsibility: Message logging and history management.

This module handles all message history operations including:
- Message logging to table cache
- Message history retrieval and formatting
- /HISTORY command processing
"""

from wappa.webhooks import IncomingMessageWebhook

from ..models.redis_demo_models import MessageLog
from ..utils.cache_utils import get_cache_ttl
from ..utils.message_utils import (
    extract_command_from_message,
    extract_user_data,
    format_message_history_display,
    sanitize_message_text,
)
from .constants import MESSAGE_HISTORY_TABLE
from .score_base import ScoreBase


class MessageHistoryScore(ScoreBase):
    """
    Handles message history logging and retrieval operations.

    Follows Single Responsibility Principle by focusing only
    on message history management.
    """

    async def can_handle(self, webhook: IncomingMessageWebhook) -> bool:
        """
        This score handles all messages for logging, plus /HISTORY command.

        Args:
            webhook: Incoming message webhook

        Returns:
            Always True since all messages should be logged
        """
        return True

    async def process(self, webhook: IncomingMessageWebhook) -> bool:
        """
        Process message logging and handle /HISTORY command.

        Args:
            webhook: Incoming message webhook

        Returns:
            True if processing was successful
        """
        if not await self.validate_dependencies():
            return False

        try:
            # Always log the message first
            await self._log_message(webhook)

            # Check if this is a /HISTORY command
            message_text = webhook.get_message_text()
            if message_text:
                command, _ = extract_command_from_message(message_text.strip())
                if command == "/HISTORY":
                    await self._handle_history_request(webhook)

            self._record_processing(success=True)
            return True

        except Exception as e:
            await self._handle_error(e, "message_history_processing")
            return False

    async def _log_message(self, webhook: IncomingMessageWebhook) -> None:
        """
        Log message to user's message history.

        Args:
            webhook: Incoming message webhook
        """
        try:
            user_data = extract_user_data(webhook)
            user_id = user_data["user_id"]
            tenant_id = user_data["tenant_id"]

            message_text = webhook.get_message_text()
            message_type = webhook.get_message_type_name()

            # ITableCache.get() requires (table_name, pkid, models=...)
            # Use user_id as the primary key for their message history
            message_log = await self.table_cache.get(
                MESSAGE_HISTORY_TABLE, user_id, models=MessageLog
            )

            if message_log:
                self.logger.debug(
                    f"📝 Found existing history for {user_id} "
                    f"({message_log.get_message_count()} messages)"
                )
            else:
                # Create new message history
                message_log = MessageLog(user_id=user_id, tenant_id=tenant_id)
                self.logger.info(f"📝 Creating new message history for {user_id}")

            # Add the new message to history
            message_content = sanitize_message_text(
                message_text or f"[{message_type.upper()} MESSAGE]"
            )
            message_log.add_message(message_content, message_type)

            # Store back to Redis with TTL
            # ITableCache.upsert() takes (table_name, pkid, data, ttl=...)
            ttl = get_cache_ttl("message")
            await self.table_cache.upsert(
                MESSAGE_HISTORY_TABLE, user_id, message_log.model_dump(), ttl=ttl
            )

            self.logger.info(
                f"📝 Message logged: {user_id} "
                f"(total: {message_log.get_message_count()} messages)"
            )

        except Exception as e:
            self.logger.error(f"Error logging message: {e}")
            raise

    async def _handle_history_request(self, webhook: IncomingMessageWebhook) -> None:
        """
        Handle /HISTORY command to show user's message history.

        Args:
            webhook: Incoming message webhook
        """
        try:
            user_data = extract_user_data(webhook)
            user_id = user_data["user_id"]

            # Get user's message history using ITableCache interface
            message_log = await self.table_cache.get(
                MESSAGE_HISTORY_TABLE, user_id, models=MessageLog
            )

            if message_log:
                # User has message history
                recent_messages = message_log.get_recent_messages(20)
                total_count = message_log.get_message_count()

                if recent_messages:
                    # Format history for display
                    history_text = format_message_history_display(
                        recent_messages, total_count, 20
                    )
                else:
                    history_text = "📚 Your message history is empty. Start chatting to build your history!"
            else:
                # No history found
                history_text = "📚 No message history found. This is your first message! Welcome! 👋"

            # Send history to user
            result = await self.messenger.send_text(
                recipient=user_id,
                text=history_text,
                reply_to_message_id=webhook.message.message_id,
            )

            if result.success:
                self.logger.info(f"✅ History sent to {user_id}")
            else:
                self.logger.error(f"❌ Failed to send history: {result.error}")

        except Exception as e:
            self.logger.error(f"Error handling history request: {e}")
            raise

    async def get_message_count(self, user_id: str) -> int:
        """
        Get message count for user (for other score modules).

        Args:
            user_id: User's phone number ID

        Returns:
            Number of messages from user, 0 if no history
        """
        try:
            message_log = await self.table_cache.get(
                MESSAGE_HISTORY_TABLE, user_id, models=MessageLog
            )
            return message_log.get_message_count() if message_log else 0
        except Exception as e:
            self.logger.error(f"Error getting message count for {user_id}: {e}")
            return 0
