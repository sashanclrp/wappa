"""
Global error handling middleware with tenant and context awareness.

Provides structured error responses and comprehensive logging for Wappa framework.
"""

import traceback
from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from wappa.core.logging.logger import get_logger


class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    """
    Global error handling middleware with tenant-aware logging.

    Catches all unhandled exceptions and provides structured error responses
    while maintaining security by not exposing internal details in production.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        """Process request with comprehensive error handling."""
        try:
            response = await call_next(request)
            return response

        except HTTPException as http_exc:
            # HTTP exceptions are handled by FastAPI, but we log them with context
            await self._log_http_exception(request, http_exc)
            raise  # Re-raise to let FastAPI handle the response

        except Exception as exc:
            # Handle unexpected exceptions
            return await self._handle_unexpected_exception(request, exc)

    async def _log_http_exception(self, request: Request, exc: HTTPException) -> None:
        """Log HTTP exceptions with tenant context."""
        logger = get_logger(__name__)
        logger.warning(
            f"HTTP {exc.status_code} - {request.method} {request.url.path} - "
            f"Detail: {exc.detail}"
        )

    async def _handle_unexpected_exception(
        self, request: Request, exc: Exception
    ) -> JSONResponse:
        """Handle unexpected exceptions with proper logging and response."""
        logger = get_logger(__name__)

        # Log the full exception with context
        logger.error(
            f"Unhandled exception in {request.method} {request.url.path}: {exc}",
            exc_info=True,
        )

        # Determine error response based on environment
        if self._is_webhook_endpoint(request.url.path):
            # Webhook endpoints need specific error handling
            return await self._create_webhook_error_response(exc)
        else:
            # Regular API endpoints
            return await self._create_api_error_response(exc)

    def _is_webhook_endpoint(self, path: str) -> bool:
        """Check if the request is to a webhook endpoint."""
        return path.startswith("/webhook/")

    async def _create_webhook_error_response(self, exc: Exception) -> JSONResponse:
        """
        Create error response for webhook endpoints.

        Webhook providers expect specific response formats and status codes.
        """
        error_response = {
            "status": "error",
            "message": "Webhook processing failed",
            "type": "webhook_error",
        }

        # In development, add more details
        from wappa.core.config.settings import settings

        if settings.is_development:
            error_response["debug"] = {
                "exception_type": type(exc).__name__,
                "exception_message": str(exc),
            }

        return JSONResponse(status_code=500, content=error_response)

    async def _create_api_error_response(self, exc: Exception) -> JSONResponse:
        """Create error response for regular API endpoints."""
        from wappa.core.config.settings import settings

        # Base error response
        error_response: dict[str, Any] = {
            "detail": "Internal server error",
            "type": "internal_error",
            "timestamp": self._get_current_timestamp(),
        }

        # Add development-specific debugging information
        if settings.is_development:
            error_response["debug"] = {
                "exception_type": type(exc).__name__,
                "exception_message": str(exc),
                "traceback": traceback.format_exc().split("\n"),
            }

        return JSONResponse(status_code=500, content=error_response)

    def _get_current_timestamp(self) -> float:
        """Get current timestamp for error responses."""
        import time

        return time.time()


class ValidationErrorHandler:
    """
    Custom handler for Pydantic validation errors.

    Provides more user-friendly validation error messages.
    """

    @staticmethod
    def format_validation_error(exc: any) -> dict[str, Any]:
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
