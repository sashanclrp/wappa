"""
WappaBuilder - Extensible FastAPI Application Factory

This module provides the WappaBuilder class that enables users to create
highly customized FastAPI applications using a plugin-based architecture.
"""

from collections.abc import Callable
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

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
        self.plugins: list[WappaPlugin] = []
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
        self, middleware_class: type, priority: int = 50, **kwargs: Any
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
        Add a startup hook to unified lifespan management.

        Hooks are executed during application startup in priority order.
        Lower priority numbers execute first.

        Priority Guidelines:
        - 10: Core system initialization (logging, sessions)
        - 20: Infrastructure (databases, caches, external services)
        - 30: Application services
        - 50: User hooks (default)
        - 70+: Late initialization hooks

        Args:
            hook: Async callable that takes (app: FastAPI) -> None
            priority: Execution priority (lower = runs first)

        Returns:
            Self for method chaining

        Example:
            async def my_startup(app: FastAPI):
                print("Starting my service")

            builder.add_startup_hook(my_startup, priority=30)
        """
        self.startup_hooks.append((hook, priority))
        return self

    def add_shutdown_hook(self, hook: Callable, priority: int = 50) -> "WappaBuilder":
        """
        Add a shutdown hook to unified lifespan management.

        Hooks are executed during application shutdown in reverse priority order.
        Higher priority numbers execute first during shutdown.

        Priority Guidelines:
        - 90: Core system cleanup (sessions, logging) - runs last
        - 70: Application services cleanup
        - 50: User hooks (default)
        - 30: Application services
        - 20: Infrastructure cleanup (databases, caches)
        - 10: Early cleanup

        Args:
            hook: Async callable that takes (app: FastAPI) -> None
            priority: Execution priority (higher = runs first in shutdown)

        Returns:
            Self for method chaining

        Example:
            async def my_shutdown(app: FastAPI):
                print("Cleaning up my service")

            builder.add_shutdown_hook(my_shutdown, priority=30)
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

    def build(self) -> FastAPI:
        """
        Build the configured FastAPI application following proper FastAPI initialization pattern.

        This method follows the exact pattern you specified:
        1. Configure plugins (sync setup only)
        2. Create FastAPI app with lifespan and config
        3. Add all middleware via app.add_middleware()
        4. Include all routers via app.include_router()

        Only async operations happen in the lifespan (startup/shutdown hooks).

        Returns:
            FastAPI application with properly configured plugins
        """
        logger = get_app_logger()
        logger.debug(f"🏗️ Building FastAPI app with {len(self.plugins)} plugins")

        # Step 1: Configure plugins (sync setup only - middleware/router registration)
        if self.plugins:
            logger.debug(f"⚙️ Configuring {len(self.plugins)} plugins synchronously...")
            for plugin in self.plugins:
                plugin.configure(self)  # Synchronous configuration

            logger.info(
                f"✅ Plugin configuration complete - registered {len(self.middlewares)} middlewares, "
                f"{len(self.routers)} routers, {len(self.startup_hooks)} startup hooks, "
                f"{len(self.shutdown_hooks)} shutdown hooks"
            )

        # Create unified lifespan (only for async startup/shutdown hooks)

        @asynccontextmanager
        async def unified_lifespan(app: FastAPI):
            try:
                # Startup phase - execute async startup hooks only
                logger.debug("🚀 Starting unified lifespan startup phase...")
                await self._execute_all_startup_hooks(app)
                logger.info("✅ All startup hooks completed successfully")
                yield
            except Exception as e:
                logger.error(f"❌ Error during startup phase: {e}", exc_info=True)
                raise
            finally:
                # Shutdown phase - execute async shutdown hooks
                logger.debug("🛑 Starting unified lifespan shutdown phase...")
                await self._execute_all_shutdown_hooks(app)
                logger.info("✅ All shutdown hooks completed")

        # Step 2: Create FastAPI app with lifespan and config
        default_config = {
            "title": "Wappa Application",
            "description": "WhatsApp Business application built with Wappa framework",
            "version": "1.0.0",
            "lifespan": unified_lifespan,
        }
        default_config.update(self.config_overrides)

        app = FastAPI(**default_config)
        logger.debug(f"Created FastAPI app: {default_config['title']}")

        # Step 3: Add all middleware via app.add_middleware()
        # Sort by priority (reverse order because FastAPI adds middleware in reverse)
        sorted_middlewares = sorted(self.middlewares, key=lambda x: x[2], reverse=True)
        for middleware_class, kwargs, priority in sorted_middlewares:
            app.add_middleware(middleware_class, **kwargs)
            logger.debug(
                f"Added middleware {middleware_class.__name__} (priority: {priority})"
            )

        # Step 4: Include all routers via app.include_router()
        for router, kwargs in self.routers:
            app.include_router(router, **kwargs)
            logger.debug(f"Included router with config: {kwargs}")

        logger.info(
            f"🎉 WappaBuilder created FastAPI app: {len(self.plugins)} plugins, "
            f"{len(self.middlewares)} middlewares, {len(self.routers)} routers"
        )

        return app

    async def _execute_all_startup_hooks(self, app: FastAPI) -> None:
        """
        Execute all startup hooks in unified priority order.

        This replaces the old plugin-specific startup execution with a unified
        approach where all hooks (from plugins and user code) are executed
        in a single priority-ordered sequence.

        Args:
            app: FastAPI application instance
        """
        logger = get_app_logger()

        try:
            # Execute all startup hooks in priority order (10, 20, 30, ...)
            sorted_hooks = sorted(self.startup_hooks, key=lambda x: x[1])

            if not sorted_hooks:
                logger.debug("No startup hooks registered")
                return

            logger.debug(
                f"Executing {len(sorted_hooks)} startup hooks in priority order..."
            )

            for hook, priority in sorted_hooks:
                hook_name = getattr(hook, "__name__", "anonymous_hook")
                logger.debug(
                    f"⚡ Executing startup hook: {hook_name} (priority: {priority})"
                )

                try:
                    await hook(app)
                    logger.debug(f"✅ Startup hook {hook_name} completed")
                except Exception as e:
                    logger.error(
                        f"❌ Startup hook {hook_name} failed: {e}", exc_info=True
                    )
                    raise  # Re-raise to fail fast

        except Exception as e:
            logger.error(f"❌ Startup sequence failed: {e}", exc_info=True)
            raise

    async def _execute_all_shutdown_hooks(self, app: FastAPI) -> None:
        """
        Execute all shutdown hooks in reverse priority order.

        This replaces the old plugin-specific shutdown execution with a unified
        approach where all hooks are executed in reverse priority order,
        with error isolation to prevent shutdown cascading failures.

        Args:
            app: FastAPI application instance
        """
        logger = get_app_logger()

        # Execute shutdown hooks in reverse priority order (90, 70, 50, 30, 20, 10)
        sorted_hooks = sorted(self.shutdown_hooks, key=lambda x: x[1], reverse=True)

        if not sorted_hooks:
            logger.debug("No shutdown hooks registered")
            return

        logger.debug(
            f"Executing {len(sorted_hooks)} shutdown hooks in reverse priority order..."
        )

        for hook, priority in sorted_hooks:
            hook_name = getattr(hook, "__name__", "anonymous_hook")
            try:
                logger.debug(
                    f"🛑 Executing shutdown hook: {hook_name} (priority: {priority})"
                )
                await hook(app)
                logger.debug(f"✅ Shutdown hook {hook_name} completed")
            except Exception as e:
                # Don't re-raise in shutdown - log and continue with other hooks
                logger.error(
                    f"❌ Error in shutdown hook {hook_name}: {e}", exc_info=True
                )
