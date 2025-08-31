"""
Universal webhook routes for the Wappa framework.

Provides webhook endpoints that delegate to WebhookController for business logic.
Routes handle only HTTP concerns (validation, responses) while controller
handles dependency injection and webhook processing.
"""

from fastapi import APIRouter, HTTPException, Query, Request

from wappa.api.controllers import WebhookController
from wappa.core.events import (
    WappaEventDispatcher,
    WebhookEndpointType,
    webhook_url_factory,
)
from wappa.core.logging.logger import get_logger
from wappa.schemas.core.types import PlatformType


def create_webhook_router(event_dispatcher: WappaEventDispatcher) -> APIRouter:
    """
    Create webhook router with controller delegation.

    This factory function creates the webhook routes that delegate all business logic
    to the WebhookController, maintaining clean separation of concerns.

    Args:
        event_dispatcher: WappaEventDispatcher instance with user's event handler

    Returns:
        APIRouter configured with webhook endpoints
    """
    # Create controller instance for this router
    webhook_controller = WebhookController(event_dispatcher)

    router = APIRouter(
        prefix="/webhook",
        tags=["Webhooks"],
        responses={
            400: {"description": "Bad Request - Invalid webhook payload"},
            401: {"description": "Unauthorized - Invalid tenant credentials"},
            403: {"description": "Forbidden - Webhook verification failed"},
            500: {"description": "Internal Server Error"},
        },
    )

    @router.get("/messenger/{platform}/verify")
    async def verify_webhook(
        request: Request,
        platform: str,
        hub_mode: str = Query(None, alias="hub.mode"),
        hub_verify_token: str = Query(None, alias="hub.verify_token"),
        hub_challenge: str = Query(None, alias="hub.challenge"),
    ):
        """
        Handle webhook verification (challenge-response) for messaging platforms.

        Delegates all business logic to WebhookController while handling HTTP concerns.

        Args:
            request: FastAPI request object
            platform: The messaging platform (whatsapp, telegram, teams, instagram)
            hub_mode: Verification mode (usually "subscribe")
            hub_verify_token: Token provided by platform for verification
            hub_challenge: Challenge string to return if verification succeeds

        Returns:
            PlainTextResponse with challenge string if verification succeeds
        """
        # Delegate to controller (handles business logic and tenant extraction)
        return await webhook_controller.verify_webhook(
            request=request,
            platform=platform,
            hub_mode=hub_mode,
            hub_verify_token=hub_verify_token,
            hub_challenge=hub_challenge,
        )

    @router.get("/messenger/{tenant_id}/{platform}")
    async def verify_webhook_at_tenant_url(
        request: Request,
        tenant_id: str,
        platform: str,
        hub_mode: str = Query(None, alias="hub.mode"),
        hub_verify_token: str = Query(None, alias="hub.verify_token"),
        hub_challenge: str = Query(None, alias="hub.challenge"),
    ):
        """
        Handle webhook verification at the same URL used for processing.

        WhatsApp and other platforms send verification requests to the same URL
        they use for webhook processing. This handles GET requests with verification.
        """
        # Delegate to controller (tenant_id will be extracted from URL by middleware)
        return await webhook_controller.verify_webhook(
            request=request,
            platform=platform,
            hub_mode=hub_mode,
            hub_verify_token=hub_verify_token,
            hub_challenge=hub_challenge,
        )

    @router.post("/messenger/{tenant_id}/{platform}")
    async def process_webhook(
        request: Request,
        tenant_id: str,
        platform: str,
    ):
        """
        Process incoming webhook payload from a messaging platform.

        Delegates business logic to WebhookController while handling HTTP concerns.
        The controller creates per-request dependencies with correct tenant isolation.

        Args:
            request: FastAPI request object
            tenant_id: Tenant identifier for multi-tenant support (extracted by middleware)
            platform: The messaging platform (whatsapp, telegram, teams, instagram)

        Returns:
            Dict with status confirmation
        """
        # Parse JSON payload (HTTP concern - handled in route)
        try:
            payload = await request.json()
        except Exception as e:
            logger = get_logger(__name__)
            logger.error(f"Failed to parse webhook payload: {e}")
            raise HTTPException(status_code=400, detail="Invalid JSON payload") from e

        # Delegate to controller (handles all business logic and dependency injection)
        return await webhook_controller.process_webhook(
            request=request,
            platform=platform,
            payload=payload,
        )

    @router.get("/messenger/{tenant_id}/{platform}/status")
    async def webhook_status(
        request: Request,
        tenant_id: str,
        platform: str,
    ):
        """
        Get webhook status and configuration for a specific platform.

        Useful for debugging and monitoring webhook health.

        Args:
            request: FastAPI request object
            tenant_id: Tenant identifier
            platform: The messaging platform

        Returns:
            Dict with webhook status information
        """
        logger = get_logger(__name__)
        logger.info(f"Status check for {platform} webhook - tenant: {tenant_id}")

        # Generate webhook URLs for this platform and tenant
        try:
            platform_type = PlatformType(platform.lower())
        except ValueError as e:
            raise HTTPException(
                status_code=400, detail=f"Unsupported platform: {platform}"
            ) from e

        webhook_url = webhook_url_factory.generate_webhook_url(platform_type, tenant_id)
        verify_url = webhook_url_factory.generate_webhook_url(
            platform_type, "", WebhookEndpointType.VERIFY
        )

        # Get controller health status
        controller_status = webhook_controller.get_health_status()

        return {
            "status": "active",
            "platform": platform,
            "tenant_id": tenant_id,
            "webhook_url": webhook_url,
            "verify_url": verify_url,
            "controller_status": controller_status,
            "supported_platforms": [p.value.lower() for p in PlatformType],
        }

    @router.get("/platforms")
    async def list_supported_platforms():
        """
        List all supported platforms and their webhook patterns.

        Returns:
            Dict with all supported platforms and URL patterns
        """
        patterns = webhook_url_factory.get_supported_platforms()

        return {
            "supported_platforms": list(patterns.keys()),
            "platform_details": patterns,
            "webhook_pattern": "/webhook/messenger/{tenant_id}/{platform}",
            "verify_pattern": "/webhook/messenger/{platform}/verify",
            "features": [
                "Challenge-response verification",
                "Multi-platform support",
                "Multi-tenant support",
                "Event dispatcher routing",
                "Default status/error handling",
            ],
        }

    return router
