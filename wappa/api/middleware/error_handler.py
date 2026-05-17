"""
Global error handling middleware with inbox and context awareness.

Provides structured error responses and comprehensive logging for Wappa framework.
"""

import time
import traceback
from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from wappa.core.config.settings import settings
from wappa.core.logging.logger import get_logger


class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    """
    Global error handling middleware with inbox-aware logging.

    Catches all unhandled exceptions and provides structured error responses
    while maintaining security by not exposing internal details in production.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        """Process request with comprehensive error handling."""
        logger = get_logger(__name__)
        try:
            return await call_next(request)

        except HTTPException as http_exc:
            logger.warning(
                "HTTP %s - %s %s - Detail: %s",
                http_exc.status_code,
                request.method,
                request.url.path,
                http_exc.detail,
            )
            raise

        except Exception as exc:
            logger.error(
                "Unhandled exception in %s %s: %s",
                request.method,
                request.url.path,
                exc,
                exc_info=True,
            )
            if self._is_webhook_endpoint(request.url.path):
                return await self._create_webhook_error_response(exc)
            return await self._create_api_error_response(exc)

    def _is_webhook_endpoint(self, path: str) -> bool:
        """Check if the request is to a webhook endpoint."""
        return path.startswith("/webhook/")

    async def _create_webhook_error_response(self, exc: Exception) -> JSONResponse:
        """Create error response for webhook endpoints."""
        error_response: dict[str, Any] = {
            "status": "error",
            "message": "Webhook processing failed",
            "type": "webhook_error",
        }

        if settings.is_development:
            error_response["debug"] = {
                "exception_type": type(exc).__name__,
                "exception_message": str(exc),
            }

        return JSONResponse(status_code=500, content=error_response)

    async def _create_api_error_response(self, exc: Exception) -> JSONResponse:
        """Create error response for regular API endpoints."""
        error_response: dict[str, Any] = {
            "detail": "Internal server error",
            "type": "internal_error",
            "timestamp": time.time(),
        }

        if settings.is_development:
            error_response["debug"] = {
                "exception_type": type(exc).__name__,
                "exception_message": str(exc),
                "traceback": traceback.format_exc().split("\n"),
            }

        return JSONResponse(status_code=500, content=error_response)


class ValidationErrorHandler:
    """
    Custom handler for Pydantic validation errors.

    Provides more user-friendly validation error messages.
    """

    @staticmethod
    def format_validation_error(exc: Any) -> dict[str, Any]:
        """Format Pydantic validation errors for API responses."""
        errors = []

        for error in exc.errors():
            errors.append(
                {
                    "field": " -> ".join(str(loc) for loc in error["loc"]),
                    "message": error["msg"],
                    "type": error["type"],
                }
            )

        return {
            "detail": "Validation failed",
            "type": "validation_error",
            "errors": errors,
        }
