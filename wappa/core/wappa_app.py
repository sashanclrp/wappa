"""
Main Wappa application class.

This is the core class that developers use to create and run their WhatsApp applications.
The class now uses WappaBuilder internally for unified plugin-based architecture.
"""

import asyncio
from collections.abc import Callable
from typing import TYPE_CHECKING

import uvicorn
from fastapi import FastAPI

from wappa.api.routes.webhooks import create_webhook_router

from .config.settings import settings
from .events import WappaEventDispatcher
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

    async def create_app(self) -> FastAPI:
        """
        Create and configure the FastAPI application using WappaBuilder.

        Uses the internal WappaBuilder instance that was configured during initialization
        with WappaCorePlugin and any cache-specific plugins. If an event handler is set,
        it will be integrated with the webhook system.

        Returns:
            Configured FastAPI application instance

        Raises:
            ValueError: If no event handler has been set
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

        # Build the FastAPI app using WappaBuilder with all configured plugins
        logger = get_app_logger()
        logger.debug("Creating FastAPI app using WappaBuilder with plugin architecture")

        # Configure FastAPI settings for builder
        self._builder.configure(
            title="Wappa Application",
            description="WhatsApp Business application built with Wappa framework",
            version=settings.version,
            docs_url="/docs" if settings.is_development else None,
            redoc_url="/redoc" if settings.is_development else None,
        )

        # Build the app with unified plugin-based architecture
        app = await self._builder.build()

        # Add webhook routes that use the event dispatcher
        dispatcher = WappaEventDispatcher(self._event_handler)
        webhook_router = create_webhook_router(dispatcher)
        app.include_router(webhook_router)

        logger.info(
            f"✅ Wappa app created with plugin architecture - "
            f"cache: {self.cache_type.value}, plugins: {len(self._builder.plugins)}, "
            f"event_handler: {self._event_handler.__class__.__name__}"
        )

        self._app = app
        return app

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

    def run(self, host: str = "0.0.0.0", port: int|None = None, **kwargs) -> None:
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

        # Auto-determine reload mode based on environment
        reload = settings.is_development

        # Create the app first to ensure logging is initialized
        if not self._app:
            self._app = asyncio.run(self.create_app())

        # Now we can safely get the logger
        logger = get_app_logger()
        logger.info(f"Starting Wappa v{settings.version} server on {host}:{port}")

        # Handle development vs production mode
        logger.info(f"Mode: {'development' if settings.is_development else 'production'}")

        if reload:
            logger.info("🔄 Development mode: auto-reload enabled")
            self._run_with_reload(host, port, **kwargs)
        else:
            logger.info("🚀 Production mode: auto-reload disabled")
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

        logger.info("Starting server with Wappa's unified architecture...")
        if self._app is None:
            logger.error("❌ FastAPI app instance is None. Cannot start server.")
            raise RuntimeError("FastAPI app instance is None. Ensure create_app() was called and succeeded.")
        uvicorn.run(self._app, **uvicorn_config)

    def _run_with_reload(self, host: str, port: int, **kwargs) -> None:
        """Run in development mode with uvicorn auto-reload using subprocess."""
        import subprocess
        import sys
        import os
        import inspect
        
        logger = get_app_logger()
        
        # Get the current script that called run()
        frame = inspect.currentframe()
        script_path = None
        while frame:
            filename = frame.f_code.co_filename
            if filename != __file__ and not filename.startswith('<') and filename.endswith('.py'):
                script_path = filename
                break
            frame = frame.f_back
        
        if not script_path:
            logger.warning("Could not detect script for reload, falling back to no-reload mode")
            self._run_production(host, port, **kwargs)
            return
        
        # Check if the script has a fastapi_app export
        try:
            with open(script_path, 'r') as f:
                content = f.read()
            
            if 'fastapi_app' not in content:
                logger.warning("🔄 Auto-reload requires 'fastapi_app' export in your script")
                logger.warning("🔄 Add: fastapi_app = create_fastapi_app()")
                logger.warning("🔄 Falling back to production mode")
                self._run_production(host, port, **kwargs)
                return
                
        except Exception as e:
            logger.error(f"❌ Could not read script for reload detection: {e}")
            self._run_production(host, port, **kwargs)
            return
        
        # Create uvicorn subprocess command
        script_dir = os.path.dirname(script_path)
        script_name = os.path.basename(script_path).replace('.py', '')
        
        logger.info(f"🔄 Starting uvicorn with reload for {script_name}")
        
        # Build uvicorn command
        cmd = [
            sys.executable, "-m", "uvicorn",
            f"{script_name}:fastapi_app",
            "--reload",
            "--host", str(host),
            "--port", str(port),
            "--log-level", settings.log_level.lower()
        ]
        
        # Add any additional kwargs as command line args
        for key, value in kwargs.items():
            if key == 'reload':  # Skip reload, we're handling it
                continue
            cmd.extend([f"--{key.replace('_', '-')}", str(value)])
        
        try:
            # Change to script directory and run
            logger.info("🔄 Starting server with reload capability...")
            logger.info(f"📁 Working directory: {script_dir}")
            logger.info(f"📁 Import string: {script_name}:fastapi_app")
            subprocess.run(cmd, cwd=script_dir)
            
        except Exception as e:
            logger.error(f"❌ Could not start with reload ({e}), falling back to no-reload mode")
            self._run_production(host, port, **kwargs)


