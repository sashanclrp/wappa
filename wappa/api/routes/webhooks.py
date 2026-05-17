"""
Universal webhook routes for the Wappa framework.

Provides webhook endpoints that delegate accepted payloads to the Inbound Runtime.
Routes handle only HTTP concerns while the controller adapts app-state dependencies.
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

    Args:
        event_dispatcher: WappaEventDispatcher instance with user's event handler

    Returns:
        APIRouter configured with webhook endpoints
    """
    # Create controller instance for this router
    webhook_controller = WebhookController(event_dispatcher)
    logger = get_logger(__name__)

    router = APIRouter(
        prefix="/webhook",
        tags=["Webhooks"],
        responses={
            400: {"description": "Bad Request - Invalid webhook payload"},
            401: {"description": "Unauthorized - Invalid inbox credentials"},
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

        Delegates verification policy to WebhookController while handling HTTP concerns.

        Args:
            request: FastAPI request object
            platform: The messaging platform (whatsapp, telegram, teams, instagram)
            hub_mode: Verification mode (usually "subscribe")
            hub_verify_token: Token provided by platform for verification
            hub_challenge: Challenge string to return if verification succeeds

        Returns:
            PlainTextResponse with challenge string if verification succeeds
        """
        return await webhook_controller.verify_webhook(
            request=request,
            platform=platform,
            hub_mode=hub_mode,
            hub_verify_token=hub_verify_token,
            hub_challenge=hub_challenge,
        )

    @router.get("/inboxes/{inbox_id}/{platform}")
    async def verify_webhook_at_inbox_url(
        request: Request,
        inbox_id: str,
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
        return await webhook_controller.verify_webhook(
            request=request,
            platform=platform,
            hub_mode=hub_mode,
            hub_verify_token=hub_verify_token,
            hub_challenge=hub_challenge,
        )

    @router.post("/inboxes/{inbox_id}/{platform}")
    async def process_webhook(
        request: Request,
        inbox_id: str,
        platform: str,
    ):
        """
        Process incoming webhook payload from a messaging platform.

        Parses JSON and delegates accepted payloads to the Inbound Runtime.

        Args:
            request: FastAPI request object
            inbox_id: Inbox identifier (extracted by middleware)
            platform: The messaging platform (whatsapp, telegram, teams, instagram)

        Returns:
            Dict with status confirmation
        """
        try:
            payload = await request.json()
        except Exception as exc:
            logger.error("Failed to parse webhook payload: %s", exc)
            raise HTTPException(status_code=400, detail="Invalid JSON payload") from exc

        return await webhook_controller.process_webhook(
            request=request,
            inbox_id=inbox_id,
            platform=platform,
            payload=payload,
        )

    @router.get("/inboxes/{inbox_id}/{platform}/status")
    async def webhook_status(
        request: Request,
        inbox_id: str,
        platform: str,
    ):
        """
        Get webhook status and configuration for a specific platform.

        Useful for debugging and monitoring webhook health.

        Args:
            request: FastAPI request object
            inbox_id: Inbox identifier
            platform: The messaging platform

        Returns:
            Dict with webhook status information
        """
        logger.info("Status check for %s webhook - inbox: %s", platform, inbox_id)

        try:
            platform_type = PlatformType(platform.lower())
        except ValueError as exc:
            raise HTTPException(
                status_code=400, detail=f"Unsupported platform: {platform}"
            ) from exc

        webhook_url = webhook_url_factory.generate_webhook_url(platform_type, inbox_id)
        verify_url = webhook_url_factory.generate_webhook_url(
            platform_type, "", WebhookEndpointType.VERIFY
        )

        controller_status = webhook_controller.get_health_status()

        return {
            "status": "active",
            "platform": platform,
            "inbox_id": inbox_id,
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
            "webhook_pattern": "/webhook/inboxes/{inbox_id}/{platform}",
            "verify_pattern": "/webhook/messenger/{platform}/verify",
            "features": [
                "Challenge-response verification",
                "Multi-platform support",
                "Multi-inbox support",
                "Event dispatcher routing",
                "Default status/error handling",
            ],
        }

    return router
