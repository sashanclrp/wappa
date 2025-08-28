"""
Health check endpoints for the Wappa framework.
"""

import time
from typing import Any

from fastapi import APIRouter

from wappa.core.config.settings import settings
from wappa.core.logging.logger import get_api_logger

logger = get_api_logger()
router = APIRouter(tags=["Health"])


@router.get("/health")
async def health_check() -> dict[str, Any]:
    """
    Basic health check endpoint.

    Returns application status, environment information, and response time.
    """
    start_time = time.time()

    # Basic health indicators
    is_healthy = True

    # Calculate response time
    response_time = time.time() - start_time

    health_data = {
        "status": "healthy" if is_healthy else "unhealthy",
        "timestamp": time.time(),
        "response_time_ms": round(response_time * 1000, 2),
        "environment": {
            "environment": settings.environment,
            "version": "2.0.0",
            "log_level": settings.log_level,
            "owner_id": settings.owner_id,
        },
        "services": {"logging": "operational", "configuration": "loaded"},
    }

    logger.info(
        f"Health check completed - Status: {health_data['status']}, "
        f"Response Time: {health_data['response_time_ms']}ms"
    )

    return health_data


@router.get("/health/detailed")
async def detailed_health_check() -> dict[str, Any]:
    """
    Detailed health check with configuration information.

    Useful for debugging and monitoring.
    """
    start_time = time.time()

    # Calculate response time
    response_time = time.time() - start_time

    detailed_data = {
        "status": "healthy",
        "timestamp": time.time(),
        "response_time_ms": round(response_time * 1000, 2),
        "application": {
            "name": "Wappa Framework",
            "version": "2.0.0",
            "environment": settings.environment,
            "is_development": settings.is_development,
        },
        "configuration": {
            "log_level": settings.log_level,
            "log_dir": settings.log_dir,
            "owner_id": settings.owner_id,
            "api_version": settings.api_version,
            "time_zone": settings.time_zone,
            "port": settings.port,
        },
        "platform_configs": {
            "whatsapp": {
                "configured": bool(settings.wp_access_token and settings.wp_phone_id),
                "webhook_token_configured": bool(
                    settings.whatsapp_webhook_verify_token
                ),
                "phone_id": settings.wp_phone_id,
                "business_id": settings.wp_bid,
            },
            "redis": {
                "configured": settings.has_redis,
                "url": settings.redis_url if settings.has_redis else None,
            },
            "openai": {"configured": bool(settings.openai_api_key)},
        },
    }

    logger.info("Detailed health check completed")

    return detailed_data
