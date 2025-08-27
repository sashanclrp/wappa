"""
Main Wappa application class.

This is the core class that developers use to create and run their WhatsApp applications.
"""

import asyncio
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import aiohttp
import uvicorn
from fastapi import FastAPI

from wappa.api.middleware.error_handler import ErrorHandlerMiddleware
from wappa.api.middleware.request_logging import RequestLoggingMiddleware
from wappa.api.middleware.owner import OwnerMiddleware
from wappa.api.routes.health import router as health_router
from wappa.api.routes.webhooks import create_webhook_router
from wappa.api.routes.whatsapp_combined import whatsapp_router

from .config.settings import settings
from .events import WappaEventDispatcher
from .logging.logger import get_app_logger, setup_app_logging

if TYPE_CHECKING:
    from .events import WappaEventHandler


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context manager."""
    # Startup
    logger = None
    try:
        # Initialize logging first
        setup_app_logging()
        logger = get_app_logger()

        logger.info(f"Starting Wappa Framework v{settings.version}")
        logger.info(f"Environment: {settings.environment}")
        logger.info(f"Owner ID: {settings.owner_id}")
        logger.info(f"Log level: {settings.log_level}")

        if settings.is_development:
            logger.info(f"Development mode - logs: {settings.log_dir}")

        # Log available URLs
        base_url = (
            f"http://localhost:{settings.port}"
            if settings.is_development
            else "https://your-domain.com"
        )
        logger.info("=== AVAILABLE ENDPOINTS ===")
        logger.info(f"Health Check: {base_url}/health")
        logger.info(f"Detailed Health: {base_url}/health/detailed")
        logger.info(f"WhatsApp API: {base_url}/api/whatsapp/...")
        logger.info(
            f"API Documentation: {base_url}/docs"
            if settings.is_development
            else "API docs disabled in production"
        )
        logger.info("=============================")
        logger.info("")

        # Generate and display WhatsApp webhook URL
        from .events.webhook_factory import webhook_url_factory

        whatsapp_webhook_url = webhook_url_factory.generate_whatsapp_webhook_url()

        logger.info("=== WHATSAPP WEBHOOK URL ===")
        logger.info(f"📍 Primary Webhook URL: {whatsapp_webhook_url}")
        logger.info("   • Use this single URL in WhatsApp Business settings")
        logger.info("   • Handles both verification (GET) and webhooks (POST)")
        logger.info("   • Auto-configured with your WP_PHONE_ID from .env")
        logger.info("=============================")
        logger.info("")

        # Initialize HTTP session for the app (shared for connection pooling - correct scope)
        app.state.http_session = aiohttp.ClientSession()

        logger.info("Wappa application startup completed")
        yield

    except Exception as e:
        if logger:
            logger.error(f"Error during application startup: {e}", exc_info=True)
        else:
            print(f"Critical error during logging setup: {e}")
        raise

    finally:
        # Shutdown
        if logger:
            logger.info("Wappa application shutdown completed")

        # Close HTTP session
        if hasattr(app.state, "http_session"):
            await app.state.http_session.close()


class Wappa:
    """
    Main Wappa application class.

    This class provides a FastAPI-like interface for building WhatsApp applications
    with minimal setup and maximum flexibility.

    Usage:
        app = Wappa()
        app.set_event_handler(MyEventHandler())
        app.run()
    """

    def __init__(self, cache: str = "memory", config: dict | None = None):
        """
        Initialize Wappa application.

        Args:
            cache: Cache type ('memory', 'redis', 'json')
            config: Optional configuration overrides
        """
        self.cache_type = cache
        self.config = config or {}
        self._event_handler: WappaEventHandler | None = None
        self._app: FastAPI | None = None

    def set_event_handler(self, handler: "WappaEventHandler") -> None:
        """
        Set the event handler for this application.

        Dependencies are now injected per-request by the WebhookController,
        ensuring proper multi-tenant support and correct tenant isolation.

        Args:
            handler: WappaEventHandler instance to handle webhooks
        """
        # Store handler reference - dependencies will be injected per request
        self._event_handler = handler

    def set_app(self, app: FastAPI) -> None:
        """
        Set a pre-built FastAPI application instance.
        
        This method allows users to provide a FastAPI app that was created
        using WappaBuilder or other advanced configuration methods, while
        still using the Wappa class for event handler integration and running.
        
        Args:
            app: Pre-configured FastAPI application instance
            
        Example:
            # Create advanced app with WappaBuilder
            builder = WappaBuilder()
            app = await (builder
                .add_plugin(DatabasePlugin(...))
                .add_plugin(RedisPlugin())
                .build())
            
            # Use with Wappa for event handling
            wappa = Wappa()
            wappa.set_app(app)
            wappa.set_event_handler(MyHandler())
            wappa.run()
        """
        self._app = app

    def create_app(self) -> FastAPI:
        """
        Create and configure the FastAPI application.

        If a pre-built app was provided via set_app(), it integrates the event
        handler with that app. Otherwise, it creates a new FastAPI app with
        default Wappa configuration.

        Returns:
            Configured FastAPI application instance
        """
        if not self._event_handler:
            raise ValueError(
                "Must set event handler with set_event_handler() before creating app"
            )

        # If pre-built app was provided, integrate event handler and return it
        if self._app is not None:
            # Add webhook routes to the existing app
            dispatcher = WappaEventDispatcher(self._event_handler)
            webhook_router = create_webhook_router(dispatcher)
            self._app.include_router(webhook_router)

            logger = get_app_logger()
            logger.info(
                "Event handler integrated with pre-built FastAPI app from WappaBuilder"
            )
            return self._app

        # Create FastAPI app
        app = FastAPI(
            title="Wappa Application",
            description="WhatsApp Business application built with Wappa framework",
            version=settings.version,
            docs_url="/docs" if settings.is_development else None,
            redoc_url="/redoc" if settings.is_development else None,
            lifespan=lifespan,
        )

        # Add middleware (order matters - last added runs first)
        app.add_middleware(RequestLoggingMiddleware)
        app.add_middleware(ErrorHandlerMiddleware)
        app.add_middleware(OwnerMiddleware)

        # Include routers
        app.include_router(health_router)
        app.include_router(whatsapp_router)

        # Add webhook routes that use the event dispatcher
        if self._event_handler:
            # Create event dispatcher (dependencies injected per request by controller)
            dispatcher = WappaEventDispatcher(self._event_handler)
            webhook_router = create_webhook_router(dispatcher)
            app.include_router(webhook_router)

            logger = get_app_logger()
            logger.info(
                "Webhook routes integrated with event dispatcher and per-request dependency injection"
            )

        self._app = app
        return app

    def run(self, host: str = "0.0.0.0", port: int = None, **kwargs) -> None:
        """
        Run the Wappa application using uvicorn.

        Args:
            host: Host to bind to
            port: Port to bind to (defaults to settings.port)
            **kwargs: Additional uvicorn configuration
        """
        # Use port from settings if not provided
        if port is None:
            port = settings.port

        # Create the app first to ensure logging is initialized
        if not self._app:
            self._app = self.create_app()

        # Now we can safely get the logger
        logger = get_app_logger()
        logger.info(f"Starting Wappa v{settings.version} server on {host}:{port}")

        # Development mode: use reload with app factory
        if settings.is_development:
            logger.info("Development mode: reload enabled")

            # For reload to work, we need to use subprocess to call uvicorn with app factory
            # This way uvicorn can import the module and create the app fresh on each reload
            try:
                import subprocess
                import sys
                import os

                # Get the current script that called run()
                import inspect

                frame = inspect.currentframe()
                while frame:
                    filename = frame.f_code.co_filename
                    if filename != __file__ and not filename.startswith("<"):
                        script_path = filename
                        break
                    frame = frame.f_back
                else:
                    # Fallback: just run without reload
                    logger.warning(
                        "Could not detect script for reload, running without reload"
                    )
                    uvicorn.run(
                        self._app,
                        host=host,
                        port=port,
                        reload=False,
                        log_level=settings.log_level.lower(),
                    )
                    return

                # Create a temporary app factory in the script's directory
                script_dir = os.path.dirname(script_path)
                script_name = os.path.basename(script_path).replace(".py", "")

                logger.info(f"Starting uvicorn with reload for {script_name}")

                # Build uvicorn command
                cmd = [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    f"{script_name}:fastapi_app",
                    "--reload",
                    "--host",
                    str(host),
                    "--port",
                    str(port),
                    "--log-level",
                    settings.log_level.lower(),
                ]

                # Add any additional kwargs as command line args
                for key, value in kwargs.items():
                    if key == "reload":  # Skip reload, we're handling it
                        continue
                    cmd.extend([f"--{key.replace('_', '-')}", str(value)])

                # Change to script directory and run
                logger.info("Starting server with reload capability...")
                subprocess.run(cmd, cwd=script_dir)

            except Exception as e:
                logger.warning(
                    f"Could not start with reload ({e}), falling back to no-reload mode"
                )
                uvicorn.run(
                    self._app,
                    host=host,
                    port=port,
                    reload=False,
                    log_level=settings.log_level.lower(),
                )
        else:
            # Production mode: no reload, run app object directly
            logger.info("Production mode: reload disabled")
            uvicorn_config = {
                "host": host,
                "port": port,
                "reload": False,
                "log_level": settings.log_level.lower(),
                **kwargs,
            }
            uvicorn.run(self._app, **uvicorn_config)
