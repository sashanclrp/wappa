"""Default handler for system webhooks."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from wappa.core.logging.logger import get_logger
from wappa.webhooks import (
    SystemWebhook,
)

from ._stats import _LOGGER_NAME, LogLevel, _SystemStats


class DefaultSystemHandler:
    """
    Default handler for platform-level system event webhooks.

    Provides logging for system events such as phone number changes,
    BSUID updates, and marketing preference changes.
    """

    def __init__(self, log_level: LogLevel = LogLevel.INFO) -> None:
        """
        Initialize the default system handler.

        Args:
            log_level: Log level for system event logging (default: INFO)
        """
        self.log_level = log_level
        self.logger = get_logger(_LOGGER_NAME)

        self._stats = _SystemStats()

    async def handle_system(self, webhook: SystemWebhook) -> dict[str, Any]:
        """
        Handle a system webhook with logging.

        Args:
            webhook: SystemWebhook instance containing system event information

        Returns:
            Dictionary with handling results
        """
        self._stats.total_events += 1
        event_type = webhook.system_event_type.value
        self._stats.by_type[event_type] = self._stats.by_type.get(event_type, 0) + 1
        self._stats.last_processed = datetime.now(UTC)

        log_method = self._get_log_method(self.log_level)
        identity = (
            (webhook.user.user_id if webhook.user is not None else None)
            or webhook.event_detail.user_id
            or webhook.event_detail.wa_id
        )
        context = f"platform: {webhook.platform.value}, inbox: {webhook.inbox.inbox_id}"
        if identity:
            context += f", user: {identity}"
        log_method(f"⚙️ System event: {event_type} ({context})")

        return {
            "success": True,
            "handler": "DefaultSystemHandler",
            "event_type": event_type,
        }

    def _get_log_method(self, log_level: LogLevel) -> Callable[[str], None]:
        """Get the appropriate logger method for log level."""
        methods = {
            LogLevel.DEBUG: self.logger.debug,
            LogLevel.INFO: self.logger.info,
            LogLevel.WARNING: self.logger.warning,
            LogLevel.ERROR: self.logger.error,
        }
        return methods.get(log_level, self.logger.info)
