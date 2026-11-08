"""Shared discovery and limits under /api/{platform}, using static Platform adapter facts."""

from fastapi import APIRouter, Depends, Request

from wappa.api.dependencies.inbox_context import route_platform
from wappa.domain.messenger_discovery import MessengerDiscovery
from wappa.platforms import PLATFORMS
from wappa.schemas.core.types import PlatformType


def platform_discovery(
    request: Request, platform: PlatformType = Depends(route_platform)
) -> MessengerDiscovery:
    platforms = getattr(request.app.state, "platforms", None) or PLATFORMS
    return platforms[platform].discovery


router = APIRouter(tags=["Messaging - Discovery"])


@router.get("/capabilities")
async def capabilities(
    discovery: MessengerDiscovery = Depends(platform_discovery),
) -> MessengerDiscovery:
    return discovery


@router.get("/messages/limits")
async def message_limits(
    discovery: MessengerDiscovery = Depends(platform_discovery),
) -> dict:
    return discovery.message_limits.model_dump(exclude_none=True)


@router.get("/media/limits")
async def media_limits(
    discovery: MessengerDiscovery = Depends(platform_discovery),
) -> dict:
    return {
        **discovery.media_http_limits,
        "formats": {
            family: limit.model_dump(mode="json")
            for family, limit in discovery.media_limits.items()
        },
    }
