"""Per-request isolation of the ambient Inbox logging context.

Inbox selection no longer happens here. Inbox-dependent routes resolve one
``InboxExecutionContext`` through a FastAPI dependency; local-only routes
never touch the Inbox Directory. This middleware only guarantees that an
Inbox value bound during one request cannot survive into the next request
served by the same worker.
"""

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from wappa.api.dependencies.inbox_context import INBOX_ID_HEADER
from wappa.core.logging.context import bind_inbox_context, reset_inbox_context

__all__ = ["INBOX_ID_HEADER", "InboxMiddleware"]


class InboxMiddleware(BaseHTTPMiddleware):
    """Reset the ambient Inbox context around every request."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        token = bind_inbox_context(None)
        try:
            return await call_next(request)
        finally:
            reset_inbox_context(token)
