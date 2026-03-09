"""
Auth Plugin

Plugin for adding authentication middleware to Wappa applications.
Uses the core auth module's strategy-based system with sensible defaults.
"""

from typing import TYPE_CHECKING

from ...core.logging.logger import get_app_logger
from ..auth.middleware import AuthMiddleware
from ..auth.strategy import AuthStrategy

if TYPE_CHECKING:
    from fastapi import FastAPI

    from ...core.factory.wappa_builder import WappaBuilder


class AuthPlugin:
    """
    Authentication middleware plugin for Wappa applications.

    Wraps AuthMiddleware with WappaPlugin lifecycle. Supports any
    AuthStrategy (Bearer, Basic, JWT, or custom).

    Example:
        from wappa.core.auth import BearerTokenStrategy

        auth = AuthPlugin(
            strategy=BearerTokenStrategy(token="my-secret"),
        )
        builder.add_plugin(auth)
    """

    DEFAULT_EXCLUDES = [
        "/health",
        "/api/sse/status",
        "/webhook/messenger",
        "/docs",
        "/openapi.json",
        "/redoc",
    ]

    def __init__(
        self,
        strategy: AuthStrategy,
        protect: list[str] | None = None,
        exclude: list[str] | None = None,
        sse_token_param: str = "token",
        expose_user: bool = True,
        middleware_priority: int = 60,
    ) -> None:
        self.strategy = strategy
        self.protect = protect
        self.sse_token_param = sse_token_param
        self.expose_user = expose_user
        self.priority = middleware_priority

        # Merge user excludes with defaults
        self.exclude = list(self.DEFAULT_EXCLUDES)
        if exclude:
            self.exclude.extend(exclude)

    def configure(self, builder: "WappaBuilder") -> None:
        """Add AuthMiddleware to the application with the configured strategy."""
        logger = get_app_logger()

        builder.add_middleware(
            AuthMiddleware,
            priority=self.priority,
            strategy=self.strategy,
            protect=self.protect,
            exclude=self.exclude,
            sse_token_param=self.sse_token_param,
            expose_user=self.expose_user,
        )

        logger.debug(
            f"AuthPlugin configured - strategy: {type(self.strategy).__name__}, "
            f"priority: {self.priority}, excludes: {len(self.exclude)} paths"
        )

    async def startup(self, app: "FastAPI") -> None:
        """No-op startup. Auth is configured entirely via middleware."""

    async def shutdown(self, app: "FastAPI") -> None:
        """No-op shutdown. No resources to clean up."""
