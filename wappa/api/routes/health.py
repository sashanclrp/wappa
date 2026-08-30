"""
Health check endpoints for the Wappa framework.

Root health never depends on an Inbox header or on Inbox Directory health.
It reports the selected Inbox Routing Mode, whether the Inbox Directory and
Meta callback configuration are present, and safe dependency facts. It never
returns tokens, envelopes, App Secrets, encryption keys, or raw exceptions.
"""

import time
from typing import Any

from fastapi import APIRouter, Request

from wappa.core.config.settings import settings
from wappa.core.logging.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(tags=["Health"])


def _inbox_runtime_status(request: Request) -> dict[str, Any]:
    runtime = getattr(request.app.state, "inbox_runtime", None)
    if runtime is None:
        return {
            "inbox_routing_mode": None,
            "inbox_directory_configured": False,
            "legacy_default_inbox_configured": False,
            "legacy_default_inbox_id": None,
        }
    status: dict[str, Any] = runtime.health_status()
    return status


def _meta_callback_status(request: Request) -> dict[str, Any]:
    config = getattr(request.app.state, "meta_application_config", None)
    if config is None:
        return {
            "configured": False,
            "app_secret_configured": False,
            "verify_token_configured": False,
        }
    return {"configured": True, **config.health_status()}


async def _directory_reachability(request: Request) -> str | None:
    runtime = getattr(request.app.state, "inbox_runtime", None)
    directory = getattr(runtime, "directory", None)
    if directory is None:
        return None
    try:
        return "reachable" if await directory.check_health() else "unreachable"
    except Exception as exc:  # never leak the raw exception
        logger.warning("Inbox Directory health probe failed: %s", type(exc).__name__)
        return "unreachable"


@router.get("/health")
async def health_check(request: Request) -> dict[str, Any]:
    """Basic health check endpoint."""
    start_time = time.time()
    runtime_status = _inbox_runtime_status(request)
    response_time = time.time() - start_time

    health_data = {
        "status": "healthy",
        "timestamp": time.time(),
        "response_time_ms": round(response_time * 1000, 2),
        "environment": {
            "environment": settings.environment,
            "version": settings.version,
            "log_level": settings.log_level,
            **runtime_status,
        },
        "services": {"logging": "operational", "configuration": "loaded"},
    }

    logger.info(
        "Health check completed - Status: %s, Response Time: %sms",
        health_data["status"],
        health_data["response_time_ms"],
    )
    return health_data


@router.get("/health/detailed")
async def detailed_health_check(request: Request) -> dict[str, Any]:
    """Detailed health check with configuration and dependency readiness."""
    start_time = time.time()
    runtime_status = _inbox_runtime_status(request)
    directory_reachability = await _directory_reachability(request)
    response_time = time.time() - start_time

    detailed_data = {
        "status": "healthy",
        "timestamp": time.time(),
        "response_time_ms": round(response_time * 1000, 2),
        "application": {
            "name": "Wappa Framework",
            "version": settings.version,
            "environment": settings.environment,
            "is_development": settings.is_development,
        },
        "configuration": {
            "log_level": settings.log_level,
            "log_dir": settings.log_dir,
            "api_version": settings.api_version,
            "time_zone": settings.time_zone,
            "port": settings.port,
            **runtime_status,
        },
        "platform_configs": {
            "whatsapp": {
                "inbox_routing_mode": runtime_status["inbox_routing_mode"],
                "inbox_directory": {
                    "configured": runtime_status["inbox_directory_configured"],
                    "reachability": directory_reachability,
                },
                "legacy_default_inbox": {
                    "configured": runtime_status["legacy_default_inbox_configured"],
                    "inbox_id": runtime_status["legacy_default_inbox_id"],
                },
                "meta_callback": _meta_callback_status(request),
            },
            "redis": {"configured": settings.has_redis},
            "openai": {"configured": bool(settings.openai_api_key)},
        },
    }

    logger.info("Detailed health check completed")
    return detailed_data
