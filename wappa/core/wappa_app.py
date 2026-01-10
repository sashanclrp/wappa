"""
Main Wappa application class.

This is the core class that developers use to create and run their WhatsApp applications.
The class now uses WappaBuilder internally for unified plugin-based architecture.
"""

import subprocess
import sys
from collections.abc import Callable
from typing import TYPE_CHECKING

import uvicorn
from fastapi import FastAPI

from wappa.api.routes.webhooks import create_webhook_router

from .config.settings import settings
from .events import APIEventDispatcher, WappaEventDispatcher
from .factory.wappa_builder import WappaBuilder
from .logging.logger import get_app_logger
from .plugins.wappa_core_plugin import WappaCorePlugin
from .types import CacheType, CacheTypeOptions, validate_cache_type

if TYPE_CHECKING:
    from .events import WappaEventHandler
    from .factory.plugin import WappaPlugin


# Traditional lifespan management has been moved to WappaCorePlugin
# This enables unified plugin-based architecture for all Wappa applications


class Wappa:
    """
    Main Wappa application class with unified plugin-based architecture.

    This class now uses WappaBuilder internally, providing both simple usage
    for beginners and advanced extensibility for power users. All functionality
    is implemented through plugins, ensuring consistency and maintainability.

    Simple Usage:
        app = Wappa()
        app.set_event_handler(MyEventHandler())
        app.run()

    Advanced Usage:
        app = Wappa(cache="redis")
        app.add_plugin(DatabasePlugin(...))
        app.add_startup_hook(my_startup_func)
        app.set_event_handler(MyEventHandler())
        app.run()
    """

    def __init__(self, cache: CacheTypeOptions = "memory", config: dict | None = None):
        """
        Initialize Wappa application with plugin-based architecture.

        Automatically creates WappaBuilder with WappaCorePlugin and adds
        cache-specific plugins based on the cache type.

        Args:
            cache: Cache type ('memory', 'redis', 'json')
            config: Optional configuration overrides for FastAPI app

        Raises:
            ValueError: If cache type is not supported
        """
        # Validate and convert cache type
        self.cache_type = validate_cache_type(cache)
        self.config = config or {}
        self._event_handler: WappaEventHandler | None = None
        self._app: FastAPI | None = None
        self._asgi: FastAPI | None = None

        # Initialize WappaBuilder with core plugin
        self._builder = WappaBuilder()
        self._core_plugin = WappaCorePlugin(cache_type=self.cache_type)
        self._builder.add_plugin(self._core_plugin)

        # Automatically add cache-specific plugins
        self._auto_add_cache_plugins()

        # Apply any FastAPI configuration overrides
        if self.config:
            self._builder.configure(**self.config)

        logger = get_app_logger()
        logger.debug(
            f"🏗️ Wappa initialized with cache_type={self.cache_type.value}, "
            f"plugins={len(self._builder.plugins)}, config_overrides={bool(self.config)}"
        )

    def _auto_add_cache_plugins(self) -> None:
        """
        Automatically add cache-specific plugins based on cache type.

        This method ensures users get the appropriate cache infrastructure
        automatically without manual plugin management.
        """
        logger = get_app_logger()

        if self.cache_type == CacheType.REDIS:
            from .plugins.redis_plugin import RedisPlugin

            redis_plugin = RedisPlugin()
            self._builder.add_plugin(redis_plugin)
            logger.debug("🔴 Auto-added RedisPlugin for Redis cache type")
        elif self.cache_type == CacheType.JSON:
            # Future: JSONCachePlugin implementation
            logger.debug("📄 JSON cache type selected (plugin not yet implemented)")
        else:  # CacheType.MEMORY
            logger.debug("💾 Memory cache type selected (no additional plugin needed)")

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

        logger = get_app_logger()
        logger.debug(f"Event handler set: {handler.__class__.__name__}")

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

        logger = get_app_logger()
        logger.debug(
            f"Pre-built FastAPI app set: {app.title} v{app.version} "
            f"(middleware: {len(app.user_middleware)}, routes: {len(app.routes)})"
        )

    @property
    def asgi(self) -> FastAPI:
        """
        Return a FastAPI ASGI application, building synchronously if needed.

        This property enables uvicorn reload compatibility by providing a synchronous
        way to access the FastAPI app. Plugin configuration is deferred to lifespan
        hooks to maintain async initialization while keeping this property sync.

        Returns:
            FastAPI ASGI application instance

        Raises:
            ValueError: If no event handler has been set
        """
        if self._asgi is None:
            self._asgi = self._build_asgi_sync()
        return self._asgi

    def _build_asgi_sync(self) -> FastAPI:
        """
        Build FastAPI application synchronously using WappaBuilder.

        Creates the FastAPI app with WappaBuilder's unified lifespan management.
        Plugin configuration is deferred to lifespan startup hooks to maintain
        proper async initialization.
        """
        if not self._event_handler:
            raise ValueError(
                "Must set event handler with set_event_handler() before accessing .asgi property"
            )

        logger = get_app_logger()
        logger.debug("Building FastAPI ASGI app synchronously using WappaBuilder")

        # Configure FastAPI settings for builder
        self._builder.configure(
            title="Wappa Application",
            description="WhatsApp Business application built with Wappa framework",
            version=settings.version,
            docs_url="/docs" if settings.is_development else None,
            redoc_url="/redoc" if settings.is_development else None,
        )

        # Use WappaBuilder.build() - creates app with lifespan,
        # defers plugin configuration to startup hooks
        app = self._builder.build()

        # Create both dispatchers for the event handler
        webhook_dispatcher = WappaEventDispatcher(self._event_handler)
        api_dispatcher = APIEventDispatcher(self._event_handler)

        # Add webhook routes to the built app
        webhook_router = create_webhook_router(webhook_dispatcher)
        app.include_router(webhook_router)

        # Store API dispatcher in app.state for dependency injection
        app.state.api_event_dispatcher = api_dispatcher

        logger.info(
            f"✅ Wappa ASGI app built synchronously - cache: {self.cache_type.value}, "
            f"plugins: {len(self._builder.plugins)}, "
            f"event_handler: {self._event_handler.__class__.__name__}"
        )
        logger.debug("API event dispatcher registered in app.state")

        return app

    def create_app(self) -> FastAPI:
        """
        Create FastAPI application.

        This method directly uses WappaBuilder.build() which creates the app
        with unified lifespan management.

        Returns:
            Configured FastAPI application instance
        """
        if self._asgi is None:
            self._asgi = self._build_asgi_sync()
        return self._asgi

    def add_plugin(self, plugin: "WappaPlugin") -> "Wappa":
        """
        Add a plugin to extend Wappa functionality.

        This method provides access to the underlying WappaBuilder's plugin system
        while maintaining the simple Wappa interface. Plugins should be added
        before calling create_app() or run().

        Args:
            plugin: WappaPlugin instance to add

        Returns:
            Self for method chaining

        Example:
            from wappa.plugins import DatabasePlugin

            app = Wappa(cache="redis")
            app.add_plugin(DatabasePlugin("postgresql://...", PostgreSQLAdapter()))
            app.set_event_handler(MyEventHandler())
            app.run()
        """
        self._builder.add_plugin(plugin)

        logger = get_app_logger()
        logger.debug(f"Plugin added to Wappa: {plugin.__class__.__name__}")

        return self

    def add_startup_hook(self, hook: Callable, priority: int = 50) -> "Wappa":
        """
        Add a startup hook to be executed during application startup.

        This provides access to the underlying WappaBuilder's hook system.
        Hooks are executed in priority order during app startup.

        Args:
            hook: Async callable that takes (app: FastAPI) -> None
            priority: Execution priority (lower numbers run first)

        Returns:
            Self for method chaining

        Example:
            async def my_startup(app: FastAPI):
                print("My service is starting!")

            app = Wappa()
            app.add_startup_hook(my_startup, priority=30)
            app.set_event_handler(MyEventHandler())
            app.run()
        """
        self._builder.add_startup_hook(hook, priority)

        logger = get_app_logger()
        hook_name = getattr(hook, "__name__", "anonymous_hook")
        logger.debug(f"Startup hook added to Wappa: {hook_name} (priority: {priority})")

        return self

    def add_shutdown_hook(self, hook: Callable, priority: int = 50) -> "Wappa":
        """
        Add a shutdown hook to be executed during application shutdown.

        This provides access to the underlying WappaBuilder's hook system.
        Hooks are executed in reverse priority order during app shutdown.

        Args:
            hook: Async callable that takes (app: FastAPI) -> None
            priority: Execution priority (higher numbers run first in shutdown)

        Returns:
            Self for method chaining

        Example:
            async def my_shutdown(app: FastAPI):
                print("Cleaning up my service!")

            app = Wappa()
            app.add_shutdown_hook(my_shutdown, priority=30)
            app.set_event_handler(MyEventHandler())
            app.run()
        """
        self._builder.add_shutdown_hook(hook, priority)

        logger = get_app_logger()
        hook_name = getattr(hook, "__name__", "anonymous_hook")
        logger.debug(
            f"Shutdown hook added to Wappa: {hook_name} (priority: {priority})"
        )

        return self

    def add_middleware(
        self, middleware_class: type, priority: int = 50, **kwargs
    ) -> "Wappa":
        """
        Add middleware to the application with priority ordering.

        This provides access to the underlying WappaBuilder's middleware system.
        Priority determines execution order:
        - Lower numbers run first (outer middleware)
        - Higher numbers run last (inner middleware)
        - Default priority is 50

        Args:
            middleware_class: Middleware class to add
            priority: Execution priority (lower = outer, higher = inner)
            **kwargs: Middleware configuration parameters

        Returns:
            Self for method chaining

        Example:
            from fastapi.middleware.cors import CORSMiddleware

            app = Wappa(cache="redis")
            app.add_middleware(CORSMiddleware, allow_origins=["*"], priority=30)
            app.set_event_handler(MyHandler())
            app.run()
        """
        self._builder.add_middleware(middleware_class, priority, **kwargs)

        logger = get_app_logger()
        logger.debug(
            f"Middleware added to Wappa: {middleware_class.__name__} (priority: {priority})"
        )

        return self

    def add_router(self, router, **kwargs) -> "Wappa":
        """
        Add a router to the application.

        This provides access to the underlying WappaBuilder's router system.

        Args:
            router: FastAPI router to include
            **kwargs: Arguments for app.include_router()

        Returns:
            Self for method chaining

        Example:
            from fastapi import APIRouter

            custom_router = APIRouter()

            app = Wappa(cache="redis")
            app.add_router(custom_router, prefix="/api/v1", tags=["custom"])
            app.set_event_handler(MyHandler())
            app.run()
        """
        self._builder.add_router(router, **kwargs)

        logger = get_app_logger()
        router_name = getattr(router, "prefix", "router")
        logger.debug(f"Router added to Wappa: {router_name} with config: {kwargs}")

        return self

    def configure(self, **overrides) -> "Wappa":
        """
        Override default FastAPI configuration.

        This provides access to the underlying WappaBuilder's configuration system.

        Args:
            **overrides: FastAPI constructor arguments to override

        Returns:
            Self for method chaining

        Example:
            app = Wappa(cache="redis")
            app.configure(
                title="My WhatsApp Bot",
                version="2.0.0",
                description="Custom bot with advanced features"
            )
            app.set_event_handler(MyHandler())
            app.run()
        """
        self._builder.configure(**overrides)

        logger = get_app_logger()
        logger.debug(f"FastAPI configuration overrides added: {list(overrides.keys())}")

        return self

    def run(self, host: str = "0.0.0.0", port: int | None = None, **kwargs) -> None:
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

        # Use settings.is_development to determine mode
        dev_mode = settings.is_development

        logger = get_app_logger()
        logger.info(f"Starting Wappa v{settings.version} server on {host}:{port}")
        logger.info(f"Mode: {'development' if dev_mode else 'production'}")

        if dev_mode:
            logger.info("🔄 Development mode: auto-reload enabled")
            self._run_dev_mode(host, port, **kwargs)
        else:
            logger.info("🚀 Production mode: running directly")
            self._run_production(host, port, **kwargs)

    def _run_production(self, host: str, port: int, **kwargs) -> None:
        """Run in production mode without auto-reload."""
        logger = get_app_logger()

        uvicorn_config = {
            "host": host,
            "port": port,
            "reload": False,
            "log_level": settings.log_level.lower(),
            **kwargs,
        }

        logger.info("Starting production server with .asgi property...")
        # Use the .asgi property which handles sync build + lifespan initialization
        uvicorn.run(self.asgi, **uvicorn_config)

    def _run_dev_mode(self, host: str, port: int, **kwargs) -> None:
        """
        Run in development mode with uvicorn auto-reload.

        Uses uvicorn with import string for proper reload functionality.
        Requires module-level 'app' variable containing Wappa instance.
        """
        import inspect

        logger = get_app_logger()

        # Get the calling module to build import string
        frame = inspect.currentframe()
        while frame and frame.f_globals.get("__name__") == __name__:
            frame = frame.f_back

        if not frame:
            logger.error("❌ Cannot detect calling script for dev mode")
            raise RuntimeError(
                "Cannot locate calling script for dev mode.\n"
                "Make sure you're running from a Python file, not a REPL."
            )

        module_name = frame.f_globals.get("__name__")
        if module_name in (None, "__main__"):
            # Try to guess from file path
            file_path = frame.f_globals.get("__file__")
            if not file_path:
                raise RuntimeError("Dev mode requires running from a file, not a REPL.")

            # Convert file path to module name (e.g., examples/main.py -> examples.main)
            import os.path

            module_name = (
                os.path.splitext(os.path.relpath(file_path))[0]
                .replace(os.sep, ".")
                .lstrip(".")
            )

        # Build uvicorn command with import string
        import_string = f"{module_name}:app.asgi"
        cmd = [
            sys.executable,
            "-m",
            "uvicorn",
            import_string,
            "--reload",
            "--host",
            host,
            "--port",
            str(port),
            "--log-level",
            settings.log_level.lower(),
        ]

        # Add additional kwargs
        for key, value in kwargs.items():
            if key != "reload":  # Skip reload, we're handling it
                cmd.extend([f"--{key.replace('_', '-')}", str(value)])

        logger.info(f"🚀 Starting dev server: {' '.join(cmd)}")
        logger.info(f"📡 Import string: {import_string}")

        try:
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError as e:
            logger.error(f"❌ Uvicorn failed to start (exit code: {e.returncode})")
            raise RuntimeError(
                f"Development server failed to start.\n\n"
                f"Common causes:\n"
                f"• No module-level 'app' variable found in {module_name}\n"
                f"• Port {port} already in use\n"
                f"• Import errors in your script\n\n"
                f"Make sure you have: app = Wappa(...) at module level."
            ) from e
        except KeyboardInterrupt:
            logger.info("👋 Development server stopped by user")
