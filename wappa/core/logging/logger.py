"""
Custom Rich-based logger with inbox and user context support for Wappa framework.

Based on mimeiapify.utils.logger but customized for multi-inbox webhook processing.
Provides context-aware logging with inbox and user information.
"""

from __future__ import annotations

import json
import logging
import os
import re
import traceback
from datetime import UTC, datetime

from rich.console import Console
from rich.logging import RichHandler
from rich.theme import Theme

from wappa.core.config.settings import settings

# Regex to parse [T:...][U:...] context prefixes injected by ContextLogger
_CTX_PREFIX_RE = re.compile(
    r"^(?:\[T:(?P<inbox>[^\]]*)\])?(?:\[U:(?P<user>[^\]]*)\])?\s*(?P<rest>.*)",
    re.DOTALL,
)


class WappaJSONFormatter(logging.Formatter):
    """
    Single-line JSON formatter for production log aggregation.

    Each log record is emitted as one JSON object. Exception tracebacks are
    serialised into the ``exc`` field with newlines escaped, preserving the
    single-line contract required by platforms like Railway.

    Fields emitted per record:
    - ``ts``     – ISO-8601 timestamp (UTC, second precision)
    - ``level``  – log level name
    - ``logger`` – logger name
    - ``msg``    – message text (context prefix stripped)
    - ``inbox`` – inbox ID when present in the message prefix
    - ``user``   – user ID when present in the message prefix
    - ``exc``    – single-line traceback string (only when exception info is present)
    """

    def format(self, record: logging.LogRecord) -> str:
        # Parse context prefix out of the message so it becomes structured fields
        raw_msg = record.getMessage()
        m = _CTX_PREFIX_RE.match(raw_msg)
        inbox = m.group("inbox") if m else None
        user = m.group("user") if m else None
        clean_msg = m.group("rest") if m else raw_msg

        obj: dict[str, str] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).strftime(
                "%Y-%m-%dT%H:%M:%S"
            ),
            "level": record.levelname,
            "logger": record.name,
            "msg": clean_msg,
        }
        if inbox:
            obj["inbox"] = inbox
        if user:
            obj["user"] = user
        if record.exc_info:
            obj["exc"] = "".join(traceback.format_exception(*record.exc_info)).replace(
                "\n", "\\n"
            )
            record.exc_info = None  # prevent the base class from appending it again
        elif record.exc_text:
            obj["exc"] = record.exc_text.replace("\n", "\\n")
            record.exc_text = None

        return json.dumps(obj, ensure_ascii=False)


class CompactFormatter(logging.Formatter):
    """Custom formatter that shortens long module names for better readability."""

    def format(self, record):
        # Shorten long module names for better readability
        if record.name.startswith("wappa."):
            # Convert wappa.core.events.event_dispatcher -> events.dispatcher
            parts = record.name.split(".")
            if len(parts) > 2:
                # Keep last 2 parts for most modules
                if "event_dispatcher" in record.name:
                    record.name = "events.dispatcher"
                elif "default_handlers" in record.name:
                    record.name = "events.handlers"
                elif "whatsapp" in record.name:
                    # For WhatsApp modules, keep whatsapp.component
                    relevant_parts = [
                        p
                        for p in parts
                        if p in ["whatsapp", "messenger", "handlers", "client"]
                    ]
                    record.name = (
                        ".".join(relevant_parts[-2:])
                        if len(relevant_parts) >= 2
                        else ".".join(relevant_parts)
                    )
                else:
                    # Default: keep last 2 parts
                    record.name = ".".join(parts[-2:])

        return super().format(record)


# Rich theme for colored output
_theme = Theme(
    {
        "info": "cyan",
        "warning": "yellow",
        "error": "bold red",
        "debug": "dim white",
    }
)
_console = Console(theme=_theme)


