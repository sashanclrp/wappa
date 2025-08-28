"""
Owner middleware for extracting owner ID from webhook URLs.

Simple middleware that extracts the owner_id from webhook URL paths and sets it in context.
This replaces the over-complicated tenant middleware with a focused single-purpose solution.
"""

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from wappa.core.config.settings import settings
from wappa.core.logging.context import set_request_context
from wappa.core.logging.logger import get_logger

logger = get_logger(__name__)


class OwnerMiddleware(BaseHTTPMiddleware):
    """
    Middleware to extract owner_id from webhook URLs and set in context.

    URL Pattern: /webhook/messenger/{owner_id}/whatsapp
    Purpose: Extract owner_id and set it in the context system.

    That's it. Nothing more.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        """Extract owner_id from URL path and set in context."""
        owner_id = None

        try:
            # ENHANCED DEBUGGING: Log all request details
            logger.debug(f"🔍 OwnerMiddleware processing: {request.method} {request.url.path}")
            
            # Extract owner_id from webhook URL pattern: /webhook/messenger/{owner_id}/{platform}
            if request.url.path.startswith("/webhook/"):
                logger.debug(f"🎯 Webhook request detected: {request.url.path}")
                path_parts = request.url.path.strip("/").split("/")
                logger.debug(f"📋 Path parts: {path_parts} (length: {len(path_parts)})")
                
                if len(path_parts) >= 4:
                    # path_parts = ["webhook", "messenger", "owner_id", "platform"]
                    owner_id = path_parts[2]
                    logger.debug(f"🔑 Extracted owner_id from URL: '{owner_id}'")

                    # Validate basic format
                    if self._is_valid_owner_id(owner_id):
                        # Set owner_id context from URL
                        set_request_context(owner_id=owner_id)
                        logger.debug(f"✅ Owner ID context set successfully: {owner_id}")
                    else:
                        logger.error(f"❌ Invalid owner ID format: {owner_id}")
                        raise HTTPException(
                            status_code=400, detail=f"Invalid owner ID: {owner_id}"
                        )
                else:
                    logger.warning(f"⚠️ Webhook URL does not have enough parts: {path_parts}")

            # For non-webhook endpoints, use default owner from settings
            elif not self._is_public_endpoint(request.url.path):
                default_owner = settings.owner_id
                set_request_context(owner_id=default_owner)
                logger.debug(f"Using default owner ID: {default_owner}")

            # Process request
            response = await call_next(request)
            return response

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error in owner middleware: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Internal server error") from e

    def _is_valid_owner_id(self, owner_id: str) -> bool:
        """Validate owner ID format."""
        if not owner_id or not isinstance(owner_id, str):
            return False

        # Basic format validation - alphanumeric and underscores only
        if not owner_id.replace("_", "").replace("-", "").isalnum():
            return False

        # Length validation
        return not (len(owner_id) < 3 or len(owner_id) > 50)

    def _is_public_endpoint(self, path: str) -> bool:
        """Check if endpoint is public and doesn't require owner context."""
        public_paths = [
            "/",
            "/health",
            "/health/detailed",
            "/docs",
            "/redoc",
            "/openapi.json",
        ]
        return any(path.startswith(p) for p in public_paths)
