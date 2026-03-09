"""
JWT Authentication Strategy

PyJWT-based token validation with configurable secret, algorithms, audience, and issuer.
"""

from starlette.requests import Request

from ..strategy import AuthResult


class JWTStrategy:
    """
    JWT authentication strategy using PyJWT.

    Validates JWT tokens from the Authorization header with configurable
    secret, algorithms, audience, and issuer.

    Raises ImportError at instantiation if PyJWT is not installed,
    so importing this module without PyJWT won't break other strategies.

    Example:
        strategy = JWTStrategy(secret="my-secret", algorithms=["HS256"])
    """

    def __init__(
        self,
        secret: str,
        algorithms: list[str] | None = None,
        audience: str | None = None,
        issuer: str | None = None,
    ) -> None:
        try:
            import jwt  # noqa: F401
        except ImportError as e:
            raise ImportError("PyJWT required. Install with: pip install PyJWT") from e

        self._secret = secret
        self._algorithms = algorithms or ["HS256"]
        self._audience = audience
        self._issuer = issuer

    async def authenticate(self, request: Request) -> AuthResult:
        """Authenticate request by decoding and validating JWT token."""
        import jwt

        auth_header = request.headers.get("authorization", "")

        if not auth_header.startswith("Bearer "):
            return AuthResult(
                authenticated=False, error="Missing or invalid Authorization header"
            )

        token = auth_header[7:]  # Strip "Bearer "

        try:
            payload = jwt.decode(
                token,
                self._secret,
                algorithms=self._algorithms,
                audience=self._audience,
                issuer=self._issuer,
            )
        except jwt.ExpiredSignatureError:
            return AuthResult(authenticated=False, error="Token has expired")
        except jwt.InvalidTokenError as e:
            return AuthResult(authenticated=False, error=f"Invalid token: {e}")

        return AuthResult(
            authenticated=True,
            user=payload,
            metadata={"token_type": "jwt"},
        )
