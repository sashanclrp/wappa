"""
Auth Strategy Protocol and Result

Defines the core contracts for authentication strategies in Wappa.
"""

from dataclasses import dataclass, field
from typing import Any, Protocol

from starlette.requests import Request


@dataclass
class AuthResult:
    """Result of an authentication attempt."""

    authenticated: bool
    user: Any = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class AuthStrategy(Protocol):
    """Protocol that all authentication strategies must implement."""

    async def authenticate(self, request: Request) -> AuthResult:
        """
        Authenticate an incoming request.

        Args:
            request: The incoming HTTP request

        Returns:
            AuthResult with authentication outcome
        """
        ...
