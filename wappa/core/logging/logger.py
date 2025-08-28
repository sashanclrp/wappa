"""
Custom Rich-based logger with tenant and user context support for Wappa framework.

Based on mimeiapify.utils.logger but customized for multi-tenant webhook processing.
Provides context-aware logging with tenant and user information.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime

from rich.console import Console
from rich.logging import RichHandler
from rich.theme import Theme

from wappa.core.config.settings import settings


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
    Logger wrapper that adds tenant and user context to messages.

    Following the old app's successful pattern - adds context as message prefixes
    instead of trying to modify the format string.
    """

    def __init__(
        self,
        logger: logging.Logger,
        tenant_id: str | None = None,
        user_id: str | None = None,
    ):
        self.logger = logger
        self.tenant_id = tenant_id or "---"
        self.user_id = user_id or "---"

    def _format_message(self, message: str) -> str:
        """Add context prefix to message."""
        # Get fresh context variables on each log call for dynamic context
        from .context import get_current_tenant_context, get_current_user_context

        current_tenant = get_current_tenant_context() or self.tenant_id
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
                - tenant_id: Override or set tenant identifier
                - user_id: Override or set user identifier

        Returns:
            New ContextLogger instance with updated context

        Example:
            # Add tenant context to existing logger
            new_logger = logger.bind(tenant_id="12345")

            # Update both tenant and user context
            contextual_logger = logger.bind(tenant_id="12345", user_id="user_67890")
        """
        # Extract context fields, using current values as defaults
        new_tenant_id = kwargs.get("tenant_id", self.tenant_id)
        new_user_id = kwargs.get("user_id", self.user_id)

        # Return new ContextLogger instance with updated context
        return ContextLogger(self.logger, tenant_id=new_tenant_id, user_id=new_user_id)


class ContextFilter(logging.Filter):
    """
    Logging filter that adds tenant and user context to log records.

    NOTE: This is kept for potential future use but not used in the current
    implementation to avoid the format string dependency issue.
    """

    def __init__(self, tenant_id: str | None = None, user_id: str | None = None):
        super().__init__()
        self.tenant_id = tenant_id or "---"
        self.user_id = user_id or "---"

    def filter(self, record: logging.LogRecord) -> bool:
        # Add context fields to record if not already present
        if not hasattr(record, "tenant_id"):
            record.tenant_id = self.tenant_id
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
) -> None:
    """
    Initialize the root logger with Rich formatting.

    Following the old app's successful pattern with simple formats that don't
    require context fields. Context will be added via logger wrapper classes.

    Parameters
    ----------
    level : str
        Logging level ("DEBUG", "INFO", "WARNING", "ERROR")
    mode : str
        "DEV" creates daily log files + console; anything else → console only
    log_dir : str, optional
        Directory for log files (DEV mode only)
    console_fmt : str, optional
        Console format string (simple format without context fields)
    file_fmt : str, optional
        File format string (simple format without context fields)
    """
    lvl = level.upper()
    lvl = lvl if lvl in ("DEBUG", "INFO", "WARNING", "ERROR") else "INFO"

    # Simple formats without context fields (like old app)
    # RichHandler already shows level and time, so we only need module name and message
    console_format = console_fmt or "[%(name)s] %(message)s"
    file_format = file_fmt or "%(asctime)s | %(levelname)s | %(name)s | %(message)s"

    # Rich console handler
    rich_handler = RichHandler(
        console=_console,
        rich_tracebacks=True,
        tracebacks_show_locals=True,
        show_time=True,
        show_level=True,
        markup=False,
    )
    rich_handler.setFormatter(CompactFormatter(console_format))

    handlers: list[logging.Handler] = [rich_handler]

    # Optional file handler for DEV mode
    if mode.upper() == "DEV" and log_dir:
        os.makedirs(log_dir, exist_ok=True)
        logfile = os.path.join(log_dir, f"wappa_{datetime.now():%Y%m%d}.log")
        file_handler = logging.FileHandler(logfile, encoding="utf-8")
        file_handler.setFormatter(CompactFormatter(file_format))
        handlers.append(file_handler)
        _console.print(f"[green]DEV mode:[/] console + file → {logfile}")
    else:
        _console.print(f"Logging configured for mode '{mode}'. Console only.")

    # Configure root logger with simple format
    logging.basicConfig(level=lvl, handlers=handlers, force=True)

    # Announce logging setup
    setup_logger = logging.getLogger("WappaLoggerSetup")
    setup_logger.info(f"Logging initialized ({lvl})")


def setup_app_logging() -> None:
    """
    Initialize application logging for Wappa platform.

    Called once during FastAPI application startup.
    """
    setup_logging(
        level=settings.log_level,
        mode="DEV" if settings.is_development else "PROD",
        log_dir=settings.log_dir if settings.is_development else None,
    )


def get_logger(name: str) -> ContextLogger:
    """
    Get a logger that automatically uses request context variables.

    This is the recommended way to get loggers in most components as it
    automatically picks up tenant_id and user_id from the current request context
    without requiring manual parameter passing.

    Args:
        name: Logger name (usually __name__)

    Returns:
        ContextLogger instance with automatic context from context variables
    """
    # Import here to avoid circular imports
    from .context import get_current_tenant_context, get_current_user_context

    # Use context variables for automatic context propagation
    effective_tenant_id = get_current_tenant_context()
    effective_user_id = get_current_user_context()

    base_logger = logging.getLogger(name)
    return ContextLogger(
        base_logger, tenant_id=effective_tenant_id, user_id=effective_user_id
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


def get_webhook_logger(name: str, tenant_id: str, user_id: str) -> ContextLogger:
    """
    Get a logger specifically configured for webhook processing.

    Args:
        name: Logger name (usually __name__)
        tenant_id: Tenant ID from webhook path
        user_id: User ID from webhook payload (WAID, etc.)

    Returns:
        ContextLogger with webhook context
    """
    base_logger = logging.getLogger(name)
    return ContextLogger(base_logger, tenant_id=tenant_id, user_id=user_id)


def update_logger_context(
    context_logger: ContextLogger,
    tenant_id: str | None = None,
    user_id: str | None = None,
) -> None:
    """
    Update the context of an existing ContextLogger.

    Useful when tenant/user context becomes available during request processing.

    Args:
        context_logger: ContextLogger instance to update
        tenant_id: New tenant ID
        user_id: New user ID
    """
    if tenant_id is not None:
        context_logger.tenant_id = tenant_id
    if user_id is not None:
        context_logger.user_id = user_id
