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

        # Performance monitoring middleware
        monitoring_plugin = CustomMiddlewarePlugin(
            PerformanceMonitoringMiddleware,
            priority=10,  # Low priority - runs last (inner)
            track_response_time=True
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

    async def configure(self, builder: "WappaBuilder") -> None:
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

        Can be used for middleware-specific initialization tasks.

        Args:
            app: FastAPI application instance
        """
        logger = get_app_logger()
        logger.debug(f"CustomMiddlewarePlugin startup - {self.name}")

    async def shutdown(self, app: "FastAPI") -> None:
        """
        Custom middleware plugin shutdown.

        Can be used for middleware-specific cleanup tasks.

        Args:
            app: FastAPI application instance
        """
        logger = get_app_logger()
        logger.debug(f"CustomMiddlewarePlugin shutdown - {self.name}")


# Convenience functions for common custom middleware patterns


def create_logging_middleware_plugin(
    middleware_class: type, log_level: str = "INFO", priority: int = 60, **kwargs: Any
) -> CustomMiddlewarePlugin:
    """
    Create a logging middleware plugin.

    Args:
        middleware_class: Logging middleware class
        log_level: Logging level
        priority: Middleware priority
        **kwargs: Additional middleware arguments

    Returns:
        Configured CustomMiddlewarePlugin for logging
    """
    return CustomMiddlewarePlugin(
        middleware_class,
        priority=priority,
        name="LoggingMiddleware",
        log_level=log_level,
        **kwargs,
    )


def create_security_middleware_plugin(
    middleware_class: type,
    priority: int = 85,  # High priority - runs early
    **kwargs: Any,
) -> CustomMiddlewarePlugin:
    """
    Create a security middleware plugin.

    Args:
        middleware_class: Security middleware class
        priority: Middleware priority
        **kwargs: Additional middleware arguments

    Returns:
        Configured CustomMiddlewarePlugin for security
    """
    return CustomMiddlewarePlugin(
        middleware_class, priority=priority, name="SecurityMiddleware", **kwargs
    )


def create_monitoring_middleware_plugin(
    middleware_class: type,
    priority: int = 10,  # Low priority - runs last (inner)
    **kwargs: Any,
) -> CustomMiddlewarePlugin:
    """
    Create a monitoring/metrics middleware plugin.

    Args:
        middleware_class: Monitoring middleware class
        priority: Middleware priority
        **kwargs: Additional middleware arguments

    Returns:
        Configured CustomMiddlewarePlugin for monitoring
    """
    return CustomMiddlewarePlugin(
        middleware_class, priority=priority, name="MonitoringMiddleware", **kwargs
    )
