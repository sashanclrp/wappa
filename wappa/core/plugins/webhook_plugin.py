"""
Webhook Plugin

Specialized plugin for adding webhook endpoints to Wappa applications.
Perfect for integrating payment providers like Wompi, Stripe, PayPal, etc.
"""

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Request

from ...core.logging.logger import get_app_logger

if TYPE_CHECKING:
    from fastapi import FastAPI

    from ...core.factory.wappa_builder import WappaBuilder


class WebhookPlugin:
    """
    Plugin for adding specialized webhook endpoints.

    This plugin makes it easy to add webhook endpoints for payment providers,
    third-party services, or any custom webhook handlers. It provides a clean
    interface for handling webhook requests with proper routing and error handling.

    Perfect for your Wompi payment provider use case and other webhook integrations.

    Example:
        # Wompi webhook
        wompi_plugin = WebhookPlugin(
            "wompi",
            wompi_webhook_handler,
            prefix="/webhook/payment"
        )

        # Stripe webhook
        stripe_plugin = WebhookPlugin(
            "stripe",
            stripe_webhook_handler,
            prefix="/webhook/payment"
        )

        # Custom webhook
        custom_plugin = WebhookPlugin(
            "notifications",
            notification_handler,
            prefix="/webhook/custom"
        )
    """

    def __init__(
        self,
        provider: str,
        handler: Callable,
        prefix: str = None,
        methods: list[str] = None,
        include_tenant_id: bool = True,
        **route_kwargs: Any,
    ):
        """
        Initialize webhook plugin.

        Args:
            provider: Provider name (e.g., 'wompi', 'stripe', 'paypal')
            handler: Async callable to handle webhook requests
                    Signature: async def handler(request: Request, tenant_id: str, provider: str) -> dict
            prefix: URL prefix for the webhook (defaults to /webhook/{provider})
            methods: HTTP methods to accept (defaults to ['POST'])
            include_tenant_id: Whether to include tenant_id in the URL path
            **route_kwargs: Additional arguments for FastAPI route decorator
        """
        self.provider = provider
        self.handler = handler
        self.prefix = prefix or f"/webhook/{provider}"
        self.methods = methods or ["POST"]
        self.include_tenant_id = include_tenant_id
        self.route_kwargs = route_kwargs

        self.router = APIRouter()

    async def configure(self, builder: "WappaBuilder") -> None:
        """
        Configure the webhook plugin with WappaBuilder.

        This method creates the FastAPI router with the webhook endpoints
        and adds it to the builder's router collection.

        Args:
            builder: WappaBuilder instance
        """
        logger = get_app_logger()

        # Create webhook endpoint based on configuration
        if self.include_tenant_id:
            # Pattern: /webhook/{provider}/{tenant_id}
            endpoint_path = "/{tenant_id}"

            # Create the endpoint handler
            @self.router.api_route(
                endpoint_path,
                methods=self.methods,
                tags=[f"{self.provider.title()} Webhooks"],
                **self.route_kwargs,
            )
            async def webhook_endpoint_with_tenant(request: Request, tenant_id: str):
                """Webhook endpoint with tenant ID in path."""
                return await self.handler(request, tenant_id, self.provider)

        else:
            # Pattern: /webhook/{provider}
            endpoint_path = "/"

            # Create the endpoint handler
            @self.router.api_route(
                endpoint_path,
                methods=self.methods,
                tags=[f"{self.provider.title()} Webhooks"],
                **self.route_kwargs,
            )
            async def webhook_endpoint_without_tenant(request: Request):
                """Webhook endpoint without tenant ID in path."""
                # Call handler with None for tenant_id
                return await self.handler(request, None, self.provider)

        # Add status endpoint for webhook health checks
        @self.router.get(
            "/status" if not self.include_tenant_id else "/{tenant_id}/status",
            tags=[f"{self.provider.title()} Webhooks"],
            response_model=dict,
        )
        async def webhook_status(request: Request, tenant_id: str = None):
            """Get webhook status and configuration."""
            return {
                "status": "active",
                "provider": self.provider,
                "tenant_id": tenant_id,
                "webhook_url": str(request.url).replace("/status", ""),
                "methods": self.methods,
                "plugin": "WebhookPlugin",
            }

        # Add the router to builder
        builder.add_router(self.router, prefix=self.prefix)

        logger.debug(
            f"WebhookPlugin configured for {self.provider} - "
            f"Prefix: {self.prefix}, Methods: {self.methods}, "
            f"Include tenant: {self.include_tenant_id}"
        )

    async def startup(self, app: "FastAPI") -> None:
        """
        Execute webhook plugin startup logic.

        Currently no startup tasks needed for webhook endpoints,
        but this provides a hook for future functionality like
        webhook registration with external services.

        Args:
            app: FastAPI application instance
        """
        logger = get_app_logger()

        # Log webhook registration for visibility
        base_url = "https://your-domain.com"  # This would be configurable
        if self.include_tenant_id:
            webhook_url = f"{base_url}{self.prefix}/{{tenant_id}}"
        else:
            webhook_url = f"{base_url}{self.prefix}/"

        logger.info(
            f"WebhookPlugin for {self.provider} ready - "
            f"URL pattern: {webhook_url}, Methods: {self.methods}"
        )

    async def shutdown(self, app: "FastAPI") -> None:
        """
        Execute webhook plugin cleanup logic.

        Currently no cleanup needed for webhook endpoints,
        but this provides a hook for future functionality like
        webhook deregistration with external services.

        Args:
            app: FastAPI application instance
        """
        logger = get_app_logger()
        logger.debug(f"WebhookPlugin for {self.provider} shutting down")


# Convenience functions for common webhook patterns


def create_payment_webhook_plugin(
    provider: str, handler: Callable, **kwargs: Any
) -> WebhookPlugin:
    """
    Create a webhook plugin optimized for payment providers.

    Uses the pattern /webhook/payment/{tenant_id}/{provider} which matches
    your existing payment webhook structure.

    Args:
        provider: Payment provider name (wompi, stripe, paypal, etc.)
        handler: Webhook handler function
        **kwargs: Additional WebhookPlugin arguments

    Returns:
        Configured WebhookPlugin for payment webhooks

    Example:
        wompi_plugin = create_payment_webhook_plugin("wompi", wompi_handler)
    """
    return WebhookPlugin(
        provider=provider,
        handler=handler,
        prefix=f"/webhook/payment/{provider}",
        include_tenant_id=True,
        **kwargs,
    )


def create_service_webhook_plugin(
    service: str, handler: Callable, include_tenant: bool = False, **kwargs: Any
) -> WebhookPlugin:
    """
    Create a webhook plugin for general service integrations.

    Args:
        service: Service name
        handler: Webhook handler function
        include_tenant: Whether to include tenant ID in URL
        **kwargs: Additional WebhookPlugin arguments

    Returns:
        Configured WebhookPlugin for service webhooks

    Example:
        notification_plugin = create_service_webhook_plugin(
            "notifications",
            notification_handler
        )
    """
    return WebhookPlugin(
        provider=service,
        handler=handler,
        prefix=f"/webhook/{service}",
        include_tenant_id=include_tenant,
        **kwargs,
    )
