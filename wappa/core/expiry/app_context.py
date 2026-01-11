"""
Application Context - Dependency Injection container for expiry system.

Replaces global state pattern with proper context injection.
"""

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = logging.getLogger(__name__)


@dataclass
class AppContext:
    """
    Application context container for expiry handlers.

    Provides dependency injection for FastAPI app reference,
    replacing the global state pattern with explicit context.

    Usage:
        # Set context during startup
        context = AppContext()
        context.set_app(fastapi_app)

        # Access in handlers
        app = context.get_app()

    Design:
        - Single instance per application lifecycle
        - Thread-safe for async operations
        - Explicit dependencies over hidden globals
    """

    _app: Optional["FastAPI"] = field(default=None, repr=False)

    def set_app(self, app: "FastAPI") -> None:
        """
        Store FastAPI app reference.

        Args:
            app: FastAPI application instance
        """
        self._app = app
        logger.debug("FastAPI app reference stored in context")

    def get_app(self) -> Optional["FastAPI"]:
        """
        Retrieve FastAPI app reference.

        Returns:
            FastAPI app instance or None if not set
        """
        return self._app

    def clear(self) -> None:
        """
        Clear context during shutdown.

        Releases FastAPI app reference to allow garbage collection.
        """
        self._app = None
        logger.debug("AppContext cleared")

    @property
    def is_initialized(self) -> bool:
        """Check if context has app reference."""
        return self._app is not None


# Module-level singleton instance
# This is the ONLY acceptable global - a context container
_app_context = AppContext()


def get_app_context() -> AppContext:
    """
    Get the application context singleton.

    Returns:
        AppContext instance
    """
    return _app_context


# Backward compatibility functions
# These delegate to the context object instead of using global state
def set_fastapi_app(app: "FastAPI") -> None:
    """
    Store FastAPI app reference for expiry handlers.

    Backward compatible function that delegates to AppContext.

    Args:
        app: FastAPI application instance
    """
    _app_context.set_app(app)


def get_fastapi_app() -> Optional["FastAPI"]:
    """
    Get FastAPI app reference for accessing HTTP session in expiry handlers.

    Backward compatible function that delegates to AppContext.

    Returns:
        FastAPI app instance or None
    """
    return _app_context.get_app()
