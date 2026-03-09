"""
Wappa Auth Module

First-class authentication system with pluggable strategies and middleware.
"""

from .middleware import AuthMiddleware
from .strategies import BasicAuthStrategy, BearerTokenStrategy, JWTStrategy
from .strategy import AuthResult, AuthStrategy

__all__ = [
    "AuthMiddleware",
    "AuthResult",
    "AuthStrategy",
    "BasicAuthStrategy",
    "BearerTokenStrategy",
    "JWTStrategy",
]
