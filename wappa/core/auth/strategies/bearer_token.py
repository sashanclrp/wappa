"""
Bearer Token Authentication Strategy

Simple static bearer token comparison using constant-time comparison.
"""

import secrets

from starlette.requests import Request

from ..strategy import AuthResult


class BearerTokenStrategy:
    """
    Bearer token authentication strategy.

    Validates requests against a static bearer token using
    constant-time comparison to prevent timing attacks.

    Example:
        strategy = BearerTokenStrategy(token="my-secret-token")
    """

    def __init__(self, token: str) -> None:
        self._token = token

    async def authenticate(self, request: Request) -> AuthResult:
        """Authenticate request by comparing bearer token."""
        auth_header = request.headers.get("authorization", "")

        if not auth_header.startswith("Bearer "):
            return AuthResult(
                authenticated=False, error="Missing or invalid Authorization header"
            )

        provided_token = auth_header[7:]  # Strip "Bearer "

        if secrets.compare_digest(provided_token, self._token):
            return AuthResult(authenticated=True, user={"type": "api_key"})

        return AuthResult(authenticated=False, error="Invalid bearer token")
