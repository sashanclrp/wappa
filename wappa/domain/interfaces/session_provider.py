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
            "httpx.AsyncClient (app.state.http_session) is closed — all "
            "outbound WhatsApp API calls will fail. Cause: app shutdown or "
            "hot-reload closed the lifespan transport. Fix: call "
            "WappaCorePlugin.recreate_http_session(app) to restore it, or "
            "ensure the host app does not close the Wappa lifespan while "
            "background handlers (expiry, cron) are still in flight."
        )
    return session
