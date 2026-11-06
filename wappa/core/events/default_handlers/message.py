"""Default handler for incoming message webhooks."""

from __future__ import annotations

import re

from wappa.core.logging.logger import ContextLogger, get_logger
from wappa.webhooks import (
    InboundMessageWebhook,
)

from ._stats import _LOGGER_NAME, LogLevel, MessageLogStrategy, _MessageStats


class DefaultMessageHandler:
    """
    Default handler for incoming message webhooks.

    Provides structured logging for incoming Platform messages with configurable
    strategies for content filtering, PII protection, and statistics tracking.

    This handler is designed to be core framework infrastructure - it runs automatically
    before user message processing to ensure comprehensive message logging and monitoring.
    """

    # Patterns for sensitive content detection
    _PHONE_PATTERN = re.compile(
        r"\b(?:\+?1[-.\s]?)?\(?([0-9]{3})\)?[-.\s]?([0-9]{3})[-.\s]?([0-9]{4})\b"
    )
    _EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
    _CREDIT_CARD_PATTERN = re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b")

    def __init__(
        self,
        log_strategy: MessageLogStrategy = MessageLogStrategy.SUMMARIZED,
        log_level: LogLevel = LogLevel.INFO,
        content_preview_length: int = 100,
        mask_sensitive_data: bool = True,
    ) -> None:
        """
        Initialize the default message handler.

        Args:
            log_strategy: Strategy for message logging (default: SUMMARIZED)
            log_level: Log level for message logging (default: INFO)
            content_preview_length: Max characters for content preview (default: 100)
            mask_sensitive_data: Whether to mask phone numbers, emails, etc. (default: True)
        """
        self.log_strategy = log_strategy
        self.log_level = log_level
        self.content_preview_length = content_preview_length
        self.mask_sensitive_data = mask_sensitive_data

        # Statistics tracking
        self._stats = _MessageStats()

    async def log_incoming_message(self, webhook: InboundMessageWebhook) -> None:
        """
        Log incoming message webhook with configured strategy.

        This is the main entry point called by the framework before user processing.

        Args:
            webhook: InboundMessageWebhook containing the message data
        """
        if self.log_strategy == MessageLogStrategy.NONE:
            return

        # Update statistics
        self._update_stats(webhook)

        # Get logger with inbox context
        webhook.inbox.get_inbox_key() if webhook.inbox else "unknown"
        logger = get_logger(_LOGGER_NAME)

        # Log based on strategy
        if self.log_strategy == MessageLogStrategy.STATS_ONLY:
            await self._log_stats_only(logger, webhook)
        elif self.log_strategy == MessageLogStrategy.SUMMARIZED:
            await self._log_summarized(logger, webhook)
        elif self.log_strategy == MessageLogStrategy.ALL:
            await self._log_full_detail(logger, webhook)
        elif self.log_strategy == MessageLogStrategy.FILTERED:
            await self._log_filtered(logger, webhook)

    async def post_process_message(self, webhook: InboundMessageWebhook) -> None:
        """
        Post-process message after user handling (optional hook for future features).

        Args:
            webhook: InboundMessageWebhook that was processed
        """
        # Future: Add post-processing logic like response time tracking,
        # conversation state updates, or user engagement metrics
        pass

    def _update_stats(self, webhook: InboundMessageWebhook) -> None:
        """Update internal statistics tracking."""
        self._stats.total_messages += 1

        # Track by message type
        message_type = webhook.get_message_type_name()
        self._stats.by_type[message_type] = self._stats.by_type.get(message_type, 0) + 1

        # Track by user
        user_id = webhook.user.user_id if webhook.user else "unknown"
        self._stats.by_user[user_id] = self._stats.by_user.get(user_id, 0) + 1

        # Track by inbox
        inbox_id = webhook.inbox.get_inbox_key() if webhook.inbox else "unknown"
        self._stats.by_inbox[inbox_id] = self._stats.by_inbox.get(inbox_id, 0) + 1

        # Check for sensitive content
        if self.mask_sensitive_data:
            content = webhook.get_message_text() or ""
            if any(
                pattern.search(content)
                for pattern in [
                    self._PHONE_PATTERN,
                    self._EMAIL_PATTERN,
                    self._CREDIT_CARD_PATTERN,
                ]
            ):
                self._stats.sensitive_content_detected += 1

    def _get_content_preview(self, webhook: InboundMessageWebhook) -> str:
        """Get masked content preview for logging."""
        content = webhook.get_message_text() or ""

        if self.mask_sensitive_data:
            # Mask sensitive patterns
            content = self._PHONE_PATTERN.sub("***-***-****", content)
            content = self._EMAIL_PATTERN.sub("***@***.***", content)
            content = self._CREDIT_CARD_PATTERN.sub("****-****-****-****", content)

        # Truncate to preview length
        if len(content) > self.content_preview_length:
            content = content[: self.content_preview_length] + "..."

        return content

    async def _log_stats_only(
        self, logger: ContextLogger, webhook: InboundMessageWebhook
    ) -> None:
        """Log only statistics summary."""
        if self._stats.total_messages % 10 == 0:  # Log every 10 messages
            logger.info(
                f"📊 Message Stats: {self._stats.total_messages} total, "
                f"Types: {dict(list(self._stats.by_type.items())[:3])}, "
                f"Active users: {len(self._stats.by_user)}"
            )

    async def _log_summarized(
        self, logger: ContextLogger, webhook: InboundMessageWebhook
    ) -> None:
        """Log summarized message information."""
        user_id = webhook.user.user_id if webhook.user else "unknown"
        message_type = webhook.get_message_type_name()
        content_preview = self._get_content_preview(webhook)

        # Create a concise but informative log entry
        logger.info(
            f"📥 Message from {user_id}: {message_type}"
            + (f" - '{content_preview}'" if content_preview else "")
        )

    async def _log_full_detail(
        self, logger: ContextLogger, webhook: InboundMessageWebhook
    ) -> None:
        """Log full message details."""
        user_id = webhook.user.user_id if webhook.user else "unknown"
        inbox_id = webhook.inbox.get_inbox_key() if webhook.inbox else "unknown"
        message_type = webhook.get_message_type_name()
        content_preview = self._get_content_preview(webhook)

        logger.info(
            f"📥 Full Message Details: User={user_id}, Inbox={inbox_id}, "
            f"Type={message_type}, Content='{content_preview}'"
        )

    async def _log_filtered(
        self, logger: ContextLogger, webhook: InboundMessageWebhook
    ) -> None:
        """Log with custom filtering logic (can be extended by users)."""
        message_type = webhook.get_message_type_name()

        # Default filtering: log only text messages and interactive responses
        if message_type.lower() in ["text", "interactive", "button"]:
            await self._log_summarized(logger, webhook)
