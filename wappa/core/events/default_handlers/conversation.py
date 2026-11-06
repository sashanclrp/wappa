"""Default handler for conversation event webhooks."""

from __future__ import annotations

from typing import Any

from wappa.core.logging.logger import get_logger

from ._stats import _LOGGER_NAME, LogLevel


class DefaultConversationEventHandler:
    """Default INFO record for update/comment/mention lanes.

    Logs native references only; comment text and payloads stay out of logs.
    """

    def __init__(self, log_level: LogLevel = LogLevel.INFO) -> None:
        self.log_level = log_level
        self.logger = get_logger(_LOGGER_NAME)

    async def log_event(self, webhook: Any) -> None:
        summary = webhook.get_summary()
        kind = summary.pop("webhook_type", type(webhook).__name__)
        summary.pop("payload", None)
        details = ", ".join(f"{k}: {v}" for k, v in summary.items() if v is not None)
        method = {
            LogLevel.DEBUG: self.logger.debug,
            LogLevel.INFO: self.logger.info,
            LogLevel.WARNING: self.logger.warning,
            LogLevel.ERROR: self.logger.error,
        }.get(self.log_level, self.logger.info)
        method(f"🗨️ {kind} ({details})")
