"""Builder-delegating setters of ``Wappa`` (plugins, hooks, middleware, routers, config).

A mixin so ``wappa_app.py`` keeps construction, the event handler, ``asgi`` and
``run``; every method here is still a public ``Wappa`` method.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, Self

from fastapi import APIRouter
from pydantic import BaseModel

from ..schemas.core.types import PlatformType
from .factory.wappa_builder import WappaBuilder
from .logging.logger import get_app_logger

if TYPE_CHECKING:
    from wappa.core.config.meta_application import MetaApplicationConfig
    from wappa.domain.inbox.ports import IInboxDirectorySource
    from wappa.domain.inbox.routing import InboxRoutingMode
    from wappa.domain.interfaces.identity_resolver import IIdentityResolver
    from wappa.webhooks.core.webhook_interfaces import CustomWebhook

    from .factory.plugin import WappaPlugin


class _WappaConfigMixin:
    """Wappa state the delegating setters use."""

    _builder: WappaBuilder

    def add_plugin(self, plugin: WappaPlugin) -> Self:
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
            from wappa.core.plugins import PostgresDatabasePlugin

            app = Wappa(cache="redis")
            app.add_plugin(PostgresDatabasePlugin("postgresql://..."))
            app.set_event_handler(MyEventHandler())
            app.run()
        """
        self._builder.add_plugin(plugin)

        logger = get_app_logger()
        logger.debug(f"Plugin added to Wappa: {plugin.__class__.__name__}")

        return self

    def add_startup_hook(self, hook: Callable, priority: int = 50) -> Self:
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

    def add_shutdown_hook(self, hook: Callable, priority: int = 50) -> Self:
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
        self, middleware_class: type, priority: int = 50, **kwargs: Any
    ) -> Self:
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

    def add_router(self, router: APIRouter, **kwargs: Any) -> Self:
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

    def register_webhook_field(
        self,
        field_name: str,
        *,
        parser: type[BaseModel] | Callable[[dict[str, Any]], BaseModel],
        handler: Callable[[CustomWebhook], Awaitable[None]],
        platform: PlatformType,
    ) -> Self:
        """
        Register a typed handler for a non-built-in Meta webhook field.

        Convenience wrapper around :meth:`WappaBuilder.register_webhook_field`
        for apps using the simple ``Wappa(...)`` constructor instead of the
        builder. See ``WappaBuilder.register_webhook_field`` for details.
        """
        self._builder.register_webhook_field(
            field_name, parser=parser, handler=handler, platform=platform
        )

        logger = get_app_logger()
        logger.debug(f"Custom webhook field registered: {field_name}")

        return self

    def set_identity_resolver(self, resolver: IIdentityResolver) -> Self:
        """
        Register an :class:`IIdentityResolver` for cache scoping.

        Convenience wrapper around
        :meth:`WappaBuilder.with_identity_resolver` for apps using the
        simple ``Wappa(...)`` constructor instead of the builder.

        When omitted, Wappa uses the passthrough resolver (recipient used
        as ``user_id`` unchanged), preserving pre-0.6.1 behavior.

        Args:
            resolver: Application-provided identity resolver instance.

        Returns:
            Self for method chaining.

        Example::

            class CanonicalIdResolver(IIdentityResolver):
                async def resolve(self, recipient: str, *, inbox_ref: InboxRef) -> str:
                    return await db.lookup_canonical_id(inbox_ref, recipient)

            app = Wappa()
            app.set_identity_resolver(CanonicalIdResolver())
        """
        self._builder.with_identity_resolver(resolver)

        logger = get_app_logger()
        logger.debug(f"Identity resolver set: {resolver.__class__.__name__}")

        return self

    def set_inbox_directory_source(self, source: IInboxDirectorySource) -> Self:
        """Register the Host's read-only Inbox Directory source (explicit mode)."""
        self._builder.with_inbox_directory_source(source)

        logger = get_app_logger()
        logger.debug(f"Inbox Directory source set: {source.__class__.__name__}")

        return self

    def set_inbox_routing(self, mode: InboxRoutingMode | str) -> Self:
        """Select ``legacy`` or ``explicit`` Inbox routing."""
        self._builder.with_inbox_routing(mode)
        return self

    def set_meta_application_config(self, config: MetaApplicationConfig) -> Self:
        """Supply the one Meta Application Configuration explicitly."""
        self._builder.with_meta_application_config(config)
        return self

    def configure(self, **overrides: Any) -> Self:
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
