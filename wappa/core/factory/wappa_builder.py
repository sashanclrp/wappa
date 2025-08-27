"""
WappaBuilder - Extensible FastAPI Application Factory

This module provides the WappaBuilder class that enables users to create
highly customized FastAPI applications using a plugin-based architecture.
"""

import asyncio
from contextlib import asynccontextmanager
from typing import Any, Callable, TYPE_CHECKING

from fastapi import FastAPI

from ..logging.logger import get_app_logger

if TYPE_CHECKING:
    from .plugin import WappaPlugin


class WappaBuilder:
    """
    Fluent builder for creating extensible Wappa applications.
    
    The WappaBuilder provides a plugin-based architecture that allows users
    to extend FastAPI functionality without modifying core code. It supports:
    
    - Plugin system with lifecycle management
    - Priority-based middleware ordering
    - Configurable startup/shutdown hooks
    - Seamless integration with existing Wappa class
    
    Example:
        builder = WappaBuilder()
        app = await (builder
            .add_plugin(DatabasePlugin("postgresql://...", PostgreSQLAdapter()))
            .add_plugin(RedisPlugin())
            .add_middleware(CORSMiddleware, allow_origins=["*"])
            .configure(title="My Wappa App")
            .build())
    """

    def __init__(self):
        """Initialize WappaBuilder with empty configuration."""
        self.plugins: list["WappaPlugin"] = []
        self.middlewares: list[tuple[type, dict, int]] = []  # (class, kwargs, priority)
        self.routers: list[tuple[Any, dict]] = []  # (router, include_kwargs)
        self.startup_hooks: list[tuple[Callable, int]] = []  # (hook, priority)
        self.shutdown_hooks: list[tuple[Callable, int]] = []  # (hook, priority)
        self.config_overrides: dict[str, Any] = {}

    def add_plugin(self, plugin: "WappaPlugin") -> "WappaBuilder":
        """
        Add a plugin to extend functionality.
        
        Plugins provide a clean way to add complex functionality like database
        connections, Redis caching, authentication, etc.
        
        Args:
            plugin: WappaPlugin instance to add
            
        Returns:
            Self for method chaining
        """
        self.plugins.append(plugin)
        return self

    def add_middleware(
        self, 
        middleware_class: type, 
        priority: int = 50, 
        **kwargs: Any
    ) -> "WappaBuilder":
        """
        Add middleware to the application with priority ordering.
        
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
        """
        self.middlewares.append((middleware_class, kwargs, priority))
        return self

    def add_router(self, router: Any, **kwargs: Any) -> "WappaBuilder":
        """
        Add a router to the application.
        
        Args:
            router: FastAPI router to include
            **kwargs: Arguments for app.include_router()
            
        Returns:
            Self for method chaining
        """
        self.routers.append((router, kwargs))
        return self

    def add_startup_hook(self, hook: Callable, priority: int = 50) -> "WappaBuilder":
        """
        Add a startup hook with priority ordering.
        
        Args:
            hook: Async callable to execute during startup
            priority: Execution priority (lower = runs first)
            
        Returns:
            Self for method chaining
        """
        self.startup_hooks.append((hook, priority))
        return self

    def add_shutdown_hook(self, hook: Callable, priority: int = 50) -> "WappaBuilder":
        """
        Add a shutdown hook with priority ordering.
        
        Args:
            hook: Async callable to execute during shutdown
            priority: Execution priority (lower = runs first in shutdown)
            
        Returns:
            Self for method chaining
        """
        self.shutdown_hooks.append((hook, priority))
        return self

    def configure(self, **overrides: Any) -> "WappaBuilder":
        """
        Override default FastAPI configuration.
        
        Args:
            **overrides: FastAPI constructor arguments to override
            
        Returns:
            Self for method chaining
        """
        self.config_overrides.update(overrides)
        return self

    async def build(self) -> FastAPI:
        """
        Build the configured FastAPI application.
        
        This method:
        1. Configures all plugins
        2. Creates the FastAPI app with lifespan management
        3. Adds middleware in priority order
        4. Includes all routers
        
        Returns:
            Configured FastAPI application instance
        """
        logger = get_app_logger()
        
        # Configure plugins first - they can modify the builder
        logger.debug(f"Configuring {len(self.plugins)} plugins...")
        for plugin in self.plugins:
            await plugin.configure(self)
        
        # Create lifespan manager with plugin coordination
        @asynccontextmanager
        async def lifespan(app: FastAPI):
            try:
                # Startup phase
                logger.debug("Starting plugin and hook startup phase...")
                await self._execute_startup(app)
                yield
            finally:
                # Shutdown phase
                logger.debug("Starting plugin and hook shutdown phase...")
                await self._execute_shutdown(app)

        # Create FastAPI app with default configuration and overrides
        default_config = {
            "title": "Wappa Application",
            "description": "WhatsApp Business application built with Wappa framework",
            "version": "1.0.0",
            "lifespan": lifespan,
        }
        default_config.update(self.config_overrides)
        
        app = FastAPI(**default_config)
        logger.debug(f"Created FastAPI app: {default_config['title']}")

        # Add middlewares in reverse priority order (FastAPI adds in reverse)
        # Higher priority numbers run closer to the routes (inner middleware)
        sorted_middlewares = sorted(self.middlewares, key=lambda x: x[2], reverse=True)
        for middleware_class, kwargs, priority in sorted_middlewares:
            app.add_middleware(middleware_class, **kwargs)
            logger.debug(f"Added middleware {middleware_class.__name__} (priority: {priority})")

        # Include all routers
        for router, kwargs in self.routers:
            app.include_router(router, **kwargs)
            logger.debug(f"Included router with config: {kwargs}")

        logger.info(
            f"WappaBuilder created app with {len(self.plugins)} plugins, "
            f"{len(self.middlewares)} middlewares, {len(self.routers)} routers"
        )
        
        return app

    async def _execute_startup(self, app: FastAPI) -> None:
        """
        Execute startup sequence for plugins and hooks.
        
        Args:
            app: FastAPI application instance
        """
        logger = get_app_logger()
        
        try:
            # Execute plugin startups first
            for plugin in self.plugins:
                plugin_name = plugin.__class__.__name__
                logger.debug(f"Starting plugin: {plugin_name}")
                await plugin.startup(app)
                logger.debug(f"Plugin {plugin_name} started successfully")

            # Execute custom startup hooks in priority order
            sorted_hooks = sorted(self.startup_hooks, key=lambda x: x[1])
            for hook, priority in sorted_hooks:
                hook_name = getattr(hook, '__name__', 'anonymous_hook')
                logger.debug(f"Executing startup hook: {hook_name} (priority: {priority})")
                await hook(app)
                logger.debug(f"Startup hook {hook_name} completed")

            logger.info("All plugins and startup hooks completed successfully")
            
        except Exception as e:
            logger.error(f"Error during startup phase: {e}", exc_info=True)
            raise

    async def _execute_shutdown(self, app: FastAPI) -> None:
        """
        Execute shutdown sequence for plugins and hooks.
        
        Args:
            app: FastAPI application instance
        """
        logger = get_app_logger()
        
        # Execute shutdown hooks first (reverse priority order)
        sorted_hooks = sorted(self.shutdown_hooks, key=lambda x: x[1], reverse=True)
        for hook, priority in sorted_hooks:
            try:
                hook_name = getattr(hook, '__name__', 'anonymous_hook')
                logger.debug(f"Executing shutdown hook: {hook_name} (priority: {priority})")
                await hook(app)
                logger.debug(f"Shutdown hook {hook_name} completed")
            except Exception as e:
                logger.error(f"Error in shutdown hook {hook_name}: {e}", exc_info=True)

        # Execute plugin shutdowns in reverse order
        for plugin in reversed(self.plugins):
            try:
                plugin_name = plugin.__class__.__name__
                logger.debug(f"Shutting down plugin: {plugin_name}")
                await plugin.shutdown(app)
                logger.debug(f"Plugin {plugin_name} shut down successfully")
            except Exception as e:
                logger.error(f"Error shutting down plugin {plugin_name}: {e}", exc_info=True)

        logger.info("All plugins and shutdown hooks completed")