"""Default handler for status webhooks."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

from wappa.core.logging.logger import get_logger
from wappa.webhooks import (
    StatusWebhook,
)

from ._stats import _LOGGER_NAME, LogLevel, StatusLogStrategy, _StatusStats


class DefaultStatusHandler:
    """
    Default handler for Platform status webhooks.

    Provides configurable logging strategies for message delivery status updates.
    Users can customize the logging strategy or extend this class for custom behavior.
    """

    def __init__(
        self,
        log_strategy: StatusLogStrategy = StatusLogStrategy.IMPORTANT_ONLY,
        log_level: LogLevel = LogLevel.INFO,
    ) -> None:
        """
        Initialize the default status handler.

        Args:
            log_strategy: Strategy for which status updates to log
            log_level: Base log level for status updates
        """
        self.log_strategy = log_strategy
        self.log_level = log_level
        self.logger = get_logger(_LOGGER_NAME)

        # Track status statistics
        self._stats = _StatusStats()

    async def handle_status(self, webhook: StatusWebhook) -> dict[str, Any]:
        """
        Handle a status webhook with configurable logging.

        Args:
            webhook: StatusWebhook instance containing status information

        Returns:
            Dictionary with handling results and statistics
        """
        self._stats.total_processed += 1
        self._stats.last_processed = datetime.now(UTC)

        # Update status-specific counters
        status_value = webhook.status.value.lower()
        if status_value == "sent":
            self._stats.sent += 1
        elif status_value == "delivered":
            self._stats.delivered += 1
        elif status_value == "read":
            self._stats.read += 1
        elif status_value == "played":
            self._stats.played += 1
        elif status_value == "failed":
            self._stats.failed += 1
        elif status_value == "deleted":
            self._stats.deleted += 1

        # Apply logging strategy
        should_log = self._should_log_status(webhook)

        if should_log:
            log_message = self._format_status_message(webhook)
            log_method = self._get_log_method(self.log_level)

            # For failed messages, always use error level
            if status_value == "failed":
                self.logger.error(log_message)
            else:
                log_method(log_message)

        return {
            "success": True,
            "action": "status_logged" if should_log else "status_ignored",
            "handler": "DefaultStatusHandler",
            "message_id": webhook.message_id,
            "status": webhook.status.value,
            "recipient": webhook.recipient_id,
            "logged": should_log,
            "stats": asdict(self._stats),
        }

    def _should_log_status(self, webhook: StatusWebhook) -> bool:
        """Determine if status should be logged based on strategy."""
        if self.log_strategy == StatusLogStrategy.NONE:
            return False
        elif self.log_strategy == StatusLogStrategy.ALL:
            return True
        elif self.log_strategy == StatusLogStrategy.FAILURES_ONLY:
            return webhook.status.value.lower() in ["failed", "undelivered"]
        elif self.log_strategy == StatusLogStrategy.IMPORTANT_ONLY:
            return webhook.status.value.lower() in [
                "delivered",
                "failed",
                "read",
                "played",
                "deleted",
                "undelivered",
            ]

        return True  # Default to logging

    def _format_status_message(self, webhook: StatusWebhook) -> str:
        """Format status message for logging."""
        status_icon = self._get_status_icon(webhook.status.value)

        return (
            f"{status_icon} Status Update: {webhook.status.value} "
            f"(platform: {webhook.platform.value}, message: {webhook.message_id}"
            + (f", recipient: {webhook.recipient_id}" if webhook.recipient_id else "")
            + ")"
        )

    def _get_status_icon(self, status: str) -> str:
        """Get emoji icon for status."""
        icons = {
            "sent": "📤",
            "delivered": "✅",
            "read": "👁️",
            "played": "🔊",
            "failed": "❌",
            "deleted": "🗑️",
            "undelivered": "⚠️",
        }
        return icons.get(status.lower(), "📋")

    def _get_log_method(self, log_level: LogLevel) -> Callable[[str], None]:
        """Get the appropriate logger method for log level."""
        methods = {
            LogLevel.DEBUG: self.logger.debug,
            LogLevel.INFO: self.logger.info,
            LogLevel.WARNING: self.logger.warning,
            LogLevel.ERROR: self.logger.error,
        }
        return methods.get(log_level, self.logger.info)
