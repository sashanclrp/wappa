"""Log levels, logging strategies and stat dataclasses for the default handlers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

# Logger name shared by every default handler module (kept from the pre-split module).
_LOGGER_NAME = "wappa.core.events.default_handlers"


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
