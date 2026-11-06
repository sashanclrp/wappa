"""
WappaBuilder - Extensible FastAPI Application Factory

This module provides the WappaBuilder class that enables users to create
highly customized FastAPI applications using a plugin-based architecture.
"""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, cast

from fastapi import FastAPI

from ...domain.inbox.ports import IInboxDirectorySource
from ...domain.inbox.routing import InboxRoutingMode
from ...domain.interfaces.identity_resolver import IIdentityResolver
from ...platforms import BUILTIN_FIELDS
from ..config.meta_application import (
    MetaApplicationConfig,
)
from ..events.field_registry import FieldHandlerRegistry
from ..logging.logger import get_app_logger
from ..messaging.pipeline import MiddlewareEntry
from ._registration import _BuilderRegistrationMixin
from .app_state import install_app_state
from .lifespan import run_shutdown_hooks, run_startup_hooks

if TYPE_CHECKING:
    from .plugin import WappaPlugin


class WappaBuilder(_BuilderRegistrationMixin):
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
        app = (builder
            .add_plugin(PostgresDatabasePlugin("postgresql://..."))
            .add_plugin(RedisPlugin())
            .add_middleware(CORSMiddleware, allow_origins=["*"])
            .configure(title="My Wappa App")
            .build())
    """

    def __init__(self) -> None:
        """Initialize WappaBuilder with empty configuration."""
        self.plugins: list[WappaPlugin] = []
        self.middlewares: list[tuple[type, dict, int]] = []  # (class, kwargs, priority)
        self.routers: list[tuple[Any, dict]] = []  # (router, include_kwargs)
        self.startup_hooks: list[tuple[Callable, int]] = []  # (hook, priority)
        self.shutdown_hooks: list[tuple[Callable, int]] = []  # (hook, priority)
        self.messenger_middleware: list[MiddlewareEntry] = []  # (middleware, priority)
        self.config_overrides: dict[str, Any] = {}
        self.field_registry: FieldHandlerRegistry = FieldHandlerRegistry(BUILTIN_FIELDS)
        self.identity_resolver: IIdentityResolver | None = None
        self.inbox_directory_source: IInboxDirectorySource | None = None
        self.inbox_routing_mode: InboxRoutingMode | None = None
        self.meta_application_config: MetaApplicationConfig | None = None
        self.persistence_backend: str = "memory"
        self._webhook_callback_mounted = False
        self._public_prefixes: list[str] = []

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

    def add_router(
        self, router: Any, *, public: bool = False, **kwargs: Any
    ) -> "WappaBuilder":
        """
        Add a router to the application.

        Args:
            router: FastAPI router to include
            public: Mark this router's combined include/router prefix as public
                (excluded from auth, at path-segment boundaries).
                Plugins that serve unauthenticated routes (health checks,
                webhook ingress) should set this to ``True`` so the auth
                middleware automatically skips them.
            **kwargs: Arguments for app.include_router()

        Returns:
            Self for method chaining
        """
        self.routers.append((router, kwargs))
        if public:
            prefix = kwargs.get("prefix", "") + getattr(router, "prefix", "")
            if prefix:
                self._public_prefixes.append(prefix)
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
        async def unified_lifespan(app: FastAPI) -> AsyncIterator[None]:
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
        default_config: dict[str, Any] = {
            "title": "Wappa Application",
            "description": "WhatsApp Business application built with Wappa framework",
            "version": "1.0.0",
            "lifespan": unified_lifespan,
        }
        default_config.update(self.config_overrides)

        app = FastAPI(**default_config)
        logger.debug(f"Created FastAPI app: {default_config['title']}")

        install_app_state(app, self)

        # Step 3: Add all middleware via app.add_middleware()
        # Sort by priority (reverse order because FastAPI adds middleware in reverse)
        sorted_middlewares = sorted(self.middlewares, key=lambda x: x[2], reverse=True)
        for middleware_class, kwargs, priority in sorted_middlewares:
            app.add_middleware(cast(Any, middleware_class), **kwargs)
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
        """Run the registered startup hooks in priority order (see ``lifespan``)."""
        await run_startup_hooks(self.startup_hooks, app)

    async def _execute_all_shutdown_hooks(self, app: FastAPI) -> None:
        """Run the registered shutdown hooks in reverse priority order."""
        await run_shutdown_hooks(self.shutdown_hooks, app)
