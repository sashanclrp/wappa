"""
CORS Plugin

Plugin for adding Cross-Origin Resource Sharing (CORS) middleware to Wappa applications.
Provides a simple wrapper around FastAPI's CORSMiddleware with sensible defaults.
"""

from typing import TYPE_CHECKING, Any

from ...core.logging.logger import get_app_logger

if TYPE_CHECKING:
    from fastapi import FastAPI

    from ...core.factory.wappa_builder import WappaBuilder


class CORSPlugin:
    """
    CORS middleware plugin for Wappa applications.

    Provides Cross-Origin Resource Sharing support with configurable
    origins, methods, and headers. Uses FastAPI's built-in CORSMiddleware
    with sensible defaults for most use cases.

    Example:
        # Basic CORS (allow all origins)
        cors_plugin = CORSPlugin(allow_origins=["*"])

        # Production CORS (specific origins)
        cors_plugin = CORSPlugin(
            allow_origins=["https://myapp.com", "https://www.myapp.com"],
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "DELETE"],
            allow_headers=["*"]
        )
    """

    def __init__(
        self,
        allow_origins: list[str] = None,
        allow_methods: list[str] = None,
        allow_headers: list[str] = None,
        allow_credentials: bool = False,
        expose_headers: list[str] = None,
        max_age: int = 600,
        priority: int = 90,  # High priority - runs early (outer middleware)
        **cors_kwargs: Any,
    ):
        """
        Initialize CORS plugin.

        Args:
            allow_origins: List of allowed origins (defaults to ["*"])
            allow_methods: List of allowed HTTP methods (defaults to ["GET"])
            allow_headers: List of allowed headers (defaults to [])
            allow_credentials: Whether to allow credentials
            expose_headers: List of headers to expose to the browser
            max_age: Maximum age for preflight requests
            priority: Middleware priority (lower runs first/outer)
            **cors_kwargs: Additional CORSMiddleware arguments
        """
        self.allow_origins = allow_origins or ["*"]
        self.allow_methods = allow_methods or ["GET"]
        self.allow_headers = allow_headers or []
        self.allow_credentials = allow_credentials
        self.expose_headers = expose_headers or []
        self.max_age = max_age
        self.priority = priority
        self.cors_kwargs = cors_kwargs

    def configure(self, builder: "WappaBuilder") -> None:
        """
        Configure CORS plugin with WappaBuilder.

        Adds CORSMiddleware to the application with specified configuration.

        Args:
            builder: WappaBuilder instance
        """
        logger = get_app_logger()

        try:
            from fastapi.middleware.cors import CORSMiddleware
        except ImportError as e:
            logger.error(
                "CORSMiddleware not available - ensure FastAPI is properly installed"
            )
            raise RuntimeError("CORSMiddleware not available") from e

        # Build CORS configuration
        cors_config = {
            "allow_origins": self.allow_origins,
            "allow_methods": self.allow_methods,
            "allow_headers": self.allow_headers,
            "allow_credentials": self.allow_credentials,
            "expose_headers": self.expose_headers,
            "max_age": self.max_age,
            **self.cors_kwargs,
        }

        # Add middleware to builder with specified priority
        builder.add_middleware(CORSMiddleware, priority=self.priority, **cors_config)

        logger.debug(
            f"CORSPlugin configured - Origins: {self.allow_origins}, "
            f"Methods: {self.allow_methods}, Credentials: {self.allow_credentials}"
        )

    async def startup(self, app: "FastAPI") -> None:
        """
        CORS plugin startup - no startup tasks needed.

        Args:
            app: FastAPI application instance
        """
        logger = get_app_logger()
        logger.debug("CORSPlugin startup completed")

    async def shutdown(self, app: "FastAPI") -> None:
        """
        CORS plugin shutdown - no cleanup tasks needed.

        Args:
            app: FastAPI application instance
        """
        logger = get_app_logger()
        logger.debug("CORSPlugin shutdown completed")
