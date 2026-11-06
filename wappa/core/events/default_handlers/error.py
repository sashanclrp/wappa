"""Default handler for error webhooks."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from wappa.core.logging.logger import get_logger
from wappa.webhooks import (
    ErrorWebhook,
)

from ._stats import _LOGGER_NAME, ErrorLogStrategy, _ErrorStats, _RecentError


class DefaultErrorHandler:
    """
    Default handler for Platform error webhooks.

    Provides configurable logging strategies for platform errors with escalation support.
    Users can customize the logging strategy or extend this class for custom behavior.
    """

    def __init__(
        self,
        log_strategy: ErrorLogStrategy = ErrorLogStrategy.ALL,
        escalation_threshold: int = 5,
        escalation_window_minutes: int = 10,
    ) -> None:
        """
        Initialize the default error handler.

        Args:
            log_strategy: Strategy for which errors to log
            escalation_threshold: Number of errors to trigger escalation
            escalation_window_minutes: Time window for escalation counting
        """
        self.log_strategy = log_strategy
        self.escalation_threshold = escalation_threshold
        self.escalation_window_minutes = escalation_window_minutes
        self.logger = get_logger(_LOGGER_NAME)

        # Track error statistics
        self._stats = _ErrorStats()

    async def handle_error(self, webhook: ErrorWebhook) -> dict[str, Any]:
        """
        Handle an error webhook with escalation logic.

        Args:
            webhook: ErrorWebhook instance containing error information

        Returns:
            Dictionary with handling results and escalation status
        """
        error_count = webhook.get_error_count()
        primary_error = webhook.get_primary_error()

        # Update statistics
        self._stats.total_errors += error_count
        self._stats.last_error = datetime.now(UTC)

        # Track error types
        error_code = primary_error.error_code
        if error_code not in self._stats.error_types:
            self._stats.error_types[error_code] = 0
        self._stats.error_types[error_code] += 1

        # Check if error is critical
        is_critical = self._is_critical_error(primary_error)
        if is_critical:
            self._stats.critical_errors += 1

        # Add to recent errors for escalation tracking
        current_time = datetime.now(UTC)
        self._stats.recent_errors.append(
            _RecentError(
                timestamp=current_time,
                error_code=error_code,
                critical=is_critical,
            )
        )

        # Clean old errors from recent list
        self._clean_recent_errors(current_time)

        # Check for escalation
        should_escalate = self._should_escalate()
        if should_escalate:
            self._stats.escalated_errors += 1

        # Apply logging strategy
        should_log = self._should_log_error(webhook, is_critical)

        if should_log:
            log_message = self._format_error_message(webhook, should_escalate)

            if should_escalate or is_critical:
                self.logger.error(log_message)
            else:
                self.logger.warning(log_message)

        return {
            "success": True,
            "action": "error_logged" if should_log else "error_ignored",
            "handler": "DefaultErrorHandler",
            "error_count": error_count,
            "primary_error_code": primary_error.error_code,
            "critical": is_critical,
            "escalated": should_escalate,
            "logged": should_log,
            "stats": self._get_stats_summary(),
        }

    def _is_critical_error(self, error: Any) -> bool:
        """Determine if an error is critical based on error code."""
        critical_codes = {
            100,  # Invalid parameter
            102,  # Message undeliverable
            131,  # Access token issue
            132,  # Application not authorized
            133,  # Phone number not authorized
        }
        return error.error_code in critical_codes

    def _should_escalate(self) -> bool:
        """Check if errors should be escalated based on recent activity."""
        recent_count = len(self._stats.recent_errors)
        critical_recent = sum(
            1 for error in self._stats.recent_errors if error.critical
        )

        # Escalate if too many errors recently, or multiple critical errors
        return recent_count >= self.escalation_threshold or critical_recent >= 2

    def _clean_recent_errors(self, current_time: datetime) -> None:
        """Remove old errors from recent tracking list."""
        cutoff_time = current_time.timestamp() - (self.escalation_window_minutes * 60)

        self._stats.recent_errors = [
            error
            for error in self._stats.recent_errors
            if error.timestamp.timestamp() > cutoff_time
        ]

    def _should_log_error(self, webhook: ErrorWebhook, is_critical: bool) -> bool:
        """Determine if error should be logged based on strategy."""
        if self.log_strategy == ErrorLogStrategy.ALL:
            return True
        elif self.log_strategy == ErrorLogStrategy.CRITICAL_ONLY:
            return is_critical
        elif self.log_strategy == ErrorLogStrategy.ERRORS_ONLY:
            return True  # All webhook errors are considered errors
        elif self.log_strategy == ErrorLogStrategy.SUMMARY_ONLY:
            return webhook.get_error_count() > 1  # Only multi-error cases

        return True  # Default to logging

    def _format_error_message(self, webhook: ErrorWebhook, escalated: bool) -> str:
        """Format error message for logging."""
        error_count = webhook.get_error_count()
        primary_error = webhook.get_primary_error()

        escalation_prefix = "🚨 ESCALATED: " if escalated else ""
        error_icon = "💥" if escalated else "⚠️"

        if error_count == 1:
            return (
                f"{escalation_prefix}{error_icon} Platform error: "
                f"{primary_error.error_code} - {primary_error.error_title}"
            )
        else:
            return (
                f"{escalation_prefix}{error_icon} Multiple platform errors: "
                f"{error_count} errors, primary: {primary_error.error_code} - {primary_error.error_title}"
            )

    def _get_stats_summary(self) -> dict[str, Any]:
        """Get summarized statistics for response."""
        return {
            "total_errors": self._stats.total_errors,
            "critical_errors": self._stats.critical_errors,
            "escalated_errors": self._stats.escalated_errors,
            "recent_count": len(self._stats.recent_errors),
            "top_error_types": dict(
                sorted(
                    self._stats.error_types.items(), key=lambda x: x[1], reverse=True
                )[:5]
            ),
        }
