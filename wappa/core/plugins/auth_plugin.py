"""
Auth Plugin

Plugin for adding authentication middleware to Wappa applications.
Provides a flexible wrapper for various authentication backends.
"""

from typing import TYPE_CHECKING, Any

from ...core.logging.logger import get_app_logger

if TYPE_CHECKING:
    from fastapi import FastAPI

    from ...core.factory.wappa_builder import WappaBuilder


class AuthPlugin:
    """
    Authentication middleware plugin for Wappa applications.

    Provides a flexible wrapper for authentication middleware, supporting
    various authentication backends like JWT, OAuth, API keys, etc.

    Example:
        # JWT authentication
        auth_plugin = AuthPlugin(
            JWTMiddleware,
            secret_key="your-secret-key",
            algorithm="HS256"
        )

        # OAuth authentication
        auth_plugin = AuthPlugin(
            OAuthMiddleware,
            client_id="your-client-id",
            client_secret="your-client-secret"
        )

        # Custom authentication
        auth_plugin = AuthPlugin(
            CustomAuthMiddleware,
            api_key_header="X-API-Key"
        )
    """

    def __init__(
        self,
        auth_middleware_class: type,
        priority: int = 80,  # High priority - runs early but after CORS
        **middleware_kwargs: Any,
    ):
        """
        Initialize authentication plugin.

        Args:
            auth_middleware_class: Authentication middleware class
            priority: Middleware priority (lower runs first/outer)
            **middleware_kwargs: Arguments for the middleware class
        """
        self.auth_middleware_class = auth_middleware_class
        self.priority = priority
        self.middleware_kwargs = middleware_kwargs

    async def configure(self, builder: "WappaBuilder") -> None:
        """
        Configure authentication plugin with WappaBuilder.

        Adds the authentication middleware to the application.

        Args:
            builder: WappaBuilder instance
        """
        logger = get_app_logger()

        # Add authentication middleware to builder
        builder.add_middleware(
            self.auth_middleware_class, priority=self.priority, **self.middleware_kwargs
        )

        logger.debug(
            f"AuthPlugin configured with {self.auth_middleware_class.__name__} "
            f"(priority: {self.priority})"
        )

    async def startup(self, app: "FastAPI") -> None:
        """
        Authentication plugin startup.

        Can be used for authentication backend initialization,
        key validation, etc.

        Args:
            app: FastAPI application instance
        """
        logger = get_app_logger()
        logger.debug(f"AuthPlugin startup - {self.auth_middleware_class.__name__}")

    async def shutdown(self, app: "FastAPI") -> None:
        """
        Authentication plugin shutdown.

        Can be used for cleaning up authentication resources.

        Args:
            app: FastAPI application instance
        """
        logger = get_app_logger()
        logger.debug(f"AuthPlugin shutdown - {self.auth_middleware_class.__name__}")


# Convenience functions for common authentication patterns


def create_jwt_auth_plugin(
    secret_key: str, algorithm: str = "HS256", **kwargs: Any
) -> AuthPlugin:
    """
    Create a JWT authentication plugin.

    Note: This is a convenience function. You'll need to provide
    an actual JWT middleware implementation.

    Args:
        secret_key: JWT secret key
        algorithm: JWT algorithm
        **kwargs: Additional JWT middleware arguments

    Returns:
        Configured AuthPlugin for JWT authentication
    """
    try:
        # This is a placeholder - you'd import your actual JWT middleware
        from your_auth_library import JWTMiddleware

        return AuthPlugin(
            JWTMiddleware, secret_key=secret_key, algorithm=algorithm, **kwargs
        )
    except ImportError as e:
        raise ImportError(
            "JWT middleware not found. Please implement or install a JWT middleware library."
        ) from e


def create_api_key_auth_plugin(
    api_key_header: str = "X-API-Key", **kwargs: Any
) -> AuthPlugin:
    """
    Create an API key authentication plugin.

    Note: This is a convenience function. You'll need to provide
    an actual API key middleware implementation.

    Args:
        api_key_header: Header name for API key
        **kwargs: Additional API key middleware arguments

    Returns:
        Configured AuthPlugin for API key authentication
    """
    try:
        # This is a placeholder - you'd import your actual API key middleware
        from your_auth_library import APIKeyMiddleware

        return AuthPlugin(APIKeyMiddleware, api_key_header=api_key_header, **kwargs)
    except ImportError as e:
        raise ImportError(
            "API key middleware not found. Please implement or install an API key middleware library."
        ) from e
