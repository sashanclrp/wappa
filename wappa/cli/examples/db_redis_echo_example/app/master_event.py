"""
Master Event Handler - DB + Redis Integration (Orchestration Layer)

This is a thin orchestration layer that delegates to specialized handlers.
Follows the Single Responsibility Principle - handles ONLY routing and coordination.

Flow:
- Incoming message -> Route to appropriate handler
- Commands (/CLOSE, /HISTORY) -> CommandHandlers
- Regular messages -> MessageHandlers -> Cache in Redis -> Echo back
- On conversation close -> Persist to DB -> Clear Redis cache

Responsibilities:
1. Dependency validation and setup
2. Message routing (commands vs regular messages)
3. High-level error handling
4. Statistics tracking
"""

from __future__ import annotations

from wappa import WappaEventHandler
from wappa.webhooks import ErrorWebhook, IncomingMessageWebhook, StatusWebhook

from .handlers.command_handlers import (
    CommandHandlers,
    get_command_from_text,
    is_special_command,
)
from .handlers.message_handlers import MessageHandlers
from .utils.cache_utils import CacheHelper


class DBRedisExampleHandler(WappaEventHandler):
    """
    Event handler demonstrating Redis caching + DB persistence.

    Architecture:
    - Redis: Stores active conversation messages for fast access
    - Database: Persists closed conversations for long-term storage

    Commands:
    - Any message: Echoed back and cached in Redis
    - "/CLOSE": Closes conversation, persists to DB, clears Redis
    - "/HISTORY": Shows message count from Redis cache

    This class follows the Orchestration Pattern:
    - Thin layer (~200-300 lines) that coordinates handlers
    - Business logic delegated to specialized handlers
    - Clean separation of concerns
    """

    def __init__(self):
        """Initialize the DB + Redis example handler."""
        super().__init__()

        # Handler instances (initialized per request)
        self.cache_helper: CacheHelper | None = None
        self.message_handlers: MessageHandlers | None = None
        self.command_handlers: CommandHandlers | None = None

        # Statistics
        self._total_messages = 0
        self._successful_processing = 0
        self._failed_processing = 0
        self._commands_processed = 0

    async def process_message(self, webhook: IncomingMessageWebhook) -> None:
        """
        Process incoming message with Redis caching and DB persistence.

        Orchestration flow:
        1. Setup dependencies and validate
        2. Check for special commands -> CommandHandlers
        3. Process regular messages -> MessageHandlers

        Args:
            webhook: Incoming message webhook
        """
        self._total_messages += 1

        try:
            # 1. Setup dependencies
            if not await self._setup_dependencies():
                self._failed_processing += 1
                return

            # Get user ID and message text
            user_id = webhook.user.user_id
            message_text = webhook.get_message_text() or ""

            self.logger.info(f"Processing message from {user_id}: {message_text}")

            # 2. Check for special commands
            if is_special_command(message_text):
                command = get_command_from_text(message_text)
                result = await self.command_handlers.handle_command(webhook, command)

                if result.get("success"):
                    self._commands_processed += 1
                    self._successful_processing += 1
                    self.logger.info(f"Command {command} processed successfully")
                else:
                    self._failed_processing += 1
                    self.logger.error(
                        f"Command {command} failed: {result.get('error')}"
                    )
                return

            # 3. Process regular message
            result = await self.message_handlers.handle_message(webhook)

            if result.get("success"):
                self._successful_processing += 1
                self.logger.info(
                    f"Message processed successfully, "
                    f"count: {result.get('message_count', 0)}"
                )
            else:
                self._failed_processing += 1
                self.logger.error(f"Message processing failed: {result.get('error')}")
                await self._send_error_response(webhook)

        except Exception as e:
            self._failed_processing += 1
            self.logger.error(
                f"Critical error in message processing: {e}", exc_info=True
            )
            await self._send_error_response(webhook)

    async def process_status(self, webhook: StatusWebhook) -> None:
        """
        Process status webhooks from WhatsApp Business API.

        Args:
            webhook: StatusWebhook containing delivery status information
        """
        try:
            status_value = webhook.status.value
            recipient = webhook.recipient_id
            message_id = webhook.message_id

            self.logger.info(
                f"Message status: {status_value.upper()} "
                f"for {recipient} (msg: {message_id[:20]}...)"
            )

        except Exception as e:
            self.logger.error(f"Error processing status webhook: {e}", exc_info=True)

    async def process_error(self, webhook: ErrorWebhook) -> None:
        """
        Process error webhooks from WhatsApp Business API.

        Args:
            webhook: ErrorWebhook containing error information
        """
        try:
            error_count = webhook.get_error_count()
            primary_error = webhook.get_primary_error()

            self.logger.error(
                f"WhatsApp API error: {error_count} errors, "
                f"primary: {primary_error.error_code} - {primary_error.error_title}"
            )

            self._failed_processing += 1

        except Exception as e:
            self.logger.error(f"Error processing error webhook: {e}", exc_info=True)

    async def _setup_dependencies(self) -> bool:
        """
        Setup handler dependencies and validate state.

        Returns:
            True if setup successful, False otherwise
        """
        if not self.validate_dependencies():
            self.logger.error("Dependencies not properly injected")
            return False

        if not self.cache_factory:
            self.logger.error("Cache factory not available - Redis caching unavailable")
            return False

        try:
            # Initialize helper instances with required dependencies
            self.cache_helper = CacheHelper(self.cache_factory, self.db)
            self.message_handlers = MessageHandlers(
                self.messenger, self.cache_factory, self.logger
            )
            self.command_handlers = CommandHandlers(
                self.messenger, self.cache_factory, self.db, self.logger
            )

            self.logger.debug("Handler dependencies initialized successfully")
            return True

        except Exception as e:
            self.logger.error(f"Failed to setup dependencies: {e}", exc_info=True)
            return False

    async def _send_error_response(self, webhook: IncomingMessageWebhook) -> None:
        """
        Send user-friendly error response when processing fails.

        Args:
            webhook: Incoming message webhook
        """
        try:
            user_id = webhook.user.user_id
            await self.messenger.send_text(
                "Sorry, an error occurred while processing your message. "
                "Please try again.",
                user_id,
            )
        except Exception as e:
            self.logger.error(f"Failed to send error response: {e}")

    async def get_handler_statistics(self) -> dict:
        """
        Get handler processing statistics.

        Returns:
            Dictionary with processing statistics
        """
        total = max(1, self._total_messages)
        success_rate = (self._successful_processing / total) * 100

        return {
            "handler_info": {
                "name": "DBRedisExampleHandler",
                "description": "Redis caching + PostgreSQL persistence demo",
            },
            "processing_stats": {
                "total_messages": self._total_messages,
                "successful_processing": self._successful_processing,
                "failed_processing": self._failed_processing,
                "success_rate_percent": round(success_rate, 2),
                "commands_processed": self._commands_processed,
            },
            "supported_commands": ["/close", "/history"],
        }

    def __str__(self) -> str:
        """String representation of the handler."""
        total = max(1, self._total_messages)
        success_rate = (self._successful_processing / total) * 100
        return (
            f"DBRedisExampleHandler("
            f"messages={self._total_messages}, "
            f"success_rate={success_rate:.1f}%, "
            f"commands={self._commands_processed})"
        )


__all__ = ["DBRedisExampleHandler"]
