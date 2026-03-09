"""
Custom Middleware Plugin

Plugin for adding user-defined middleware to Wappa applications.
Provides a flexible wrapper for any custom middleware implementation.
"""

from typing import TYPE_CHECKING, Any

from ...core.logging.logger import get_app_logger

if TYPE_CHECKING:
    from fastapi import FastAPI

    from ...core.factory.wappa_builder import WappaBuilder


class CustomMiddlewarePlugin:
    """
    Custom middleware plugin for Wappa applications.

    Provides a flexible wrapper for any user-defined middleware,
    allowing complete control over middleware configuration and behavior.

    Example:
        # Request logging middleware
        logging_plugin = CustomMiddlewarePlugin(
            RequestLoggingMiddleware,
            priority=60,
            log_level="INFO"
        )

        # Security headers middleware
        security_plugin = CustomMiddlewarePlugin(
            SecurityHeadersMiddleware,
            priority=85,
            include_hsts=True,
            include_csp=True
        )
    """

    def __init__(
        self,
        middleware_class: type,
        priority: int = 50,  # Default priority
        name: str = None,
        **middleware_kwargs: Any,
    ):
        """
        Initialize custom middleware plugin.

        Args:
            middleware_class: Custom middleware class
            priority: Middleware priority (lower runs first/outer)
            name: Optional name for the middleware (for logging)
            **middleware_kwargs: Arguments for the middleware class
        """
        self.middleware_class = middleware_class
        self.priority = priority
        self.name = name or middleware_class.__name__
        self.middleware_kwargs = middleware_kwargs

    def configure(self, builder: "WappaBuilder") -> None:
        """
        Configure custom middleware plugin with WappaBuilder.

        Adds the custom middleware to the application.

        Args:
            builder: WappaBuilder instance
        """
        logger = get_app_logger()

        # Add custom middleware to builder
        builder.add_middleware(
            self.middleware_class, priority=self.priority, **self.middleware_kwargs
        )

        logger.debug(
            f"CustomMiddlewarePlugin configured - {self.name} "
            f"(priority: {self.priority})"
        )

    async def startup(self, app: "FastAPI") -> None:
        """
        Custom middleware plugin startup.

        Args:
            app: FastAPI application instance
        """
        logger = get_app_logger()
        logger.debug(f"CustomMiddlewarePlugin startup - {self.name}")

    async def shutdown(self, app: "FastAPI") -> None:
        """
        Custom middleware plugin shutdown.

        Args:
            app: FastAPI application instance
        """
        logger = get_app_logger()
        logger.debug(f"CustomMiddlewarePlugin shutdown - {self.name}")
