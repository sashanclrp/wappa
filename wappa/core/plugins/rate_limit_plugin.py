"""
Rate Limit Plugin

Plugin for adding rate limiting middleware to Wappa applications.
Provides protection against abuse and DoS attacks.
"""

from typing import TYPE_CHECKING, Any

from ...core.logging.logger import get_app_logger

if TYPE_CHECKING:
    from fastapi import FastAPI

    from ...core.factory.wappa_builder import WappaBuilder


class RateLimitPlugin:
    """
    Rate limiting middleware plugin for Wappa applications.

    Provides request rate limiting to protect against abuse and DoS attacks.
    Can be configured with different strategies and backends.

    Example:
        # Basic rate limiting
        rate_limit_plugin = RateLimitPlugin(
            RateLimiterMiddleware,
            max_requests=100,
            window_seconds=60
        )

        # Redis-backed rate limiting
        rate_limit_plugin = RateLimitPlugin(
            RedisRateLimiterMiddleware,
            max_requests=1000,
            window_seconds=3600,
            redis_url="redis://localhost:6379"
        )
    """

    def __init__(
        self,
        rate_limit_middleware_class: type,
        priority: int = 70,  # Medium-high priority
        **middleware_kwargs: Any,
    ):
        """
        Initialize rate limit plugin.

        Args:
            rate_limit_middleware_class: Rate limiting middleware class
            priority: Middleware priority (lower runs first/outer)
            **middleware_kwargs: Arguments for the middleware class
        """
        self.rate_limit_middleware_class = rate_limit_middleware_class
        self.priority = priority
        self.middleware_kwargs = middleware_kwargs

    async def configure(self, builder: "WappaBuilder") -> None:
        """
        Configure rate limit plugin with WappaBuilder.

        Adds the rate limiting middleware to the application.

        Args:
            builder: WappaBuilder instance
        """
        logger = get_app_logger()

        # Add rate limiting middleware to builder
        builder.add_middleware(
            self.rate_limit_middleware_class,
            priority=self.priority,
            **self.middleware_kwargs,
        )

        logger.debug(
            f"RateLimitPlugin configured with {self.rate_limit_middleware_class.__name__} "
            f"(priority: {self.priority})"
        )

    async def startup(self, app: "FastAPI") -> None:
        """
        Rate limit plugin startup.

        Can be used for rate limiter backend initialization.

        Args:
            app: FastAPI application instance
        """
        logger = get_app_logger()
        logger.debug(
            f"RateLimitPlugin startup - {self.rate_limit_middleware_class.__name__}"
        )

    async def shutdown(self, app: "FastAPI") -> None:
        """
        Rate limit plugin shutdown.

        Can be used for cleaning up rate limiter resources.

        Args:
            app: FastAPI application instance
        """
        logger = get_app_logger()
        logger.debug(
            f"RateLimitPlugin shutdown - {self.rate_limit_middleware_class.__name__}"
        )


# Convenience functions for common rate limiting patterns


def create_memory_rate_limit_plugin(
    max_requests: int = 100, window_seconds: int = 60, **kwargs: Any
) -> RateLimitPlugin:
    """
    Create an in-memory rate limiting plugin.

    Note: This is a convenience function. You'll need to provide
    an actual rate limiting middleware implementation.

    Args:
        max_requests: Maximum requests per window
        window_seconds: Time window in seconds
        **kwargs: Additional rate limiter arguments

    Returns:
        Configured RateLimitPlugin for in-memory rate limiting
    """
    try:
        # This is a placeholder - you'd import your actual rate limiting middleware
        from your_rate_limit_library import MemoryRateLimiterMiddleware

        return RateLimitPlugin(
            MemoryRateLimiterMiddleware,
            max_requests=max_requests,
            window_seconds=window_seconds,
            **kwargs,
        )
    except ImportError as e:
        raise ImportError(
            "Rate limiting middleware not found. Please implement or install a rate limiting middleware library."
        ) from e


def create_redis_rate_limit_plugin(
    max_requests: int = 1000,
    window_seconds: int = 3600,
    redis_url: str = "redis://localhost:6379",
    **kwargs: Any,
) -> RateLimitPlugin:
    """
    Create a Redis-backed rate limiting plugin.

    Note: This is a convenience function. You'll need to provide
    an actual Redis rate limiting middleware implementation.

    Args:
        max_requests: Maximum requests per window
        window_seconds: Time window in seconds
        redis_url: Redis connection URL
        **kwargs: Additional rate limiter arguments

    Returns:
        Configured RateLimitPlugin for Redis-backed rate limiting
    """
    try:
        # This is a placeholder - you'd import your actual Redis rate limiting middleware
        from your_rate_limit_library import RedisRateLimiterMiddleware

        return RateLimitPlugin(
            RedisRateLimiterMiddleware,
            max_requests=max_requests,
            window_seconds=window_seconds,
            redis_url=redis_url,
            **kwargs,
        )
    except ImportError as e:
        raise ImportError(
            "Redis rate limiting middleware not found. Please implement or install a Redis rate limiting middleware library."
        ) from e
