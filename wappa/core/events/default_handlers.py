"""
Default event handlers for message, status and error webhooks.

Provides built-in handlers for incoming messages, status updates and error webhooks that can be
used out-of-the-box or extended by users for custom behavior.
"""

import re
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from wappa.core.logging.logger import ContextLogger, get_logger
from wappa.webhooks import (
    ErrorWebhook,
    InboundMessageWebhook,
    StatusWebhook,
    SystemWebhook,
)


class LogLevel(Enum):
    """Log levels for default handlers."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class MessageLogStrategy(Enum):
    """Strategies for logging incoming message webhooks."""

    ALL = "all"  # Log all incoming messages with full detail
    SUMMARIZED = "summarized"  # Log message type, user info, content preview
    FILTERED = "filtered"  # Log only specific message types or conditions
    STATS_ONLY = "stats_only"  # Log only statistics, no individual messages
    NONE = "none"  # Don't log incoming messages


class StatusLogStrategy(Enum):
    """Strategies for logging status webhooks."""

    ALL = "all"  # Log all status updates
    FAILURES_ONLY = "failures_only"  # Log only failed/undelivered messages
    IMPORTANT_ONLY = "important_only"  # Log delivered, failed, read events only
    NONE = "none"  # Don't log status updates


class ErrorLogStrategy(Enum):
    """Strategies for logging error webhooks."""

    ALL = "all"  # Log all errors with full detail
    ERRORS_ONLY = "errors_only"  # Log only error-level issues
    CRITICAL_ONLY = "critical_only"  # Log only critical/fatal errors
    SUMMARY_ONLY = "summary_only"  # Log error count and primary error only


@dataclass
class _MessageStats:
    total_messages: int = 0
    by_type: dict[str, int] = field(default_factory=dict)
    by_user: dict[str, int] = field(default_factory=dict)
    by_inbox: dict[str, int] = field(default_factory=dict)
    sensitive_content_detected: int = 0
    last_reset: datetime = field(default_factory=datetime.now)


@dataclass
class _StatusStats:
    total_processed: int = 0
    sent: int = 0
    delivered: int = 0
    read: int = 0
    played: int = 0
    failed: int = 0
    deleted: int = 0
    last_processed: datetime | None = None


@dataclass
class _RecentError:
    timestamp: datetime
    error_code: int
    critical: bool


@dataclass
class _ErrorStats:
    total_errors: int = 0
    critical_errors: int = 0
    escalated_errors: int = 0
    last_error: datetime | None = None
    error_types: dict[int, int] = field(default_factory=dict)
    recent_errors: list[_RecentError] = field(default_factory=list)


@dataclass
class _SystemStats:
    total_events: int = 0
    by_type: dict[str, int] = field(default_factory=dict)
    last_processed: datetime | None = None


class DefaultMessageHandler:
    """
    Default handler for incoming message webhooks.

    Provides structured logging for all incoming WhatsApp messages with configurable
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
        logger = get_logger(__name__)

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

    def get_stats(self) -> dict[str, Any]:
        """
        Get current message processing statistics.

        Returns:
            Dictionary containing message processing statistics
        """
        return asdict(self._stats)

    def reset_stats(self) -> None:
        """Reset statistics tracking."""
        self._stats = _MessageStats()


class DefaultStatusHandler:
    """
    Default handler for WhatsApp status webhooks.

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
        self.logger = get_logger(__name__)

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
            f"(recipient: {webhook.recipient_id})"
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

    def get_stats(self) -> dict[str, Any]:
        """Get current status processing statistics."""
        return asdict(self._stats)

    def reset_stats(self) -> None:
        """Reset status processing statistics."""
        self._stats = _StatusStats()


class DefaultErrorHandler:
    """
    Default handler for WhatsApp error webhooks.

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
        self.logger = get_logger(__name__)

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

    def get_stats(self) -> dict[str, Any]:
        """Get complete error processing statistics."""
        return asdict(self._stats)

    def reset_stats(self) -> None:
        """Reset error processing statistics."""
        self._stats = _ErrorStats()


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
        self.logger = get_logger(__name__)

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
        log_method(
            f"⚙️ System event: {event_type} "
            f"(wa_id: {webhook.event_detail.wa_id}, user_id: {webhook.event_detail.user_id})"
        )

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

    def get_stats(self) -> dict[str, Any]:
        """Get current system event processing statistics."""
        return asdict(self._stats)

    def reset_stats(self) -> None:
        """Reset system event processing statistics."""
        self._stats = _SystemStats()


class DefaultHandlerFactory:
    """
    Factory for creating default event handlers with common configurations.
    """

    @staticmethod
    def create_production_status_handler() -> DefaultStatusHandler:
        """Create status handler optimized for production logging."""
        return DefaultStatusHandler(
            log_strategy=StatusLogStrategy.FAILURES_ONLY, log_level=LogLevel.WARNING
        )

    @staticmethod
    def create_development_status_handler() -> DefaultStatusHandler:
        """Create status handler optimized for development logging."""
        return DefaultStatusHandler(
            log_strategy=StatusLogStrategy.ALL, log_level=LogLevel.INFO
        )

    @staticmethod
    def create_production_message_handler() -> DefaultMessageHandler:
        """Create message handler optimized for production logging."""
        return DefaultMessageHandler(
            log_strategy=MessageLogStrategy.SUMMARIZED,
            log_level=LogLevel.INFO,
            content_preview_length=50,  # Shorter for production
            mask_sensitive_data=True,
        )

    @staticmethod
    def create_development_message_handler() -> DefaultMessageHandler:
        """Create message handler optimized for development logging."""
        return DefaultMessageHandler(
            log_strategy=MessageLogStrategy.ALL,
            log_level=LogLevel.INFO,
            content_preview_length=200,  # Longer for debugging
            mask_sensitive_data=False,  # No masking in dev for debugging
        )

    @staticmethod
    def create_production_error_handler() -> DefaultErrorHandler:
        """Create error handler optimized for production monitoring."""
        return DefaultErrorHandler(
            log_strategy=ErrorLogStrategy.ALL,
            escalation_threshold=3,
            escalation_window_minutes=5,
        )

    @staticmethod
    def create_development_error_handler() -> DefaultErrorHandler:
        """Create error handler optimized for development debugging."""
        return DefaultErrorHandler(
            log_strategy=ErrorLogStrategy.ALL,
            escalation_threshold=10,  # Higher threshold for dev
            escalation_window_minutes=15,
        )

    @staticmethod
    def create_production_system_handler() -> DefaultSystemHandler:
        """Create system handler optimized for production logging."""
        return DefaultSystemHandler(log_level=LogLevel.INFO)

    @staticmethod
    def create_development_system_handler() -> DefaultSystemHandler:
        """Create system handler optimized for development logging."""
        return DefaultSystemHandler(log_level=LogLevel.DEBUG)
