"""
Request and response logging middleware with tenant and user context.

Provides comprehensive logging for monitoring, debugging, and audit trails for Wappa framework.
"""

import time
from typing import Any

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware for logging HTTP requests and responses with context.

    Features:
    - Tenant-aware logging
    - Request/response timing
    - Privacy-conscious logging (excludes sensitive data)
    - Structured log format for monitoring
    """

    def __init__(self, app, log_requests: bool = True, log_responses: bool = True):
        super().__init__(app)
        self.log_requests = log_requests
        self.log_responses = log_responses
        # Sensitive headers to exclude from logs
        self.sensitive_headers = {
            "authorization",
            "x-api-key",
            "cookie",
            "set-cookie",
            "x-access-token",
            "x-auth-token",
            "x-whatsapp-hub-signature",
        }

    async def dispatch(self, request: Request, call_next) -> Response:
        """Process request with comprehensive logging."""
        # Start timing
        start_time = time.time()

        # Get logger with context (context is set by OwnerMiddleware and processors)
        from wappa.core.logging.logger import get_logger

        logger = get_logger(__name__)

        # Log incoming request
        if self.log_requests and not self._should_skip_logging(request.url.path):
            await self._log_request(request, logger)

        # Process request
        response = await call_next(request)

        # Calculate processing time
        process_time = time.time() - start_time

        # Add processing time to response headers (in development)
        from wappa.core.config.settings import settings

        if settings.is_development:
            response.headers["X-Process-Time"] = str(round(process_time * 1000, 2))

        # Log response
        if self.log_responses and not self._should_skip_logging(request.url.path):
            await self._log_response(request, response, process_time, logger)

        return response

    def _extract_user_id(self, request: Request) -> str:
        """
        Extract user ID from request context.

        This will be populated by webhook processing or API authentication.
        For now, returns 'unknown' as we haven't implemented user extraction yet.
        """
        return getattr(request.state, "user_id", "unknown")

    def _should_skip_logging(self, path: str) -> bool:
        """Check if we should skip logging for this path."""
        # Skip logging for health checks and static assets to reduce noise
        skip_paths = ["/health", "/docs", "/redoc", "/openapi.json", "/favicon.ico"]
        return any(path.startswith(skip_path) for skip_path in skip_paths)

    async def _log_request(self, request: Request, logger) -> None:
        """Log incoming request with sanitized information."""
        # Safely read body for logging (only for small payloads)
        body_info = await self._get_request_body_info(request)

        # Sanitized headers (exclude sensitive ones)
        safe_headers = {
            k: v
            for k, v in request.headers.items()
            if k.lower() not in self.sensitive_headers
        }

        log_data = {
            "method": request.method,
            "url": str(request.url),
            "path": request.url.path,
            "query_params": dict(request.query_params),
            "headers": safe_headers,
            "client_host": request.client.host if request.client else "unknown",
            "user_agent": request.headers.get("user-agent", "unknown"),
            **body_info,
        }

        logger.info(
            f"Incoming {request.method} {request.url.path}", extra={"request": log_data}
        )

    async def _log_response(
        self, request: Request, response: Response, process_time: float, logger
    ) -> None:
        """Log response with timing and status information."""
        # Determine log level based on status code
        status_code = response.status_code

        if status_code >= 500:
            log_level = "error"
        elif status_code >= 400:
            log_level = "warning"
        else:
            log_level = "info"

        log_data = {
            "status_code": status_code,
            "process_time_ms": round(process_time * 1000, 2),
            "content_length": response.headers.get("content-length", "unknown"),
            "content_type": response.headers.get("content-type", "unknown"),
        }

        message = (
            f"Response {status_code} for {request.method} {request.url.path} "
            f"({log_data['process_time_ms']}ms)"
        )

        # Log with appropriate level
        getattr(logger, log_level)(message, extra={"response": log_data})

    async def _get_request_body_info(self, request: Request) -> dict[str, Any]:
        """
        Get safe information about request body.

        Returns body size and type information without logging sensitive content.
        """
        try:
            # Only read body for non-streaming requests and if small enough
            content_length = request.headers.get("content-length")
            content_type = request.headers.get("content-type", "unknown")

            body_info = {"content_type": content_type, "content_length": content_length}

            # For webhook endpoints, we might want to log structure but not content
            if request.url.path.startswith("/webhook/"):
                body_info["is_webhook"] = True
                # Don't log webhook payload content for privacy/security
                body_info["body_logged"] = False
            else:
                # For API endpoints, we could log small bodies in development
                from wappa.core.config.settings import settings

                if (
                    settings.is_development
                    and content_length
                    and int(content_length) < 1000
                ):  # Only log small payloads
                    # Read body (this consumes the stream, so we need to be careful)
                    # For now, just log that we could log it
                    body_info["body_loggable"] = True
                else:
                    body_info["body_logged"] = False

            return body_info

        except Exception as e:
            # If we can't read body info, just return basic info
            return {
                "content_type": request.headers.get("content-type", "unknown"),
                "body_read_error": str(e),
            }
