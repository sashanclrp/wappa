"""
JWT Authentication Strategy

PyJWT-based token validation supporting both shared-secret (HS256) and
JWKS-based asymmetric verification (ES256, RS256, etc.).
"""

from __future__ import annotations

from starlette.requests import Request

from ..strategy import AuthResult


class JWTStrategy:
    """
    JWT authentication strategy using PyJWT.

    Validates JWT tokens from the Authorization header. Supports two modes:

    - **Shared secret** (symmetric): Provide ``secret`` for HS256/HS384/HS512.
    - **JWKS URL** (asymmetric): Provide ``jwks_url`` for ES256/RS256/etc.
      Keys are fetched lazily and cached; rotation is handled automatically
      via ``kid`` matching.

    Exactly one of ``secret`` or ``jwks_url`` must be provided.

    Raises ImportError at instantiation if PyJWT is not installed,
    so importing this module without PyJWT won't break other strategies.

    Examples:
        # Shared secret (existing usage — unchanged)
        strategy = JWTStrategy(secret="my-secret", algorithms=["HS256"])

        # JWKS URL for asymmetric verification
        strategy = JWTStrategy(
            jwks_url="https://project.supabase.co/auth/v1/.well-known/jwks.json",
            algorithms=["ES256"],
            audience="authenticated",
        )
    """

    def __init__(
        self,
        secret: str | None = None,
        *,
        jwks_url: str | None = None,
        algorithms: list[str] | None = None,
        audience: str | None = None,
        issuer: str | None = None,
        jwks_cache_ttl: int = 300,
    ) -> None:
        try:
            from jwt import PyJWKClient
        except ImportError as e:
            raise ImportError("PyJWT required. Install with: pip install PyJWT") from e

        has_secret = secret is not None
        has_jwks = jwks_url is not None

        if has_secret == has_jwks:
            raise ValueError("Exactly one of 'secret' or 'jwks_url' must be provided.")

        self._secret = secret
        self._algorithms = algorithms or (["HS256"] if has_secret else ["RS256"])
        self._audience = audience
        self._issuer = issuer

        self._jwks_client: PyJWKClient | None = None
        if has_jwks:
            self._jwks_client = PyJWKClient(
                jwks_url, cache_jwk_set=True, lifespan=jwks_cache_ttl
            )

    async def authenticate(self, request: Request) -> AuthResult:
        """Authenticate request by decoding and validating JWT token."""
        import jwt

        auth_header = request.headers.get("authorization", "")

        if not auth_header.startswith("Bearer "):
            return AuthResult(
                authenticated=False, error="Missing or invalid Authorization header"
            )

        token = auth_header.removeprefix("Bearer ")

        try:
            if self._jwks_client is not None:
                signing_key = self._jwks_client.get_signing_key_from_jwt(token)
                key = signing_key.key
            else:
                key = self._secret

            payload = jwt.decode(
                token,
                key,
                algorithms=self._algorithms,
                audience=self._audience,
                issuer=self._issuer,
            )
        except jwt.ExpiredSignatureError:
            return AuthResult(authenticated=False, error="Token has expired")
        except jwt.PyJWKClientError as e:
            return AuthResult(authenticated=False, error=f"JWKS key fetch failed: {e}")
        except jwt.InvalidTokenError as e:
            return AuthResult(authenticated=False, error=f"Invalid token: {e}")

        return AuthResult(
            authenticated=True,
            user=payload,
            metadata={"token_type": "jwt"},
        )
