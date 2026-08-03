"""HTTP session lifecycle validation for Wappa's transport layer."""

from __future__ import annotations

import httpx


class HTTPSessionClosedError(RuntimeError):
    """Raised when an HTTP session is used after being closed."""

    pass


class RuntimeDrainingError(RuntimeError):
    """Raised when session access is attempted during runtime shutdown."""

    pass


def validate_session(session: httpx.AsyncClient) -> httpx.AsyncClient:
    """Check that a session is open; raise HTTPSessionClosedError if closed.

    Tolerates duck-typed session objects that lack ``is_closed`` (e.g., test
    doubles) — they are assumed valid.
    """
    if getattr(session, "is_closed", False):
        raise HTTPSessionClosedError(
            "Wappa's HTTP session is closed — outbound platform calls cannot "
            "start. The lifespan may be stopping or may require "
            "WappaCorePlugin.recreate_http_session()."
        )
    return session
