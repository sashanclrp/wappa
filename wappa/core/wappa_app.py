"""
Main Wappa application class.

This is the core class that developers use to create and run their WhatsApp applications.
The class now uses WappaBuilder internally for unified plugin-based architecture.
"""

from typing import TYPE_CHECKING, Any

from fastapi import FastAPI

from wappa.api.routes.webhooks import create_webhook_router

from ._wappa_config import _WappaConfigMixin
from .config.settings import settings
from .events import APIEventDispatcher, WappaEventDispatcher
from .factory.wappa_builder import WappaBuilder
from .logging.logger import get_app_logger
from .plugins.wappa_core_plugin import WappaCorePlugin
from .server import run_dev_mode, run_production
from .types import CacheType, CacheTypeOptions, validate_cache_type

if TYPE_CHECKING:
    from wappa.core.config.meta_application import MetaApplicationConfig
    from wappa.domain.inbox.ports import IInboxDirectorySource
    from wappa.domain.inbox.routing import InboxRoutingMode

    from .events import WappaEventHandler


# Traditional lifespan management has been moved to WappaCorePlugin
# This enables unified plugin-based architecture for all Wappa applications


class Wappa(_WappaConfigMixin):
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
        app.add_plugin(PostgresDatabasePlugin(...))
        app.add_startup_hook(my_startup_func)
        app.set_event_handler(MyEventHandler())
        app.run()
    """

    def __init__(
        self,
        cache: CacheTypeOptions = "memory",
        config: dict | None = None,
        inbox_directory_source: "IInboxDirectorySource | None" = None,
        inbox_routing: "InboxRoutingMode | str | None" = None,
        meta_application_config: "MetaApplicationConfig | None" = None,
        route_profile: str | None = None,
        include_template_transport_api: bool | None = None,
        include_outbound_transport_api: bool | None = None,
        include_media_management_api: bool | None = None,
        include_media_upload_api: bool | None = None,
        include_state_handler_api: bool | None = None,
        include_comment_controls_api: bool | None = None,
    ):
        """
        Initialize Wappa application with plugin-based architecture.

        Automatically creates WappaBuilder with WappaCorePlugin and adds
        cache-specific plugins based on the cache type.

        Args:
            cache: Cache type ('memory', 'redis', 'json')
            config: Optional configuration overrides for FastAPI app
            inbox_directory_source: The Host's read-only ``IInboxDirectorySource``
                for explicit multi-Inbox routing. Wappa builds and runs the
                Inbox Directory over it; the Host never replaces the directory.
            inbox_routing: ``legacy`` (default) uses the single settings-backed
                Inbox from ``META_WHATSAPP_ACCESS_TOKEN``/``META_WHATSAPP_PHONE_NUMBER_ID``/``META_WHATSAPP_BUSINESS_ACCOUNT_ID``.
                ``explicit`` uses the Inbox Directory and rejects those
                variables. The modes never fall back to one another.
            meta_application_config: Explicit Meta Application Configuration.
                Omit it to let Wappa read ``META_APP_SECRET`` and
                ``META_WEBHOOK_VERIFY_TOKEN`` from the environment; configuring
                both is a startup error.
            route_profile: Which HTTP capability groups to mount.
                "standalone" (default) is the surface a standalone Wappa app
                has always had. "embedded" omits every route that sends,
                deletes, or rewrites state — use it when your application owns
                an authenticated boundary. Reads, lookups, media upload, and
                every `wappa.messaging` service stay either way.
            include_template_transport_api: Mount Template mutation routes.
                Off under both profiles unless asked for.
            include_outbound_transport_api: Mount ordinary send routes.
                Passing False without a profile implies "embedded", so the
                other unauthenticated mutations go with it.
            include_media_management_api: Mount DELETE /media/{id}, which
                destroys a media asset on the platform.
            include_media_upload_api: Mount POST /media/upload. Kept under the
                embedded profile because hosts still need Wappa's upload path;
                pass False to close it.
            include_state_handler_api: Mount /state-handlers/*, which reads,
                overwrites, and deletes the cached conversational state of any
                recipient named in the request.
            include_comment_controls_api: Mount the comment reply, hide,
                unhide, delete and comments-enabled routes (Platforms with
                ICommentControls; today Instagram). On under standalone, off
                under embedded.

            Every include_* option defaults to None, meaning "take it from the
            profile". Naming one explicitly always wins.

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
        self._builder.with_persistence_backend(self.cache_type.value)
        if inbox_directory_source is not None:
            self._builder.with_inbox_directory_source(inbox_directory_source)
        if inbox_routing is not None:
            self._builder.with_inbox_routing(inbox_routing)
        if meta_application_config is not None:
            self._builder.with_meta_application_config(meta_application_config)
        self._core_plugin = WappaCorePlugin(
            cache_type=self.cache_type,
            route_profile=route_profile,
            include_template_transport_api=include_template_transport_api,
            include_outbound_transport_api=include_outbound_transport_api,
            include_media_management_api=include_media_management_api,
            include_media_upload_api=include_media_upload_api,
            include_state_handler_api=include_state_handler_api,
            include_comment_controls_api=include_comment_controls_api,
        )
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
        ensuring proper multi-inbox support and correct inbox isolation.

        Args:
            handler: WappaEventHandler instance to handle webhooks
        """
        # Store handler reference - dependencies will be injected per request
        self._event_handler = handler
        self._publish_event_handler()

        logger = get_app_logger()
        logger.debug(f"Event handler set: {handler.__class__.__name__}")

    def _publish_event_handler(self) -> None:
        """Make the handler prototype reachable by ``Scheduling.from_app(app)``."""
        if self._app is not None and self._event_handler is not None:
            self._app.state.wappa_event_handler = self._event_handler

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
            app = (builder
                .add_plugin(PostgresDatabasePlugin(...))
                .add_plugin(RedisPlugin())
                .build())

            # Use with Wappa for event handling
            wappa = Wappa()
            wappa.set_app(app)
            wappa.set_event_handler(MyHandler())
            wappa.run()
        """
        self._app = app
        self._publish_event_handler()

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

        # Create dispatchers and register webhook router through the builder
        # so the builder owns the complete route tree.
        webhook_dispatcher = WappaEventDispatcher(
            self._event_handler, field_registry=self._builder.field_registry
        )
        api_dispatcher = APIEventDispatcher(self._event_handler)
        webhook_router = create_webhook_router(webhook_dispatcher)
        self._builder.add_router(webhook_router, public=True)
        self._builder.mount_webhook_callback()

        app = self._builder.build()

        # Store API dispatcher in app.state for dependency injection
        app.state.api_event_dispatcher = api_dispatcher
        app.state.wappa_event_handler = self._event_handler

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

    def run(
        self, host: str = "0.0.0.0", port: int | None = None, **kwargs: Any
    ) -> None:
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

    def _run_production(self, host: str, port: int, **kwargs: Any) -> None:
        """Run in production mode without auto-reload."""
        run_production(self, host, port, **kwargs)

    def _run_dev_mode(self, host: str, port: int, **kwargs: Any) -> None:
        """
        Run in development mode with uvicorn auto-reload.

        Uses uvicorn with import string for proper reload functionality.
        Requires module-level 'app' variable containing Wappa instance.
        """
        run_dev_mode(self, host, port, **kwargs)
