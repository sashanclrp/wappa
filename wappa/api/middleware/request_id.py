"""Request correlation ID middleware.

Assigns every inbound HTTP request a correlation ID, publishes it to the
request-scoped logging context, echoes it on the response, and clears the
context once the response has been produced.

This is the outermost Wappa middleware so the ID is available to every other
middleware, route, and logger — including responses produced by the error
handler.
"""

from __future__ import annotations

from uuid import uuid4

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from wappa.core.logging.context import bind_request_id, reset_request_id

DEFAULT_REQUEST_ID_HEADER = "X-Request-ID"

# Hard cap on inbound header reuse so a hostile client cannot inject
# unbounded values into every downstream log line.
_MAX_INBOUND_LENGTH = 128


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Attach a correlation ID to each request, response, and log record.

    Args:
        header_name: Header read for an inbound ID and written on the response.
        trust_inbound: When True (default), a well-formed inbound header value
            is reused so IDs survive across service hops. Set to False at an
            untrusted edge to always generate a fresh ID.
    """

    def __init__(
        self,
        app,
        header_name: str = DEFAULT_REQUEST_ID_HEADER,
        trust_inbound: bool = True,
    ) -> None:
        super().__init__(app)
        self.header_name = header_name
        self.trust_inbound = trust_inbound

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = self._resolve_request_id(request)

        request.state.request_id = request_id
        token = bind_request_id(request_id)
        try:
            response = await call_next(request)
        finally:
            reset_request_id(token)

        response.headers[self.header_name] = request_id
        return response

    def _resolve_request_id(self, request: Request) -> str:
        if self.trust_inbound:
            inbound = (request.headers.get(self.header_name) or "").strip()
            if self._is_acceptable(inbound):
                return inbound
        return uuid4().hex

    @staticmethod
    def _is_acceptable(value: str) -> bool:
        """Accept short, printable, single-line identifiers only."""
        if not value or len(value) > _MAX_INBOUND_LENGTH:
            return False
        return all(char.isprintable() for char in value)
