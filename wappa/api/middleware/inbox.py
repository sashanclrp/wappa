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
            logger.debug(
                f"🔍 InboxMiddleware processing: {request.method} {request.url.path}"
            )

            # Extract inbox_id from webhook URL pattern: /webhook/inboxes/{inbox_id}/{platform}
            if request.url.path.startswith("/webhook/"):
                logger.debug(f"🎯 Webhook request detected: {request.url.path}")
                path_parts = request.url.path.strip("/").split("/")
                logger.debug(f"📋 Path parts: {path_parts} (length: {len(path_parts)})")

                if len(path_parts) >= 4:
                    # path_parts = ["webhook", "inboxes", "inbox_id", "platform"]
                    inbox_id = path_parts[2]
                    logger.debug(f"🔑 Extracted inbox_id from URL: '{inbox_id}'")

                    if self._is_valid_inbox_id(inbox_id):
                        set_request_context(inbox_id=inbox_id)
                        logger.debug(
                            f"✅ Inbox ID context set successfully: {inbox_id}"
                        )
                    else:
                        logger.error(f"❌ Invalid inbox ID format: {inbox_id}")
                        raise HTTPException(
                            status_code=400, detail=f"Invalid inbox ID: {inbox_id}"
                        )
                else:
                    logger.warning(
                        f"⚠️ Webhook URL does not have enough parts: {path_parts}"
                    )

            # For non-webhook endpoints (API routes), use default inbox from settings.
            else:
                is_public = self._is_public_endpoint(request.url.path)
                logger.debug(f"🔍 Non-webhook route - is_public: {is_public}")

                if not is_public:
                    default_inbox = settings.inbox_id
                    logger.debug(f"🔑 Setting context - inbox: {default_inbox}")
                    set_request_context(inbox_id=default_inbox)
                    logger.debug(
                        f"✅ API route context set - inbox: {default_inbox}"
                    )

            response = await call_next(request)
            return response

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error in inbox middleware: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Internal server error") from e

    def _is_valid_inbox_id(self, inbox_id: str) -> bool:
        """Validate inbox ID format."""
        if not inbox_id or not isinstance(inbox_id, str):
            return False

        if not inbox_id.replace("_", "").replace("-", "").isalnum():
            return False

        return not (len(inbox_id) < 3 or len(inbox_id) > 50)

    def _is_public_endpoint(self, path: str) -> bool:
        """Check if endpoint is public and doesn't require inbox context."""
        if path == "/":
            return True

        public_prefixes = [
            "/health",
            "/docs",
            "/redoc",
            "/openapi.json",
        ]
        return any(path.startswith(prefix) for prefix in public_prefixes)
