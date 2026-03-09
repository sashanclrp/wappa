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

    The plugin operates in one of two mutually exclusive modes:

    - **Exclude mode** (default): All paths require auth except those in the
      exclude list. Default excludes (health, docs, webhook) are always included.
    - **Protect mode**: Only paths in the protect list require auth; everything
      else passes through freely.

    You cannot pass both ``protect`` and ``exclude``; doing so raises a
    ``ValueError``.

    Example:
        from wappa.core.auth import BearerTokenStrategy

        # Exclude mode (default) — everything protected, these paths skipped
        auth = AuthPlugin(
            strategy=BearerTokenStrategy(token="my-secret"),
            exclude=["/public"],
        )

        # Protect mode — only these paths require auth
        auth = AuthPlugin(
            strategy=BearerTokenStrategy(token="my-secret"),
            protect=["/api/admin", "/api/users"],
        )
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
        if protect is not None and exclude is not None:
            raise ValueError(
                "AuthPlugin does not support both 'protect' and 'exclude' at the "
                "same time. Use 'protect' to list the only paths that require auth, "
                "or 'exclude' to list paths that skip auth (everything else protected)."
            )

        self.strategy = strategy
        self.sse_token_param = sse_token_param
        self.expose_user = expose_user
        self.priority = middleware_priority

        if protect is not None:
            # Protect mode: only these paths require auth
            self.protect = protect
            self.exclude = None
        else:
            # Exclude mode (default): everything protected, skip these paths
            self.protect = None
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

        mode = "protect" if self.protect is not None else "exclude"
        path_count = (
            len(self.protect) if self.protect is not None else len(self.exclude or [])
        )
        logger.debug(
            f"AuthPlugin configured - strategy: {type(self.strategy).__name__}, "
            f"mode: {mode}, {mode} paths: {path_count}, priority: {self.priority}"
        )

    async def startup(self, app: "FastAPI") -> None:
        """No-op startup. Auth is configured entirely via middleware."""

    async def shutdown(self, app: "FastAPI") -> None:
        """No-op shutdown. No resources to clean up."""