class ContextLogger:
    """
    Logger wrapper that adds inbox and user context to messages.

    Following the old app's successful pattern - adds context as message prefixes
    instead of trying to modify the format string.
    """

    def __init__(
        self,
        logger: logging.Logger,
        inbox_id: str | None = None,
        user_id: str | None = None,
    ):
        self.logger = logger
        self.inbox_id = inbox_id or "---"
        self.user_id = user_id or "---"

    def _format_message(self, message: str) -> str:
        """Add context prefix to message."""
        # Get fresh context variables on each log call for dynamic context
        from .context import get_current_inbox_context, get_current_user_context

        current_tenant = get_current_inbox_context() or self.inbox_id
        current_user = get_current_user_context() or self.user_id

        if current_tenant and current_tenant != "---":
            if current_user and current_user != "---":
                return f"[T:{current_tenant}][U:{current_user}] {message}"
            else:
                return f"[T:{current_tenant}] {message}"
        elif current_user and current_user != "---":
            return f"[U:{current_user}] {message}"
        return message

    def debug(self, message: str, *args, **kwargs) -> None:
        """Log debug message with context."""
        self.logger.debug(self._format_message(message), *args, **kwargs)

    def info(self, message: str, *args, **kwargs) -> None:
        """Log info message with context."""
        self.logger.info(self._format_message(message), *args, **kwargs)

    def warning(self, message: str, *args, **kwargs) -> None:
        """Log warning message with context."""
        self.logger.warning(self._format_message(message), *args, **kwargs)

    def error(self, message: str, *args, **kwargs) -> None:
        """Log error message with context."""
        self.logger.error(self._format_message(message), *args, **kwargs)

    def critical(self, message: str, *args, **kwargs) -> None:
        """Log critical message with context."""
        self.logger.critical(self._format_message(message), *args, **kwargs)

    def exception(self, message: str, *args, **kwargs) -> None:
        """Log exception message with context."""
        self.logger.exception(self._format_message(message), *args, **kwargs)

    def bind(self, **kwargs) -> ContextLogger:
        """
        Create a new ContextLogger with additional or updated context.

        This method follows the Loguru-style bind pattern, returning a new
        logger instance with updated context rather than modifying the current one.

        Args:
            **kwargs: Context fields to bind. Common fields:
                - inbox_id: Override or set inbox identifier
                - user_id: Override or set user identifier

        Returns:
            New ContextLogger instance with updated context

        Example:
            # Add inbox context to existing logger
            new_logger = logger.bind(inbox_id="12345")

            # Update both inbox and user context
            contextual_logger = logger.bind(inbox_id="12345", user_id="user_67890")
        """
        # Extract context fields, using current values as defaults
        new_inbox_id = kwargs.get("inbox_id", self.inbox_id)
        new_user_id = kwargs.get("user_id", self.user_id)

        # Return new ContextLogger instance with updated context
        return ContextLogger(self.logger, inbox_id=new_inbox_id, user_id=new_user_id)


class ContextFilter(logging.Filter):
    """
    Logging filter that adds inbox and user context to log records.

    NOTE: This is kept for potential future use but not used in the current
    implementation to avoid the format string dependency issue.
    """

    def __init__(self, inbox_id: str | None = None, user_id: str | None = None):
        super().__init__()
        self.inbox_id = inbox_id or "---"
        self.user_id = user_id or "---"

    def filter(self, record: logging.LogRecord) -> bool:
        # Add context fields to record if not already present
        if not hasattr(record, "inbox_id"):
            record.inbox_id = self.inbox_id
        if not hasattr(record, "user_id"):
            record.user_id = self.user_id
        return True


