"""
Application context — dependency injection container for the expiry system.

Replaces global state with explicit context injection.
"""

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = logging.getLogger(__name__)


@dataclass
class AppContext:
    """
    Holds a reference to the FastAPI app for use inside expiry handlers.

    Usage:
        context = AppContext()
        context.set_app(fastapi_app)
        app = context.get_app()
    """

    _app: "FastAPI | None" = field(default=None, repr=False)

    def set_app(self, app: "FastAPI") -> None:
        """Store FastAPI app reference."""
        self._app = app
        logger.debug("FastAPI app reference stored in context")

    def get_app(self) -> "FastAPI | None":
        """Return the FastAPI app, or None if not yet set."""
        return self._app

    def clear(self) -> None:
        """Release app reference on shutdown."""
        self._app = None
        logger.debug("AppContext cleared")

    @property
    def is_initialized(self) -> bool:
        """True if the app reference has been set."""
        return self._app is not None


# Single acceptable module-level global — the context container itself.
_app_context = AppContext()


def get_app_context() -> AppContext:
    """Return the application context singleton."""
    return _app_context
