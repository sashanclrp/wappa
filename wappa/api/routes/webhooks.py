"""
Universal webhook routes for the Wappa framework.

Provides webhook endpoints that delegate accepted payloads to the Inbound Runtime.
Routes handle only HTTP concerns while the controller adapts app-state dependencies.
"""

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from wappa.api.controllers import WebhookController
from wappa.core.events import (
    WappaEventDispatcher,
    webhook_url_factory,
)
from wappa.core.inbound import SIGNATURE_HEADER
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
            400: {"description": "Bad Request - unroutable authenticated payload"},
            401: {"description": "Unauthorized - missing or invalid Meta signature"},
            403: {"description": "Forbidden - GET verify token mismatch"},
            503: {"description": "Inbox Directory or runtime dependency unavailable"},
            500: {"description": "Internal Server Error"},
        },
    )

    @router.get("/inboxes/{platform}")
    async def verify_webhook(
        request: Request,
        platform: str,
        hub_mode: str = Query(None, alias="hub.mode"),
        hub_verify_token: str = Query(None, alias="hub.verify_token"),
        hub_challenge: str = Query(None, alias="hub.challenge"),
    ) -> PlainTextResponse:
        """
        Handle webhook verification (challenge-response) for messaging platforms.

        Delegates verification policy to WebhookController while handling HTTP concerns.
        GET verification uses the Meta Application Configuration verify token
        only; it never reads the Inbox Directory or the App Secret.

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

    @router.post("/inboxes/{platform}")
    async def process_webhook(
        request: Request,
        platform: str,
    ) -> dict[str, str]:
        """
        Accept one authenticated Meta callback batch.

        The route reads the exact request bytes once and hands them, with the
        ``X-Hub-Signature-256`` header, to the controller. Authentication
        happens before JSON parsing; the route parses nothing itself.
        """
        body = await request.body()
        return await webhook_controller.process_webhook(
            request=request,
            platform=platform,
            body=body,
            signature=request.headers.get(SIGNATURE_HEADER),
        )

    @router.get("/inboxes/{platform}/status")
    async def webhook_status(
        request: Request,
        platform: str,
    ) -> dict[str, Any]:
        """
        Get webhook status and configuration for a specific platform.

        Useful for debugging and monitoring webhook health.

        Args:
            request: FastAPI request object
            platform: The messaging platform

        Returns:
            Dict with webhook status information
        """
        logger.info("Status check for %s webhook", platform)

        try:
            platform_type = PlatformType(platform.lower())
        except ValueError as exc:
            raise HTTPException(
                status_code=400, detail=f"Unsupported platform: {platform}"
            ) from exc

        webhook_url = webhook_url_factory.generate_webhook_url(platform_type)

        controller_status = webhook_controller.get_health_status()

        return {
            "status": "active",
            "platform": platform,
            "webhook_url": webhook_url,
            "verify_url": webhook_url,
            "controller_status": controller_status,
            "supported_platforms": [p.value.lower() for p in PlatformType],
        }

    @router.get("/platforms")
    async def list_supported_platforms() -> dict[str, Any]:
        """
        List all supported platforms and their webhook patterns.

        Returns:
            Dict with all supported platforms and URL patterns
        """
        patterns = webhook_url_factory.get_supported_platforms()

        return {
            "supported_platforms": list(patterns.keys()),
            "platform_details": patterns,
            "webhook_pattern": "/webhook/inboxes/{platform}",
            "verify_pattern": "/webhook/inboxes/{platform}",
            "features": [
                "Challenge-response verification",
                "Multi-platform support",
                "Multi-inbox support",
                "Event dispatcher routing",
                "Default status/error handling",
            ],
        }

    return router
