"""Wire a built Wappa ``FastAPI`` app's ``app.state`` from a ``WappaBuilder``.

Holds the messenger middleware list, identity resolver, Inbox runtime, Meta
application config, public route prefixes and the installed Platforms.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import FastAPI

from ...platforms import build_platforms
from ..config.meta_application import resolve_meta_application_config
from ..config.settings import settings
from ..logging.logger import get_app_logger
from .inbox_assembly import assemble_inbox_runtime, resolve_routing_mode

if TYPE_CHECKING:
    from .wappa_builder import WappaBuilder


def install_app_state(app: FastAPI, builder: WappaBuilder) -> None:
    """Publish the builder's configuration on ``app.state``."""
    # Expose the registered messenger middleware as mutable app state so
    # plugins can append runtime-constructed middleware from their
    # startup hooks (e.g., SSEEventsPlugin needs the live SSEEventHub).
    # Startup hooks all complete before the first request, so the list
    # is effectively frozen once serving begins.
    app.state.messenger_middleware = list(builder.messenger_middleware)

    # Expose the identity resolver (if registered) so DI dependencies
    # such as ``get_template_state_service`` can pick it up. Absence
    # falls back to PassthroughIdentityResolver inside the dependency.
    if builder.identity_resolver is not None:
        app.state.identity_resolver = builder.identity_resolver

    inbox_runtime = assemble_inbox_runtime(
        mode=resolve_routing_mode(builder.inbox_routing_mode, settings),
        source=builder.inbox_directory_source,
        settings=settings,
        cache_type=builder.persistence_backend,
    )
    app.state.inbox_runtime = inbox_runtime
    if inbox_runtime.directory is not None:
        directory = inbox_runtime.directory

        async def _reset_inbox_directory_cache(_app: FastAPI) -> None:
            cleared = await directory.reset_cache()
            get_app_logger().info(
                "Inbox Directory cache cleared at startup (%s rows); "
                "Inboxes reload from the source on first use",
                cleared,
            )

        # After cache infrastructure (20), before Host hooks (50).
        builder.startup_hooks.append((_reset_inbox_directory_cache, 25))
    app.state.inbox_routing_mode = inbox_runtime.mode
    app.state.meta_application_config = resolve_meta_application_config(
        builder.meta_application_config,
        settings,
        callback_mounted=builder._webhook_callback_mounted,
    )
    app.state.public_route_prefixes = tuple(builder._public_prefixes)
    # The installed Platforms, bound to this app's extension fields.
    app.state.platforms = build_platforms(builder.field_registry)
