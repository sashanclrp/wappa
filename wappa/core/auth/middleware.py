"""
Auth Middleware

Starlette BaseHTTPMiddleware that delegates authentication to a pluggable strategy.
Operates in one of two mutually exclusive modes (enforced by AuthPlugin):

- **Exclude mode**: All paths require auth except those in the exclude list.
- **Protect mode**: Only paths in the protect list require auth.

Also supports SSE query-param token promotion and user info exposure.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ..logging.logger import get_app_logger
from .strategy import AuthStrategy


class AuthMiddleware(BaseHTTPMiddleware):
    """
    Authentication middleware that delegates to an AuthStrategy.

    Operates in one of two mutually exclusive modes:

    - **Exclude mode** (``exclude`` set, ``protect`` is None):
      Every path requires auth unless it matches an exclude prefix.
    - **Protect mode** (``protect`` set, ``exclude`` is None):
      Only paths matching a protect prefix require auth.

    The two modes cannot be combined — AuthPlugin validates this at init.

    Additional features:
        - SSE query-param token promotion (?token=... → Bearer header)
        - User info exposed on request.state when enabled

    Args:
        app: ASGI application
        strategy: AuthStrategy implementation
        protect: Protect-mode prefix list (mutually exclusive with exclude)
        exclude: Exclude-mode prefix list (mutually exclusive with protect)
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
        self.exclude = exclude
        self.sse_token_param = sse_token_param
        self.expose_user = expose_user

    def _requires_auth(self, path: str, request: Request | None = None) -> bool:
        """Determine whether the given path requires authentication."""
        if self.protect is not None:
            return any(path.startswith(prefix) for prefix in self.protect)

        if self.exclude and any(path.startswith(prefix) for prefix in self.exclude):
            return False

        if request is not None:
            public = getattr(request.app.state, "public_route_prefixes", ())
            if any(path.startswith(prefix) for prefix in public):
                return False

        return True

    async def dispatch(self, request: Request, call_next) -> Response:  # noqa: ANN001
        """Authenticate the request or pass through based on path rules."""
        logger = get_app_logger()
        path = request.url.path

        if not self._requires_auth(path, request):
            return await call_next(request)

        # SSE token promotion: read ?token= param and inject as Bearer header
        if path.startswith("/api/sse") and not request.headers.get("authorization"):
            token_value = request.query_params.get(self.sse_token_param)
            if token_value:
                # Build new headers list (don't mutate original scope)
                new_headers = list(request.scope["headers"])
                new_headers.append((b"authorization", f"Bearer {token_value}".encode()))
                request.scope["headers"] = new_headers
                # Invalidate cached Headers so strategy sees the promoted token
                if hasattr(request, "_headers"):
                    del request._headers

        # Authenticate
        strategy_name = type(self.strategy).__name__
        try:
            result = await self.strategy.authenticate(request)
        except Exception as e:
            logger.error("Auth strategy error: %s", e, exc_info=True)
            return JSONResponse(
                status_code=500,
                content={
                    "detail": (
                        f"Authentication strategy '{strategy_name}' raised "
                        f"{type(e).__name__} — check auth configuration and credentials"
                    )
                },
            )

        if not result.authenticated:
            return JSONResponse(
                status_code=401,
                content={
                    "detail": result.error
                    or f"Authentication failed — provide valid credentials for strategy '{strategy_name}'"
                },
            )

        # Expose user info on request.state
        if self.expose_user:
            request.state.auth_user = result.user
            request.state.auth_metadata = result.metadata

        return await call_next(request)
