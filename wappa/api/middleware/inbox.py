"""
Inbox middleware for extracting inbox ID from webhook URLs.

Simple middleware that extracts the inbox_id from webhook URL paths and sets it in context.
"""

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from wappa.core.config.settings import settings
from wappa.core.logging.context import set_request_context
from wappa.core.logging.logger import get_logger

logger = get_logger(__name__)


class InboxMiddleware(BaseHTTPMiddleware):
    """
    Middleware to extract inbox_id from webhook URLs and set in context.

    URL Pattern: /webhook/inboxes/{inbox_id}/whatsapp
    Purpose: Extract inbox_id and set it in the context system.

    That's it. Nothing more.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        """Extract inbox_id from URL path and set in context."""
        inbox_id = None

        try:
            # Extract inbox_id from webhook URL pattern: /webhook/inboxes/{inbox_id}/{platform}
            if request.url.path.startswith("/webhook/"):
                path_parts = request.url.path.strip("/").split("/")

                if len(path_parts) >= 4:
                    # path_parts = ["webhook", "inboxes", "inbox_id", "platform"]
                    inbox_id = path_parts[2]

                    if self._is_valid_inbox_id(inbox_id):
                        set_request_context(inbox_id=inbox_id)
                    else:
                        logger.error("Invalid inbox ID format: %s", inbox_id)
                        raise HTTPException(
                            status_code=400, detail=f"Invalid inbox ID: {inbox_id}"
                        )
                else:
                    logger.warning(
                        "Webhook URL does not have enough parts: %s", path_parts
                    )

            # For non-webhook endpoints (API routes), use default inbox from settings.
            elif not self._is_public_endpoint(request.url.path):
                set_request_context(inbox_id=settings.inbox_id)

            return await call_next(request)

        except HTTPException:
            raise
        except Exception as e:
            logger.error("Error in inbox middleware: %s", e, exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=(
                    f"InboxMiddleware failed while resolving inbox context for "
                    f"path '{request.url.path}': {type(e).__name__}: {e}"
                ),
            ) from e

    def _is_valid_inbox_id(self, inbox_id: str) -> bool:
        """Validate inbox ID format."""
        if not inbox_id or not isinstance(inbox_id, str):
            return False

        if not inbox_id.replace("_", "").replace("-", "").isalnum():
            return False

        return not (len(inbox_id) < 3 or len(inbox_id) > 50)

    def _is_public_endpoint(self, path: str) -> bool:
        """Check if endpoint is public and doesn't require inbox context."""
        public_paths = {"/"}
        public_prefixes = ("/health", "/docs", "/redoc", "/openapi.json")
        return path in public_paths or any(
            path.startswith(prefix) for prefix in public_prefixes
        )
