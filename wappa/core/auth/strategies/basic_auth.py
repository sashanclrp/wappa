"""
HTTP Basic Authentication Strategy

Base64 decoded username:password comparison using constant-time comparison.
"""

import base64
import secrets

from starlette.requests import Request

from ..strategy import AuthResult


class BasicAuthStrategy:
    """
    HTTP Basic authentication strategy.

    Validates requests using HTTP Basic Auth with constant-time
    comparison for both username and password.

    Example:
        strategy = BasicAuthStrategy(username="admin", password="secret")
    """

    def __init__(self, username: str, password: str) -> None:
        self._username = username
        self._password = password

    async def authenticate(self, request: Request) -> AuthResult:
        """Authenticate request using HTTP Basic Auth."""
        auth_header = request.headers.get("authorization", "")

        if not auth_header.startswith("Basic "):
            return AuthResult(
                authenticated=False, error="Missing or invalid Authorization header"
            )

        try:
            decoded = base64.b64decode(auth_header[6:]).decode("utf-8")
            username, password = decoded.split(":", 1)
        except Exception:
            return AuthResult(
                authenticated=False, error="Malformed Basic Auth credentials"
            )

        username_match = secrets.compare_digest(username, self._username)
        password_match = secrets.compare_digest(password, self._password)

        if username_match and password_match:
            return AuthResult(
                authenticated=True, user={"type": "basic", "username": username}
            )

        return AuthResult(authenticated=False, error="Invalid credentials")