def setup_logging(
    *,
    level: str = "INFO",
    mode: str = "PROD",
    log_dir: str | None = None,
    console_fmt: str | None = None,
    file_fmt: str | None = None,
    rich_format: bool = True,
) -> None:
    """
    Initialize the root logger.

    Parameters
    ----------
    level : str
        Logging level ("DEBUG", "INFO", "WARNING", "ERROR")
    mode : str
        "DEV" creates daily log files + console; anything else → console only
    log_dir : str, optional
        Directory for log files (DEV mode only)
    console_fmt : str, optional
        Console format string used in Rich mode only
    file_fmt : str, optional
        File format string used in Rich/DEV mode only
    rich_format : bool
        When True (default in dev) uses RichHandler with coloured tracebacks.
        When False (default in prod) emits compact single-line JSON to stdout —
        safe for log-aggregation platforms with per-line rate limits.
    """
    lvl = level.upper()
    lvl = lvl if lvl in ("DEBUG", "INFO", "WARNING", "ERROR") else "INFO"

    handlers: list[logging.Handler] = []

    if rich_format:
        console_format = console_fmt or "[%(name)s] %(message)s"
        file_format = file_fmt or "%(asctime)s | %(levelname)s | %(name)s | %(message)s"

        rich_handler = RichHandler(
            console=_console,
            rich_tracebacks=True,
            tracebacks_show_locals=True,
            show_time=True,
            show_level=True,
            markup=False,
        )
        rich_handler.setFormatter(CompactFormatter(console_format))
        handlers.append(rich_handler)

        if mode.upper() == "DEV" and log_dir:
            os.makedirs(log_dir, exist_ok=True)
            logfile = os.path.join(log_dir, f"wappa_{datetime.now():%Y%m%d}.log")
            file_handler = logging.FileHandler(logfile, encoding="utf-8")
            file_handler.setFormatter(CompactFormatter(file_format))
            handlers.append(file_handler)
            _console.print(f"[green]DEV mode:[/] console + file → {logfile}")
        else:
            _console.print(
                f"Logging configured for mode '{mode}' (rich). Console only."
            )
    else:
        json_handler = logging.StreamHandler()
        json_handler.setFormatter(WappaJSONFormatter())
        handlers.append(json_handler)

    logging.basicConfig(level=lvl, handlers=handlers, force=True)

    setup_logger = logging.getLogger("WappaLoggerSetup")
    fmt_label = "rich" if rich_format else "json"
    setup_logger.info(f"Logging initialized ({lvl}, format={fmt_label})")


def setup_app_logging() -> None:
    """
    Initialize application logging for Wappa platform.

    Called once during FastAPI application startup. Format is chosen by:
    1. ``SYSTEM_LOGS_RICH_FORMAT`` env var (via ``settings.logs_rich_format``) — explicit override
    2. ``settings.is_development`` — ``True`` → rich, ``False`` → json
    """
    rich_format = (
        settings.logs_rich_format
        if settings.logs_rich_format is not None
        else settings.is_development
    )

    setup_logging(
        level=settings.log_level,
        mode="DEV" if settings.is_development else "PROD",
        log_dir=settings.log_dir if settings.is_development else None,
        rich_format=rich_format,
    )


def get_logger(name: str) -> ContextLogger:
    """
    Get a logger that automatically uses request context variables.

    This is the recommended way to get loggers in most components as it
    automatically picks up inbox_id and user_id from the current request context
    without requiring manual parameter passing.

    Args:
        name: Logger name (usually __name__)

    Returns:
        ContextLogger instance with automatic context from context variables
    """
    # Import here to avoid circular imports
    from .context import get_current_inbox_context, get_current_user_context

    # Use context variables for automatic context propagation
    effective_inbox_id = get_current_inbox_context()
    effective_user_id = get_current_user_context()

    base_logger = logging.getLogger(name)
    return ContextLogger(
        base_logger, inbox_id=effective_inbox_id, user_id=effective_user_id
    )


def get_app_logger() -> ContextLogger:
    """
    Get application logger for general app events (startup, shutdown, etc.).

    Returns:
        ContextLogger instance with app-level context
    """
    return get_logger("wappa.app")


def get_api_logger(name: str | None = None) -> ContextLogger:
    """
    Get API logger for application endpoints and controllers.

    Alias for get_app_logger() to maintain compatibility with existing code.

    Args:
        name: Optional logger name (ignored for compatibility)

    Returns:
        ContextLogger instance with API-level context
    """
    return get_logger(name or "wappa.api")


def get_webhook_logger(name: str, inbox_id: str, user_id: str) -> ContextLogger:
    """
    Get a logger specifically configured for webhook processing.

    Args:
        name: Logger name (usually __name__)
        inbox_id: Inbox ID from webhook path
        user_id: User ID from webhook payload (WAID, etc.)

    Returns:
        ContextLogger with webhook context
    """
    base_logger = logging.getLogger(name)
    return ContextLogger(base_logger, inbox_id=inbox_id, user_id=user_id)


def update_logger_context(
    context_logger: ContextLogger,
    inbox_id: str | None = None,
    user_id: str | None = None,
) -> None:
    """
    Update the context of an existing ContextLogger.

    Useful when inbox/user context becomes available during request processing.

    Args:
        context_logger: ContextLogger instance to update
        inbox_id: New inbox ID
        user_id: New user ID
    """
    if inbox_id is not None:
        context_logger.inbox_id = inbox_id
    if user_id is not None:
        context_logger.user_id = user_id
