"""
Wappa Plugin Protocol

Defines the interface that all Wappa plugins must implement for consistent
integration with the WappaBuilder factory system.
"""

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from fastapi import FastAPI

    from .wappa_builder import WappaBuilder


class WappaPlugin(Protocol):
    """
    Universal plugin interface for extending Wappa functionality.

    All plugins must implement these three lifecycle methods:
    1. configure: Called during WappaBuilder setup to register middleware/routes
    2. startup: Called during FastAPI application startup
    3. shutdown: Called during FastAPI application shutdown

    This protocol ensures consistent plugin behavior and proper resource management.
    """

    def configure(self, builder: "WappaBuilder") -> None:
        """
        Configure the plugin with the WappaBuilder.

        This method is called during the build phase, before the FastAPI app
        is created. Use this to register middleware, routes, and other components
        that need to be set up before the app starts.

        This method is synchronous because it only registers components with the builder.
        Actual async initialization should be done in the startup() method.

        Args:
            builder: WappaBuilder instance to configure
        """
        ...

    async def startup(self, app: "FastAPI") -> None:
        """
        Execute plugin startup logic.

        This method is called during FastAPI application startup. Use this
        for initializing connections, setting up resources, health checks,
        and any other startup tasks.

        Args:
            app: FastAPI application instance
        """
        ...

    async def shutdown(self, app: "FastAPI") -> None:
        """
        Execute plugin cleanup logic.

        This method is called during FastAPI application shutdown. Use this
        for closing connections, cleaning up resources, and any other
        shutdown tasks. Should be the reverse of startup operations.

        Args:
            app: FastAPI application instance
        """
        ...
