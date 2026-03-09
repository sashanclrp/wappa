"""
Auth Middleware

Starlette BaseHTTPMiddleware that delegates authentication to a pluggable strategy.
Supports SSE query-param token promotion, path exclusions, and scope protection.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ..logging.logger import get_app_logger
from .strategy import AuthStrategy


class AuthMiddleware(BaseHTTPMiddleware):
    """
    Authentication middleware that delegates to an AuthStrategy.

    Features:
        - Path exclusion (prefix match) for public endpoints
        - Optional path protection scope (only protect matching paths)
        - SSE query-param token promotion (?token=... → Bearer header)
        - User info exposed on request.state when enabled

    Args:
        app: ASGI application
        strategy: AuthStrategy implementation
        protect: If set, only protect paths matching these prefixes
        exclude: Path prefixes to skip authentication
        sse_token_param: Query parameter name for SSE token promotion
        expose_user: Whether to set request.state.auth_user/auth_metadata
    """

    def __init__(
        self,
        app,  # noqa: ANN001
        strategy: AuthStrategy,
        protect: list[str] | None = None,
        exclude: list[str] | None = None,
        sse_token_param: str = "token",
        expose_user: bool = True,
    ) -> None:
        super().__init__(app)
        self.strategy = strategy
        self.protect = protect
        self.exclude = exclude or []
        self.sse_token_param = sse_token_param
        self.expose_user = expose_user

    async def dispatch(self, request: Request, call_next) -> Response:  # noqa: ANN001
        """Authenticate the request or pass through based on path rules."""
        logger = get_app_logger()
        path = request.url.path

        # Check exclusions (prefix match) → pass through
        if any(path.startswith(prefix) for prefix in self.exclude):
            return await call_next(request)

        # Check protection scope → if set and path doesn't match, pass through
        if self.protect and not any(path.startswith(prefix) for prefix in self.protect):
            return await call_next(request)

        # SSE token promotion: read ?token= param and inject as Bearer header
        if path.startswith("/api/sse") and not request.headers.get("authorization"):
            token_value = request.query_params.get(self.sse_token_param)
            if token_value:
                # Build new headers list (don't mutate original scope)
                new_headers = list(request.scope["headers"])
                new_headers.append((b"authorization", f"Bearer {token_value}".encode()))
                request.scope["headers"] = new_headers

        # Authenticate
        try:
            result = await self.strategy.authenticate(request)
        except Exception as e:
            logger.error(f"Auth strategy error: {e}", exc_info=True)
            return JSONResponse(
                status_code=500,
                content={"detail": "Internal authentication error"},
            )

        if not result.authenticated:
            return JSONResponse(
                status_code=401,
                content={"detail": result.error or "Unauthorized"},
            )

        # Expose user info on request.state
        if self.expose_user:
            request.state.auth_user = result.user
            request.state.auth_metadata = result.metadata

        return await call_next(request)
