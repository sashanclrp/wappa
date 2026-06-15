"""
Wappa Plugin Protocol

Defines the interface that all Wappa plugins must implement for consistent
integration with the WappaBuilder factory system.
"""

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from .wappa_builder import WappaBuilder


class WappaPlugin(Protocol):
    """
    Universal plugin interface for extending Wappa functionality.

    Plugins implement a single lifecycle method:

    - ``configure``: Called during ``WappaBuilder.build()`` to register
      middleware, routes, startup hooks, shutdown hooks, and any other
      components.  Async initialization and cleanup are handled by hooks
      registered here via ``builder.add_startup_hook`` /
      ``builder.add_shutdown_hook`` — the framework never calls
      ``startup()`` or ``shutdown()`` directly on the plugin.
    """

    def configure(self, builder: "WappaBuilder") -> None:
        """
        Configure the plugin with the WappaBuilder.

        Called during the build phase, before the FastAPI app is created.
        Register middleware, routes, and lifecycle hooks here.  The method
        is synchronous because it only registers components; async work
        belongs in hooks registered via ``builder.add_startup_hook``.

        Args:
            builder: WappaBuilder instance to configure
        """
        ...
